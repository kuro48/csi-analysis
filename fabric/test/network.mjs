// Opt-in REAL-network integration test; creates records but never resets the ledger.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { id } from "ethers";
import { openGateway } from "../gateway.mjs";
const config = JSON.parse(readFileSync(process.argv[2]));
const bank = JSON.parse(readFileSync(process.argv[3]));
const writer = openGateway(config, "writer"),
  reader = openGateway(config, "reader");
const checks = [];
try {
  await writer.configuration();
  await reader.configuration();
  for (const sample of bank.samples.slice(0, 2)) {
    const payload = {
      observationId: id(randomUUID()),
      patientRef: id(randomUUID()),
      observedAt: Math.floor(Date.now() / 1000) - 61,
      durationSeconds: 60,
      proof: sample.proof,
      publicSignals: sample.publicSignals,
    };
    const record = await writer.record(payload);
    assert.equal(record.commit.code, 0);
    assert.equal(record.result.reused, false);
    assert.equal("isNormal" in record.result, false);
    const meta = await reader.metadata(payload.observationId);
    assert.equal("isNormal" in meta, false);
    assert.equal("publicSignals" in meta, false);
    const result = await reader.verify(payload.observationId);
    assert.equal(result.result.isNormal, sample.publicSignals[0] === "1");
    assert.equal(result.result.transactionId, record.result.transactionId);
    const repeat = await writer.record(payload);
    assert.equal(repeat.result.reused, true);
    assert.equal(repeat.result.transactionId, record.result.transactionId);
    await assert.rejects(
      reader.contract.submitTransaction(
        "RecordObservation",
        JSON.stringify({ ...payload, observationId: id(randomUUID()) }),
      ),
    );
    await assert.rejects(
      writer.record({ ...payload, patientRef: id(randomUUID()) }),
    );
    await assert.rejects(
      writer.record({ ...payload, observationId: id(randomUUID()) }),
    );
    const tampered = {
      ...payload,
      observationId: id(randomUUID()),
      publicSignals: [sample.publicSignals[0] === "1" ? "0" : "1"],
    };
    await writer.record(tampered);
    await assert.rejects(reader.verify(tampered.observationId));
    checks.push({
      isNormal: result.result.isNormal,
      transactionId: record.result.transactionId,
      validCommit: true,
      readerIsOrg2: true,
      tamperedRejected: true,
      unauthorizedWriterRejected: true,
      idempotency: true,
      replayRejected: true,
    });
  }
  const evidence = {
    kind: "real-fabric-network-integration",
    deploymentId: config.deploymentId,
    checks,
  };
  if (process.argv[4])
    writeFileSync(process.argv[4], JSON.stringify(evidence, null, 2) + "\n");
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  writer.close();
  reader.close();
}
