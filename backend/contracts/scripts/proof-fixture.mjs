// Synthetic signal, REAL Groth16 proof. Never described as a real CSI measurement.
import { groth16 } from 'snarkjs';
import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import { root } from './build.mjs';

const wave = Array.from({ length: 300 }, (_, i) => Math.round(80 * Math.sin(2 * Math.PI * .25 * i / 5)));
const result = await groth16.fullProve({ vmdInput: wave, modes: [wave, ...Array.from({ length: 4 }, () => Array(300).fill(0))], sel: [1, 0, 0, 0, 0] },
  resolve(root, '../../zkp/build/csi_breathing_certificate_js/csi_breathing_certificate.wasm'),
  resolve(root, '../../zkp/keys/csi_breathing_certificate_final.zkey'));
const bundle = { circuit: 'csi_breathing_certificate', ...result };
writeFileSync(resolve(root, 'build/onchain/synthetic-proof.json'), JSON.stringify(bundle, null, 2));
console.log('Generated real Groth16 proof from a synthetic 0.25 Hz signal.');
process.exit(0);
