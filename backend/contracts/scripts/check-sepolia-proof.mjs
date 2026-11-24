// Validates a saved REAL-capture proof without any transaction or private key.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { groth16 } from 'snarkjs';
const root = resolve(import.meta.dirname, '../../..');
const evidence = resolve(root, 'docs/progress/2026-11-09-adaptive-4004');
const artifactsPath = process.env.ADAPTIVE_ARTIFACT_MANIFEST || resolve(root, '.local/circom-adaptive-4004/artifacts.json');
const artifacts = JSON.parse(readFileSync(artifactsPath));
const keyBytes = readFileSync(artifacts.files.verificationKey);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const bundleBytes = readFileSync(resolve(evidence, 'evm-proof-bundle.json'));
const bundle = JSON.parse(bundleBytes);
const metadata = JSON.parse(readFileSync(resolve(evidence, 'input-metadata.json')));
if (artifacts.circuit !== 'csi_lomb_scargle_adaptive_4004' || hash(keyBytes) !== artifacts.sha256.verificationKey ||
    bundle.publicSignals.length !== 70 || Number(bundle.publicSignals[69]) !== 4004 ||
    Number(bundle.publicSignals[68]) !== metadata.relativeDurationMs ||
    !(await groth16.verify(JSON.parse(keyBytes), bundle.publicSignals, bundle.proof))) throw Error('Real capture proof/key mismatch');
const report = {
  checkedAt: new Date().toISOString(), inputKind: 'saved-real-capture-proof',
  offlineProofValid: true, onchainVerified: false, newProofGenerated: false,
  publicSignalCount: 70, candidateCount: 4004,
  bundleSha256: hash(bundleBytes), verificationKeyHash: '0x' + hash(keyBytes),
  sourceCaptureSha256: metadata.sourceSha256,
  observedAt: Number(BigInt(metadata.captureStartUnixNs) / 1000000000n),
  durationSeconds: Math.ceil(metadata.relativeDurationMs / 1000),
};
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exit(0);
