import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { protocol, normalize } = require('../chaincode/lib/proof.js');
const real = JSON.parse(readFileSync(new URL('../../docs/progress/2026-11-09-adaptive-4004/evm-proof-bundle.json', import.meta.url)));
const config = n => ({ experiment: 'sample-count-v1', sampleCount: n, capacity: 4004,
  publicSignalCount: n+6, isNormalIndex: 1, circuit: `csi_lomb_scargle_adaptive_n${n}_c4004` });

test('sample-count protocols require exact explicit shape and experiment tag', () => {
  for (const n of [64,96,128]) assert.deepEqual(protocol(config(n)), {count:n+6,index:1});
  for (const changed of [ {experiment:undefined}, {sampleCount:256}, {capacity:53}, {publicSignalCount:70},
    {isNormalIndex:0}, {circuit:'csi_lomb_scargle_adaptive_n128_c4004'},
    {publicSignalCount:1,isNormalIndex:0},
    {publicSignalCount:70,circuit:'csi_lomb_scargle_adaptive_4004'} ]) {
    assert.throws(() => protocol({...config(96),...changed}), /Unsupported/);
  }
});

test('real 64-point proof cannot be reinterpreted as a 96-point proof', () => {
  const input = { observationId:'0x'+'12'.repeat(32), patientRef:'0x'+'34'.repeat(32),
    observedAt:1779158991,durationSeconds:54,proof:real.proof,publicSignals:real.publicSignals };
  assert.equal(normalize(input, config(64)).publicSignals.length,70);
  assert.throws(() => normalize(input, config(96)), /Invalid proof encoding/);
  const changed = structuredClone(input); changed.publicSignals[69]='4005';
  assert.throws(() => normalize(changed, config(64)), /Invalid candidate count/);
});
