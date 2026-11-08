// Local-network negative control with a real full-pool proof (writes one invalid Fabric test record).
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { JsonRpcProvider, Contract, id } from 'ethers';
import { openGateway } from '../gateway.mjs';
const root = resolve(import.meta.dirname, '../..');
const evidence = resolve(root, 'docs/progress/2026-11-09-adaptive-4004');
const bundle = JSON.parse(readFileSync(resolve(evidence, 'evm-proof-bundle.json')));
assert.equal(bundle.publicSignals[69], '4004');
const manifest = JSON.parse(readFileSync(resolve(root, '.local/adaptive-evm/1337/manifest.json')));
const provider = new JsonRpcProvider('http://127.0.0.1:8545');
const gateway = openGateway(JSON.parse(readFileSync(resolve(root, '.local/fabric-adaptive/gateway.json'))), 'writer');
const reader = openGateway(JSON.parse(readFileSync(resolve(root, '.local/fabric-adaptive/gateway-reader.json'))), 'reader');
const report = { fullPool: 4004, validEvmProof: false, modifiedPublicSignalsRejected: [], invalidFabricRecordRejectedOnRead: false };
try {
  assert.equal(Number((await provider.getNetwork()).chainId), 1337);
  const verifier = new Contract(manifest.verifierAddress, ['function verifyProof(uint256[2],uint256[2][2],uint256[2],uint256[70]) view returns (bool)'], provider);
  const p = bundle.proof;
  const points = [p.pi_a.slice(0,2), [[p.pi_b[0][1],p.pi_b[0][0]],[p.pi_b[1][1],p.pi_b[1][0]]], p.pi_c.slice(0,2)];
  assert.equal(await verifier.verifyProof(...points, bundle.publicSignals), true);
  report.validEvmProof = true;
  for (const index of [0,1,2,5,69]) {
    const changed = [...bundle.publicSignals];
    changed[index] = index === 1 ? (changed[1] === '0' ? '1' : '0') : (BigInt(changed[index]) + 1n).toString();
    assert.equal(await verifier.verifyProof(...points, changed), false);
    report.modifiedPublicSignalsRejected.push(index);
  }
  const changed = [...bundle.publicSignals]; changed[1] = changed[1] === '0' ? '1' : '0';
  const observationId = id('adaptive-negative-control:' + randomUUID());
  const recorded = await gateway.record({ observationId, patientRef: id('adaptive-negative-control'), observedAt: 1779158991,
    durationSeconds: 60, proof: bundle.proof, publicSignals: changed });
  assert.equal(recorded.commit.code, 0);
  // Confirm the reader is healthy before checking the rejection, so an outage cannot count as success.
  await reader.configuration();
  const metadata = await reader.metadata(observationId);
  assert.equal(metadata.observationId, observationId);
  await assert.rejects(reader.verify(observationId), error => /Invalid proof|verification failed/i.test(String(error) + JSON.stringify(error.details)));
  report.invalidFabricRecordRejectedOnRead = true;
  report.negativeControlTransaction = recorded.result.transactionId;
  writeFileSync(resolve(evidence, 'full-pool-negative-controls.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
} finally { provider.destroy(); gateway.close(); reader.close(); }
