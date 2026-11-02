import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash, X509Certificate } from "node:crypto";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const Observations = require("../chaincode/lib/observations.js");
const { normalize, proofDigest } = require("../chaincode/lib/proof.js");
const cert = readFileSync(new URL("recorder-certificate.txt", import.meta.url));
const hash = (b) => createHash("sha256").update(b).digest("hex");
const key = Buffer.from(
  JSON.stringify({ protocol: "groth16", curve: "bn128", nPublic: 1 }),
);
const cfg = {
  channelName: "csi",
  readerMspIds: ["Org1MSP", "Org2MSP"],
  recorderMspId: "Org1MSP",
  recorderCertificateHash: hash(new X509Certificate(cert).raw),
  verificationKeyHash: hash(key),
  deploymentId: "test",
  debugMode: true,
};
const payload = {
  observationId: "0x" + "1".repeat(64),
  patientRef: "0x" + "2".repeat(64),
  observedAt: 1,
  durationSeconds: 60,
  proof: {
    protocol: "groth16",
    curve: "bn128",
    pi_a: ["1", "2", "1"],
    pi_b: [
      ["1", "2"],
      ["3", "4"],
      ["1", "0"],
    ],
    pi_c: ["1", "2", "1"],
  },
  publicSignals: ["1"],
};
function context(msp = "Org1MSP", channel = "csi") {
  const state = new Map();
  return {
    clientIdentity: { getMSPID: () => msp, getIDBytes: () => cert },
    stub: {
      getChannelID: () => channel,
      getTxTimestamp: () => ({ seconds: 100 }),
      getTxID: () => "a".repeat(64),
      createCompositeKey: (type, args) => type + args.join(":"),
      getState: async (k) => state.get(k) || Buffer.alloc(0),
      putState: async (k, v) => state.set(k, v),
      setEvent: () => {},
    },
    state,
  };
}
test("Record stores no verified flag; metadata and idempotency never disclose output", async () => {
  const contract = new Observations(cfg, key),
    ctx = context();
  const first = JSON.parse(
    await contract.RecordObservation(
      ctx,
      JSON.stringify({ ...payload, rawCSI: "private" }),
    ),
  );
  assert.equal(first.reused, false);
  assert.equal("isNormal" in first, false);
  assert.equal(ctx.state.size, 2);
  assert.equal(
    [...ctx.state.values()].some((v) => v.includes("private")),
    false,
  );
  const again = JSON.parse(
    await contract.RecordObservation(ctx, JSON.stringify(payload)),
  );
  assert.equal(again.reused, true);
  assert.equal(again.transactionId, first.transactionId);
  const metadata = JSON.parse(
    await contract.ReadObservation(ctx, payload.observationId),
  );
  assert.equal("publicSignals" in metadata, false);
  assert.equal("proof" in metadata, false);
  await assert.rejects(
    contract.RecordObservation(
      ctx,
      JSON.stringify({ ...payload, durationSeconds: 61 }),
    ),
    /Conflicting/,
  );
  await assert.rejects(
    contract.RecordObservation(
      ctx,
      JSON.stringify({ ...payload, observationId: "0x" + "3".repeat(64) }),
    ),
    /Duplicate/,
  );
});
test("Organization, certificate, channel and time authorization", async () => {
  const contract = new Observations(cfg, key);
  await assert.rejects(
    contract.RecordObservation(context("Org2MSP"), JSON.stringify(payload)),
    /Unauthorized recorder/,
  );
  await assert.rejects(
    new Observations(
      { ...cfg, recorderCertificateHash: "bad" },
      key,
    ).RecordObservation(context(), JSON.stringify(payload)),
    /Unauthorized recorder/,
  );
  await assert.rejects(
    contract.ReadObservation(context("Unknown"), payload.observationId),
    /Unauthorized reader/,
  );
  await assert.rejects(
    contract.ReadObservation(
      context("Org1MSP", "another"),
      payload.observationId,
    ),
    /Unauthorized reader/,
  );
  await assert.rejects(
    contract.RecordObservation(
      context(),
      JSON.stringify({ ...payload, observedAt: 500 }),
    ),
    /Future/,
  );
  assert.throws(
    () => new Observations({ ...cfg, verificationKeyHash: "wrong" }, key),
    /Verification key mismatch/,
  );
});
test("Reject malformed or non-canonical proof fields before storing", () => {
  assert.throws(() => normalize({ ...payload, publicSignals: ["2"] }));
  assert.throws(() => normalize({ ...payload, publicSignals: [1] }));
  assert.throws(() =>
    normalize({
      ...payload,
      proof: { ...payload.proof, pi_a: ["01", "2", "1"] },
    }),
  );
  assert.throws(() => normalize({ ...payload, durationSeconds: 1.5 }));
  assert.match(proofDigest(normalize(payload)), /^0x[0-9a-f]{64}$/);
});
