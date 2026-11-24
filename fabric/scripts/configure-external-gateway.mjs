// Run separately on EACH bridge host. This reads only that role's private key.
import { readFileSync, writeFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { X509Certificate, createPrivateKey, createHash } from "node:crypto";
const [manifestPath, role, mspId, peerEndpoint, directory] = process.argv.slice(2);
if (!directory || !["reader", "writer"].includes(role))
  throw Error("Usage: configure-external-gateway.mjs manifest.json reader|writer MSP peer.dns:7051 IDENTITY_DIR");
const manifest = JSON.parse(readFileSync(manifestPath));
if (manifest.topology?.singleHost !== false || !manifest.readerMspIds.includes(mspId)) throw Error("Wrong consortium manifest/MSP");
if (!/^[a-z0-9.-]+:7051$/.test(peerEndpoint) || peerEndpoint.startsWith("localhost:")) throw Error("Use peer DNS endpoint");
const cert = new X509Certificate(readFileSync(join(directory, "client.crt")));
const keyPath = join(directory, "client.key");
if (statSync(keyPath).mode & 0o077) throw Error("Client key must have mode 0600");
if (!cert.checkPrivateKey(createPrivateKey(readFileSync(keyPath)))) throw Error("Identity key/certificate mismatch");
if (role === "writer" && (mspId !== manifest.recorderMspId ||
    createHash("sha256").update(cert.raw).digest("hex") !== manifest.recorderCertificateHash)) throw Error("Writer identity not pinned to this deployment");
const config = { ...manifest, peerEndpoint, tlsRootCert: "/identity/peer-ca.crt",
  [role]: { mspId, certificate: "/identity/client.crt", privateKey: "/identity/client.key" } };
writeFileSync(join(directory, "gateway.json"), JSON.stringify(config, null, 2) + "\n", { flag: "wx", mode: 0o600 });
console.log(JSON.stringify({ role, deploymentId: manifest.deploymentId, configured: true, connected: false }));
