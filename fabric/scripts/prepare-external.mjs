// Packages existing circuit/key for an independently provisioned consortium.
// Reads PUBLIC certificates only. No enrollment, key generation, or network writes.
import { readFileSync, writeFileSync, mkdirSync, cpSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { createHash, X509Certificate } from "node:crypto";
import { fileURLToPath } from "node:url";
import { protocol } from "../chaincode/lib/proof.js";

const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const identifier = /^[A-Za-z][A-Za-z0-9_-]{1,63}$/;
function validateHost(host) {
  if (typeof host !== "string" || !/^(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?$/.test(host)
      || !host.includes(".") || /(^localhost$|\.localhost$|\.example\.(com|org|net)$|\.invalid$)/.test(host)
      || /^\d+\.\d+\.\d+\.\d+$/.test(host)) throw Error("Use actual DNS names matching issued TLS certificates");
}
function validatePort(port) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error("Use an integer port between 1024 and 65535");
}
export function validatePeerEndpoint(endpoint) {
  if (typeof endpoint !== "string" || !/^[a-z0-9.-]+:[1-9][0-9]{0,4}$/.test(endpoint)) throw Error("Use peer DNS:port endpoint");
  const [host, port] = endpoint.split(":");
  validateHost(host); validatePort(Number(port));
  return endpoint;
}
export function validateExternalInventory(input) {
  if (input.version !== 1 || input.environment !== "distributed-staging") throw Error("Expected distributed-staging inventory");
  if (!/^[a-z][a-z0-9.-]{1,63}$/.test(input.channelName) || !identifier.test(input.chaincodeName)) throw Error("Invalid channel or chaincode");
  if (typeof input.debugMode !== "boolean" || !input.networkName?.trim()) throw Error("Explicit network name/debugMode required");
  const profile = input.deploymentProfile ?? "three-host-raft";
  if (!["three-host-raft", "two-host-bootstrap"].includes(profile)) throw Error("Unknown deployment profile");
  const ordererCount = profile === "two-host-bootstrap" ? 1 : 3;
  if (input.organizations?.length !== 2 || input.orderers?.length !== ordererCount)
    throw Error(`${profile} requires two peer organizations and ${ordererCount} orderers`);
  const orgIds = input.organizations.map(org => org.mspId);
  if (new Set(orgIds).size !== 2 || orgIds.some(id => !identifier.test(id))) throw Error("Distinct MSP IDs required");
  if (!identifier.test(input.ordererMspId) || orgIds.includes(input.ordererMspId)) throw Error("Separate orderer MSP required");
  const hosts = [...input.organizations.map(org => org.peerHost), ...input.orderers.map(node => node.host)];
  if (new Set(input.organizations.map(org => org.peerHost)).size !== 2 ||
      new Set(input.orderers.map(node => node.host)).size !== ordererCount) throw Error("Distinct peer/orderer DNS endpoints required");
  for (const host of hosts) validateHost(host);
  for (const org of input.organizations) validatePort(org.peerPort ?? 7051);
  for (const node of input.orderers) validatePort(node.port ?? 7050);
  if (input.organizations[0].hostId === input.organizations[1].hostId ||
      new Set(input.orderers.map(node => node.hostId)).size !== ordererCount ||
      [...input.organizations, ...input.orderers].some(node => !identifier.test(node.hostId)))
    throw Error("Peers must use separate hosts; orderers need distinct hostIds");
  if (profile === "two-host-bootstrap" && !input.organizations.some(org => org.hostId === input.orderers[0].hostId))
    throw Error("Two-host bootstrap orderer must share one of the two peer hosts");
  const endpoints = [...input.organizations.map(org => `${org.peerHost}:${org.peerPort ?? 7051}`),
    ...input.orderers.map(node => `${node.host}:${node.port ?? 7050}`)];
  if (new Set(endpoints).size !== endpoints.length) throw Error("Peer and orderer endpoints must not collide");
  if (!orgIds.includes(input.recorderMspId) || !input.recorderCertificate) throw Error("Recorder public certificate required");
  return input;
}

export function prepareExternal(inventory, artifactsPath, destination) {
  const input = validateExternalInventory(inventory);
  const source = resolve(import.meta.dirname, "../chaincode");
  const artifacts = JSON.parse(readFileSync(artifactsPath));
  if (artifacts.circuit !== "csi_lomb_scargle_adaptive_4004" || artifacts.capacity !== 4004 ||
      artifacts.sampleCount !== 64 || artifacts.publicSignalCount !== 70 || artifacts.isNormalIndex !== 1)
    throw Error("Expected the stable adaptive4004 artifact profile");
  const vkey = readFileSync(artifacts.files.verificationKey);
  const parsed = JSON.parse(vkey);
  if (hash(vkey) !== artifacts.sha256.verificationKey || parsed.nPublic !== 70 || parsed.IC?.length !== 71 ||
      parsed.protocol !== "groth16" || parsed.curve !== "bn128") throw Error("Invalid pinned verification key");
  const cert = new X509Certificate(readFileSync(input.recorderCertificate));
  if (Date.parse(cert.validTo) <= Date.now() || Date.parse(cert.validFrom) > Date.now()) throw Error("Recorder certificate not currently valid");
  const orgIds = input.organizations.map(org => org.mspId);
  const files = ["index.js", "lib/proof.js", "lib/observations.js", "package.json", "package-lock.json"];
  const config = {
    version: 1, channelName: input.channelName, chaincodeName: input.chaincodeName,
    networkName: input.networkName, debugMode: input.debugMode,
    recorderMspId: input.recorderMspId, recorderCertificateHash: hash(cert.raw), readerMspIds: orgIds,
    verificationKeyHash: "0x" + hash(vkey), publicSignalCount: 70, isNormalIndex: 1,
    circuit: artifacts.circuit, verificationKeyFile: "verification_key.json",
    sourceHash: hash(Buffer.concat(files.map(file => readFileSync(join(source, file))))),
    topology: {
      peerOrganizations: 2, peers: 2, orderers: input.orderers.length, consensus: "Raft",
      deploymentProfile: input.deploymentProfile ?? "three-host-raft",
      ordererFaultTolerance: Math.floor((input.orderers.length - 1) / 2),
      endorsementPolicy: `AND('${orgIds[0]}.peer','${orgIds[1]}.peer')`,
      fabricVersion: "2.5.16", singleHost: false, environment: input.environment,
      // Claimed inventory, not proof that nodes are actually deployed.
      hostIds: [...new Set([...input.organizations, ...input.orderers].map(node => node.hostId))],
    },
  };
  protocol(config);
  config.deploymentId = "0x" + hash(JSON.stringify(config));
  if (existsSync(destination)) throw Error("Output already exists; use a new release directory");
  const packageDir = join(destination, "chaincode");
  mkdirSync(join(packageDir, "deployment"), { recursive: true });
  mkdirSync(join(destination, "deployment"));
  for (const file of ["index.js", "lib", "package.json", "package-lock.json"])
    cpSync(join(source, file), join(packageDir, file), { recursive: true });
  for (const [dir, name] of [[join(packageDir, "deployment"), "config.json"], [join(destination, "deployment"), "manifest.json"]]) {
    writeFileSync(join(dir, name), JSON.stringify(config, null, 2) + "\n");
    writeFileSync(join(dir, "verification_key.json"), vkey);
  }
  writeFileSync(join(destination, "inventory.json"), JSON.stringify(input, null, 2) + "\n");
  return config;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [inventory, artifacts, destination] = process.argv.slice(2);
  if (!destination) throw Error("Usage: prepare-external.mjs inventory.json artifacts.json NEW_OUTPUT_DIR");
  const result = prepareExternal(JSON.parse(readFileSync(inventory)), artifacts, resolve(destination));
  console.log(JSON.stringify({ deploymentId: result.deploymentId, output: resolve(destination), deployed: false }));
}
