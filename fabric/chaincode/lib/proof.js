'use strict';
const { AbiCoder, keccak256 } = require('ethers');
const FQ = 21888242871839275222246405745257275088696311157297823662689037894645226208583n;
const FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const decimal = (value, field) => typeof value === 'string' && /^(0|[1-9][0-9]{0,77})$/.test(value) && BigInt(value) < field;

function normalize(input) {
  if (!input || typeof input !== 'object') throw new Error('Invalid observation');
  for (const field of ['observationId', 'patientRef']) {
    if (!/^0x[0-9a-f]{64}$/.test(input[field]) || /^0x0+$/.test(input[field])) throw new Error('Invalid identifier');
  }
  if (!Number.isSafeInteger(input.observedAt) || input.observedAt <= 0 || !Number.isSafeInteger(input.durationSeconds)
      || input.durationSeconds < 1 || input.durationSeconds > 3600) throw new Error('Invalid capture time');
  const p = input.proof;
  if (!p || p.protocol !== 'groth16' || !['bn128', 'bn254'].includes(p.curve)) throw new Error('Only Groth16/BN254');
  if (![p.pi_a, p.pi_c].every(a => Array.isArray(a) && a.length === 3 && a.every(v => decimal(v, FQ)))
      || !Array.isArray(p.pi_b) || p.pi_b.length !== 3
      || !p.pi_b.every(row => Array.isArray(row) && row.length === 2 && row.every(v => decimal(v, FQ)))
      || p.pi_a[2] !== '1' || p.pi_c[2] !== '1' || p.pi_b[2][0] !== '1' || p.pi_b[2][1] !== '0'
      || !Array.isArray(input.publicSignals) || input.publicSignals.length !== 1
      || !input.publicSignals.every(v => decimal(v, FR)) || !['0', '1'].includes(input.publicSignals[0])) throw new Error('Invalid proof encoding');
  return { observationId: input.observationId, patientRef: input.patientRef, observedAt: input.observedAt,
    durationSeconds: input.durationSeconds, proof: {protocol: 'groth16', curve: 'bn128', pi_a: p.pi_a, pi_b: p.pi_b, pi_c: p.pi_c},
    publicSignals: input.publicSignals };
}

function proofDigest(input) {
  const {pi_a:a, pi_b:b, pi_c:c} = input.proof;
  // Identical digest to the EVM registry: snarkjs Fp2 -> Solidity order.
  return keccak256(AbiCoder.defaultAbiCoder().encode(['uint256[2]','uint256[2][2]','uint256[2]','uint256[1]'],
    [a.slice(0,2), [[b[0][1],b[0][0]],[b[1][1],b[1][0]]], c.slice(0,2), input.publicSignals]));
}
module.exports = { normalize, proofDigest };
