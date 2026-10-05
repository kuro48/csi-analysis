# Hybrid Python/Circom implementation log

This file is intentionally formatted so each section can be captured as a
standalone screenshot for a progress report.

## Step 1 — Commitment specification

Implemented a versioned, domain-separated Poseidon chain for raw complex CSI
(C0) and quantized VMD input (C1). Signed values use explicit offsets, dimensions
and scale are absorbed as metadata, and matrices have a fixed flattening order.

Changed files:

- `backend/app/services/poseidon_commitment.py`
- `zkp/scripts/poseidon_commit.js`
- `research/phase2_authenticity/COMMITMENT_DESIGN.md`
- `zkp/package.json`
- `backend/entrypoint.sh`

Screenshot-ready usage:

```python
nonce = new_commitment_nonce()
c0 = commit_raw_csi(csi_matrix, nonce)
c1 = commit_vmd_input(vmd_input, nonce)
```

Verification:

```bash
cd backend
pytest tests/unit/test_poseidon_commitment.py
```

## Step 2 — C1-bound certificate circuit

Added `csi_breathing_certificate_committed` alongside the existing production
circuit. It range-checks the offset-encoded VMD input, recomputes C1 inside the
circuit, and enforces equality with the public commitment.

Changed files:

- `zkp/scripts/generate_breathing_certificate_committed_circuit.py`
- `zkp/circuits/csi_breathing_certificate_committed.circom`
- `backend/app/services/committed_breathing_certificate_service.py`
- `backend/app/api/endpoints/breathing.py`

Screenshot-ready constraint:

```circom
encodedVmdInput[i] <== vmdInput[i] + 1024;
commitmentStep[i].inputs[0] <== commitmentState[i];
commitmentStep[i].inputs[1] <== encodedVmdInput[i];
commitmentState[T] === vmdCommitment;
```

Run:

```bash
cd zkp
npm run generate:breathing_certificate_committed
npm run compile:breathing_certificate_committed
npm run setup:breathing_certificate_committed
```

## Step 3 — One-capture experiment records

Added an experiment service and `POST /api/v2/breathing/benchmark`. A single
capture is parsed once, then Python baseline, committed hybrid proof, reduced
preprocessing proof, and fixed-point Circom approximation are measured from the
same pipeline result.

Every request appends one full record to `results/runs.jsonl` and one row per
method to `results/method_runs.csv`. Records include source SHA-256, ground
truth, stage timings, accuracy errors, proof timings, constraint count, proof
size, and peak process RSS.

Screenshot-ready request:

```bash
curl -X POST http://localhost:8000/api/v2/breathing/benchmark \
  -F file=@capture.csi \
  -F dataset_id=subject-01-rest \
  -F ground_truth_bpm=15.0
```

## Step 4 — Batch comparison on real captures

Added a manifest-driven runner. It processes captures sequentially to avoid
mixing memory and proving-time measurements between simultaneous Groth16 jobs.
`--repeat` supports latency distributions while the source hash confirms every
method used the same capture.

```bash
cd backend
python3 scripts/run_hybrid_benchmark.py \
  ../research/phase2_authenticity/example_manifest.csv --repeat 3
```

## Step 5 — Accuracy and performance report

Added a dependency-free report generator. It calculates MAE, RMSE, ±1/±2 BPM
accuracy, and median end-to-end latency. It writes both a Markdown table and an
SVG designed for direct screenshots.

```bash
python3 research/phase2_authenticity/generate_report.py
open research/phase2_authenticity/results/comparison.svg
```

## Step 6 — Incremental preprocessing proof

Added a reduced fixed-point PCA projection circuit. It commits to a 32x8 matrix
and eight component weights, proves every output dot product exactly, and emits
a Poseidon commitment to the projected vector. The witness selects the eight
largest-magnitude PCA loadings and reports correlation with the full Python PCA
projection, so accuracy/cost can determine whether to expand the circuit.

```circom
for (var t = 0; t < T; t++) {
    projectionTerm[t][0] <== centeredX[t][0] * weights[0];
    projectionPartial[t][0] <== projectionTerm[t][0];
    for (var n = 1; n < N; n++) {
        projectionTerm[t][n] <== centeredX[t][n] * weights[n];
        projectionPartial[t][n] <== projectionPartial[t][n-1] + projectionTerm[t][n];
    }
    projected[t] <== projectionPartial[t][N-1];
}
```

Explicit limitation: this stage proves the reduced quantized projection, not
SNR selection, filtering, or that the supplied component is the maximum
eigenvector. Those remain the next possible circuit-expansion boundaries.

## Verification snapshot

Both new circuits were compiled and exercised through real Groth16 witness,
proof, and local verification—not only mocked service tests.

| Circuit | Constraints | Private inputs | Public inputs | Outputs | Proof verified |
|---|---:|---:|---:|---:|---|
| `csi_breathing_certificate_committed` | 171,993 | 1,806 | 1 | 1 | yes |
| `csi_preprocess_projection` | 161,400 | 265 | 1 | 1 | yes |

A deliberately changed public C1 was rejected during witness generation. The
matching C1 generated and verified a Groth16 proof, and the private nonce was
absent from the returned metadata.

```bash
cd zkp
npm run compile:breathing_certificate_committed
npm run compile:preprocess_projection
snarkjs r1cs info build/csi_breathing_certificate_committed.r1cs
snarkjs r1cs info build/csi_preprocess_projection.r1cs
```

Backend regression snapshot: all 122 unit tests passed in Docker. The
container's auto-loaded Web3 pytest plugin has an unrelated `eth_typing`
version conflict, so the reproducible invocation disables third-party plugin
autoload and clears coverage arguments:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p pytest_asyncio.plugin \
  -o addopts='' tests/unit
```
