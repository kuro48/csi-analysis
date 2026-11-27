import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { validateExternalInventory, validatePeerEndpoint, prepareExternal } from "../scripts/prepare-external.mjs";

const root = resolve(import.meta.dirname, "../..");
function inventory() {
  return JSON.parse(readFileSync(join(root, "deploy/staging/inventory.example.json"), "utf8").replaceAll("example.invalid", "csi.home.arpa"));
}
test("external profile rejects local topology and unresolved placeholders", () => {
  const cfg = inventory();
  assert.equal(validateExternalInventory(cfg).orderers.length, 3);
  assert.throws(() => validateExternalInventory(JSON.parse(readFileSync(join(root, "deploy/staging/inventory.example.json")))));
  const sameHost = structuredClone(cfg); sameHost.organizations[1].hostId = sameHost.organizations[0].hostId;
  assert.throws(() => validateExternalInventory(sameHost));
  const sameOrderer = structuredClone(cfg); sameOrderer.orderers[2].hostId = sameOrderer.orderers[0].hostId;
  assert.throws(() => validateExternalInventory(sameOrderer));
  const sameOrg = structuredClone(cfg); sameOrg.organizations[1].mspId = sameOrg.organizations[0].mspId;
  assert.throws(() => validateExternalInventory(sameOrg));
});

test("two-host bootstrap explicitly permits one orderer but never collocates both peers", () => {
  const cfg = inventory();
  cfg.orderers = cfg.orderers.slice(0, 1);
  assert.throws(() => validateExternalInventory(cfg), /three-host-raft/);
  cfg.deploymentProfile = "two-host-bootstrap";
  assert.equal(validateExternalInventory(cfg).orderers.length, 1);
  const sameHost = structuredClone(cfg); sameHost.organizations[1].hostId = sameHost.organizations[0].hostId;
  assert.throws(() => validateExternalInventory(sameHost));
  const extraHost = structuredClone(cfg); extraHost.orderers[0].hostId = "unexpected-host";
  assert.throws(() => validateExternalInventory(extraHost), /share/);
  const collision = structuredClone(cfg);
  collision.orderers[0].host = cfg.organizations[0].peerHost;
  collision.orderers[0].port = 7051;
  assert.throws(() => validateExternalInventory(collision), /collide/);
  const unknown = structuredClone(cfg); unknown.deploymentProfile = "anything";
  assert.throws(() => validateExternalInventory(unknown), /Unknown/);
});

