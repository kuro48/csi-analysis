// Requires only PUBLIC organization MSPs and node TLS certificates under /srv/csi/public.
import { readFileSync, writeFileSync } from "node:fs";
import { validateExternalInventory } from "../../fabric/scripts/prepare-external.mjs";
const [inventory, output] = process.argv.slice(2);
if (!output) throw Error("Usage: render-channel.mjs inventory.json configtx.yaml");
const cfg = validateExternalInventory(JSON.parse(readFileSync(inventory)));
const signature = Rule => ({ Type: "Signature", Rule });
const implicit = Rule => ({ Type: "ImplicitMeta", Rule });
const org = (id, peer) => ({
  Name: id, ID: id, MSPDir: `/srv/csi/public/${id}/msp`,
  Policies: {
    Readers: signature(`OR('${id}.member')`),
    Writers: signature(`OR('${id}.member')`),
    Admins: signature(`OR('${id}.admin')`),
    ...(peer ? { Endorsement: signature(`OR('${id}.peer')`) } : {}),
  },
  ...(peer ? { AnchorPeers: [{ Host: peer, Port: 7051 }] }
    : { OrdererEndpoints: cfg.orderers.map(node => `${node.host}:7050`) }),
});
const defaults = { Readers: implicit("ANY Readers"), Writers: implicit("ANY Writers"), Admins: implicit("MAJORITY Admins") };
const outputConfig = { Profiles: { CSIStaging: {
  Capabilities: { V2_0: true }, Policies: defaults,
  Orderer: {
    OrdererType: "etcdraft", Addresses: cfg.orderers.map(node => `${node.host}:7050`),
    BatchTimeout: "2s", BatchSize: { MaxMessageCount: 10, AbsoluteMaxBytes: "99 MB", PreferredMaxBytes: "512 KB" },
    EtcdRaft: { Consenters: cfg.orderers.map(node => ({
      Host: node.host, Port: 7050,
      ClientTLSCert: `/srv/csi/public/orderers/${node.host}.crt`,
      ServerTLSCert: `/srv/csi/public/orderers/${node.host}.crt`,
    })) },
    Organizations: [org(cfg.ordererMspId)], Capabilities: { V2_0: true },
    Policies: { ...defaults, BlockValidation: implicit("ANY Writers") },
  },
  Application: {
    Organizations: cfg.organizations.map(o => org(o.mspId, o.peerHost)), Capabilities: { V2_5: true },
    Policies: { ...defaults, LifecycleEndorsement: implicit("MAJORITY Endorsement"), Endorsement: implicit("MAJORITY Endorsement") },
  },
} } };
// JSON is a YAML subset accepted by Fabric's YAML parser.
writeFileSync(output, JSON.stringify(outputConfig, null, 2) + "\n", { flag: "wx" });
