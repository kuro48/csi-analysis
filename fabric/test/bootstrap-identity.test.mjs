import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, statSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { X509Certificate, createPrivateKey } from "node:crypto";

test("host-local bootstrap isolates roots, preserves node roles and exports no secrets", () => {
  const dir = mkdtempSync(join(tmpdir(), "csi-host-pki-"));
  const script = resolve(import.meta.dirname, "../../scripts/staging/bootstrap_fabric_identity.py");
  const cert = path => new X509Certificate(readFileSync(path));
  try {
    const hospital = join(dir, "hospital"), ordering = join(dir, "ordering");
    execFileSync("python3", [script, hospital, "--msp-id", "HospitalMSP", "--dns", "hospital.csi.home.arpa", "--bridge-role", "writer"]);
    execFileSync("python3", [script, ordering, "--msp-id", "OrderingMSP", "--dns", "ordering.csi.home.arpa", "--node-role", "orderer"]);
    const signing = cert(join(hospital, "ca/signing/ca.crt"));
    const tls = cert(join(hospital, "ca/tls/ca.crt"));
    const writer = cert(join(hospital, "bridge/client.crt"));
    assert.equal(writer.verify(signing.publicKey), true);
    assert.equal(writer.verify(tls.publicKey), false);
    assert.match(writer.subject, /OU=client/);
    assert.match(cert(join(hospital, "node/msp/signcerts/cert.pem")).subject, /OU=peer/);
    assert.match(cert(join(hospital, "admin/msp/signcerts/cert.pem")).subject, /OU=admin/);
    assert.equal(cert(join(hospital, "node/tls/server.crt")).checkHost("hospital.csi.home.arpa"), "hospital.csi.home.arpa");
    assert.equal(writer.checkPrivateKey(createPrivateKey(readFileSync(join(hospital, "bridge/client.key")))), true);
    assert.equal(statSync(join(hospital, "bridge/client.key")).mode & 0o077, 0);
    assert.deepEqual(readFileSync(join(hospital, "public/recorder.crt")), readFileSync(join(hospital, "bridge/client.crt")));
    for (const root of [hospital, ordering]) {
      for (const name of readdirSync(join(root, "public"), { recursive: true })) {
        const path = join(root, "public", String(name));
        if (statSync(path).isFile()) assert.doesNotMatch(readFileSync(path, "utf8"), /PRIVATE KEY|bridge.token/);
      }
    }
    const adminTls = cert(join(ordering, "admin-tls/cert.pem"));
    assert.equal(adminTls.verify(cert(join(ordering, "ca/admin-tls/ca.crt")).publicKey), true);
    assert.equal(adminTls.verify(cert(join(ordering, "ca/tls/ca.crt")).publicKey), false);
    const duplicate = spawnSync("python3", [script, hospital, "--msp-id", "HospitalMSP", "--dns", "hospital.csi.home.arpa"]);
    assert.notEqual(duplicate.status, 0);
    assert.deepEqual(cert(join(hospital, "bridge/client.crt")).raw, writer.raw);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