test("distributed channel and gateway use explicit ports while preserving existing defaults", () => {
  const dir = mkdtempSync(join(tmpdir(), "csi-channel-ports-"));
  try {
    const cfg = inventory();
    const render = name => {
      const input = join(dir, name + ".json"), output = join(dir, name + ".yaml");
      writeFileSync(input, JSON.stringify(cfg));
      execFileSync(process.execPath, [join(root, "deploy/staging/render-channel.mjs"), input, output]);
      return JSON.parse(readFileSync(output)).Profiles.CSIStaging;
    };
    const original = render("default");
    assert.equal(original.Orderer.EtcdRaft.Consenters[0].Port, 7050);
    assert.equal(original.Application.Organizations[0].AnchorPeers[0].Port, 7051);
    cfg.organizations.forEach(org => { org.peerPort = 17051; });
    cfg.orderers.forEach(node => { node.port = 17050; });
    const changed = render("isolated");
    assert.ok(changed.Orderer.Addresses.every(address => address.endsWith(":17050")));
    assert.ok(changed.Orderer.Organizations[0].OrdererEndpoints.every(address => address.endsWith(":17050")));
    assert.ok(changed.Orderer.EtcdRaft.Consenters.every(node => node.Port === 17050));
    assert.ok(changed.Application.Organizations.every(org => org.AnchorPeers[0].Port === 17051));
    assert.equal(validatePeerEndpoint("peer.hospital.csi.home.arpa:17051"), "peer.hospital.csi.home.arpa:17051");
    for (const bad of ["localhost:17051", "127.0.0.1:17051", "peer.example.invalid:17051", "peer.csi.home.arpa:65536", "peer.csi.home.arpa:0"])
      assert.throws(() => validatePeerEndpoint(bad));
    for (const port of [0, -1, 65536, 7051.5, "17051"]) {
      const invalid = structuredClone(cfg); invalid.organizations[0].peerPort = port;
      assert.throws(() => validateExternalInventory(invalid), /port/);
      const invalidOrderer = structuredClone(cfg); invalidOrderer.orderers[0].port = port;
      assert.throws(() => validateExternalInventory(invalidOrderer), /port/);
    }
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("external package pins real verification key and recorder certificate without copying private keys", () => {
  const dir = mkdtempSync(join(tmpdir(), "csi-external-"));
  try {
    execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=test-recorder", "-keyout", join(dir, "private.key"), "-out", join(dir, "recorder.crt")], { stdio: "ignore" });
    const cfg = inventory(); cfg.recorderCertificate = join(dir, "recorder.crt");
    const keyPath = join(root, "docs/progress/2026-11-09-adaptive-4004/verification_key.json");
    const key = readFileSync(keyPath);
    const artifact = { circuit: "csi_lomb_scargle_adaptive_4004", capacity: 4004, sampleCount: 64, publicSignalCount: 70, isNormalIndex: 1,
      files: { verificationKey: keyPath }, sha256: { verificationKey: createHash("sha256").update(key).digest("hex") } };
    writeFileSync(join(dir, "artifacts.json"), JSON.stringify(artifact));
    const out = join(dir, "release");
    const result = prepareExternal(cfg, join(dir, "artifacts.json"), out);
    assert.equal(result.topology.singleHost, false);
    assert.equal(result.topology.endorsementPolicy, "AND('HospitalMSP.peer','ResearchMSP.peer')");
    assert.deepEqual(readFileSync(join(out, "deployment/verification_key.json")), key);
    assert.ok(!readdirSync(out, { recursive: true }).some(name => String(name).endsWith(".key")));
    assert.throws(() => prepareExternal(cfg, join(dir, "artifacts.json"), out), /already exists/);
    cfg.deploymentProfile = "two-host-bootstrap";
    cfg.orderers = cfg.orderers.slice(0, 1);
    const twoHost = prepareExternal(cfg, join(dir, "artifacts.json"), join(dir, "two-host"));
    assert.equal(twoHost.topology.orderers, 1);
    assert.equal(twoHost.topology.ordererFaultTolerance, 0);
    assert.equal(twoHost.topology.hostIds.length, 2);
    assert.notEqual(twoHost.deploymentId, result.deploymentId);
    artifact.sha256.verificationKey = "0".repeat(64);
    writeFileSync(join(dir, "artifacts.json"), JSON.stringify(artifact));
    assert.throws(() => prepareExternal(cfg, join(dir, "artifacts.json"), join(dir, "bad")), /verification key/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("bridge refuses non-loopback cleartext before contacting a peer", () => {
  const dir = mkdtempSync(join(tmpdir(), "csi-bridge-"));
  try {
    const cfg = join(dir, "gateway.json"); writeFileSync(cfg, "{}");
    const run = spawnSync(process.execPath, [join(root, "fabric/gateway-server.mjs")], {
      env: { ...process.env, FABRIC_GATEWAY_CONFIG: cfg, FABRIC_BRIDGE_ROLE: "reader", FABRIC_BRIDGE_TOKEN: "a".repeat(64), FABRIC_BRIDGE_HOST: "0.0.0.0", FABRIC_BRIDGE_TLS_CERT: "", FABRIC_BRIDGE_TLS_KEY: "", FABRIC_BRIDGE_TOKEN_FILE: "" }, encoding: "utf8", timeout: 10000,
    });
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /Non-loopback bridges require TLS/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
