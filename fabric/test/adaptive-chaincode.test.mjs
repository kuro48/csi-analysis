import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash, X509Certificate } from 'node:crypto';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Observations = require('../chaincode/lib/observations.js');
const { normalize, protocol } = require('../chaincode/lib/proof.js');
const snarkjs = createRequire(require.resolve('../chaincode/lib/observations.js'))('snarkjs');
const cert = readFileSync(new URL('recorder-certificate.txt', import.meta.url));
const evidence = new URL('../../docs/progress/2026-11-09-circom-adaptive/', import.meta.url);
const key = readFileSync(new URL('verification_key.json', evidence));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const config = {
  circuit: 'csi_lomb_scargle_adaptive_4004', publicSignalCount: 70, isNormalIndex: 1,
  channelName: 'csi', readerMspIds: ['Org1MSP', 'Org2MSP'], recorderMspId: 'Org1MSP',
  recorderCertificateHash: hash(new X509Certificate(cert).raw), verificationKeyHash: hash(key),
  deploymentId: 'compact-fixture-protocol-test', debugMode: true,
};
const payload = {
  observationId: '0x' + '1'.repeat(64), patientRef: '0x' + '2'.repeat(64), observedAt: 1, durationSeconds: 60,
  proof: JSON.parse(readFileSync(new URL('proof.json', evidence))),
  publicSignals: JSON.parse(readFileSync(new URL('public.json', evidence))),
};
function context() {
  const state = new Map();
  return {
    clientIdentity: { getMSPID: () => 'Org1MSP', getIDBytes: () => cert },
    stub: {
      getChannelID: () => 'csi', getTxTimestamp: () => ({ seconds: 100 }), getTxID: () => 'a'.repeat(64),
      createCompositeKey: (kind, args) => kind + args.join(':'),
      getState: async key => state.get(key) || Buffer.alloc(0),
      putState: async (key, value) => state.set(key, value), setEvent: () => {},
    },
  };
}
test('70-signal protocol verifies a real compact fixture only on read', async () => {
  const contract = new Observations(config, key);
  const ctx = context();
  const result = JSON.parse(await contract.RecordObservation(ctx, JSON.stringify(payload)));
  assert.equal('isNormal' in result, false);
  assert.equal('publicSignals' in JSON.parse(await contract.ReadObservation(ctx, payload.observationId)), false);
  const verified = JSON.parse(await contract.VerifyObservation(ctx, payload.observationId));
  assert.equal(verified.isNormal, payload.publicSignals[1] === '1');
  for (const index of [0, 1, 2, 6, 69]) {
    const changed = structuredClone(payload);
    changed.observationId = '0x' + String(index + 3).padStart(64, '0');
    changed.publicSignals[index] = index === 1 ? '0' : (BigInt(changed.publicSignals[index]) + 1n).toString();
    await contract.RecordObservation(ctx, JSON.stringify(changed));
    await assert.rejects(contract.VerifyObservation(ctx, changed.observationId), /Invalid proof/);
  }
});
test('wrong public shape and candidate count fail before storage', () => {
  assert.throws(() => normalize(payload), /encoding/);
  assert.throws(() => protocol({ ...config, isNormalIndex: 0 }), /Unsupported/);
  for (const count of ['0', '4005']) {
    const changed = structuredClone(payload); changed.publicSignals[69] = count;
    assert.throws(() => normalize(changed, config), /candidate count/);
  }
});
after(async () => { const curve = await snarkjs.curves.getCurveFromName('bn128'); await curve.terminate(); });
