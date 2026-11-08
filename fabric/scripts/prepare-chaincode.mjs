// Packages public configuration and verification key only; identities stay outside chaincode.
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  cpSync,
  readdirSync,
  existsSync,
} from "node:fs";
import { resolve, join } from "node:path";
import { createHash, X509Certificate, randomBytes } from "node:crypto";
const root = resolve(import.meta.dirname, "../..");
const local = resolve(
  process.env.FABRIC_WORK_DIR || join(root, ".local/fabric"),
);
const network = resolve(process.env.FABRIC_NETWORK_DIR || join(local, "fabric-samples/test-network"));
const source = join(root, "fabric/chaincode");
const destination = join(local, "chaincode");
const deployment = join(local, "deployment");
const vkey = readFileSync(
  process.env.FABRIC_VKEY ||
    join(
      root,
      "backend/contracts/build/onchain/csi_breathing_certificate.vkey.json",
    ),
);
const hash = (b) => createHash("sha256").update(b).digest("hex");
const identity = (org) => {
  const msp = join(
    network,
    `organizations/peerOrganizations/org${org}.example.com/users/User1@org${org}.example.com/msp`,
  );
  const only = (dir) => {
    const files = readdirSync(dir);
    if (files.length !== 1) throw Error("Expected one identity file");
    return join(dir, files[0]);
  };
  return {
    mspId: `Org${org}MSP`,
    certificate: only(join(msp, "signcerts")),
    privateKey: only(join(msp, "keystore")),
  };
};
const writer = identity(1),
  reader = identity(2);
const config = {
  version: 1,
  channelName: "csi",
  chaincodeName: process.env.FABRIC_CHAINCODE_NAME || "csiobservations",
  networkName: "Fabric local consortium",
  debugMode: process.env.FABRIC_DEBUG_MODE === "true",
  recorderMspId: writer.mspId,
  recorderCertificateHash: hash(
    new X509Certificate(readFileSync(writer.certificate)).raw,
  ),
  readerMspIds: ["Org1MSP", "Org2MSP"],
  verificationKeyHash: "0x" + hash(vkey),
  publicSignalCount: JSON.parse(vkey).nPublic,
  isNormalIndex: JSON.parse(vkey).nPublic === 70 ? 1 : 0,
  circuit: JSON.parse(vkey).nPublic === 70 ? "csi_lomb_scargle_adaptive_4004" : "csi_breathing_certificate",
  verificationKeyFile: "verification_key.json",
  sourceHash: hash(
    [
      "index.js",
      "lib/proof.js",
      "lib/observations.js",
      "package.json",
      "package-lock.json",
    ]
      .map((f) => readFileSync(join(source, f)))
      .reduce((a, b) => Buffer.concat([a, b]), Buffer.alloc(0)),
  ),
  topology: {
    peerOrganizations: 2,
    peers: 2,
    orderers: 1,
    consensus: "Raft",
    endorsementPolicy: "AND('Org1MSP.peer','Org2MSP.peer')",
    fabricVersion: "2.5.16",
    singleHost: true,
  },
};
if (![1, 70].includes(config.publicSignalCount)) throw Error("Unsupported proof protocol");
if (config.publicSignalCount === 70 && config.chaincodeName === "csiobservations") throw Error("Adaptive proofs require a separate chaincode name");
if (config.publicSignalCount === 70) {
  if (!process.env.ADAPTIVE_ARTIFACT_MANIFEST) throw Error("Adaptive deployment requires its artifact manifest");
  const artifacts = JSON.parse(readFileSync(process.env.ADAPTIVE_ARTIFACT_MANIFEST));
  if (artifacts.circuit !== config.circuit || artifacts.capacity !== 4004 || artifacts.sampleCount !== 64
      || artifacts.publicSignalCount !== 70 || artifacts.isNormalIndex !== 1 || artifacts.sha256.verificationKey !== hash(vkey)) {
    throw Error("Fabric key does not match the full-pool artifact manifest");
  }
}
config.deploymentId = "0x" + hash(JSON.stringify(config));
if (
  existsSync(join(deployment, "manifest.json")) &&
  JSON.parse(readFileSync(join(deployment, "manifest.json"))).deploymentId !==
    config.deploymentId &&
  process.env.FABRIC_UPGRADE !== "true"
)
  throw Error(
    "Deployment already pinned. For an intentional lifecycle upgrade set FABRIC_UPGRADE=true and increment chaincode sequence.",
  );
mkdirSync(join(destination, "deployment"), { recursive: true });
mkdirSync(deployment, { recursive: true });
for (const f of ["index.js", "lib", "package.json", "package-lock.json"])
  cpSync(join(source, f), join(destination, f), { recursive: true });
for (const dir of [join(destination, "deployment"), deployment]) {
  writeFileSync(
    join(dir, dir === deployment ? "manifest.json" : "config.json"),
    JSON.stringify(config, null, 2) + "\n",
  );
  writeFileSync(join(dir, config.verificationKeyFile), vkey);
  if (config.publicSignalCount === 1) writeFileSync(join(dir, "csi_breathing_certificate.vkey.json"), vkey);
}
const gateway = {
  ...config,
  peerEndpoint: "localhost:7051",
  peerHostAlias: "peer0.org1.example.com",
  tlsRootCert: join(
    network,
    "organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt",
  ),
  writer,
  reader,
};
writeFileSync(
  join(local, "gateway.json"),
  JSON.stringify(gateway, null, 2) + "\n",
  { mode: 0o600 },
);
for (const role of ["reader", "writer"]) {
  // Separate files prevent the reader process from receiving the writer's identity paths.
  const roleConfig = { ...gateway };
  delete roleConfig[role === "reader" ? "writer" : "reader"];
  writeFileSync(
    join(local, `gateway-${role}.json`),
    JSON.stringify(roleConfig, null, 2) + "\n",
    { mode: 0o600 },
  );
  if (!existsSync(join(local, `${role}.token`)))
    writeFileSync(
      join(local, `${role}.token`),
      randomBytes(32).toString("hex"),
      { mode: 0o600 },
    );
}
console.log(
  JSON.stringify({
    package: destination,
    manifest: join(deployment, "manifest.json"),
    deploymentId: config.deploymentId,
    debugMode: config.debugMode,
  }),
);
