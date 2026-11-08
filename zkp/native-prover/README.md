# Circom R1CS native Groth16 prover

The selection algorithm and Lomb–Scargle computation remain inside Circom. This adapter reads the compiled BN254 R1CS and Circom witness; it does not rank CSI columns or replace the circuit's arithmetic. It uses [arkworks Groth16 0.5.0](https://github.com/arkworks-rs/groth16/tree/v0.5.0) for setup, proving and local verification. Standard snarkjs JSON output is independently verified by the existing snarkjs verifier and consumed by EVM/Fabric.

```bash
mkdir -p .local/circom-adaptive-4004/build
circom zkp/circuits/csi_lomb_scargle_adaptive_4004.circom --r1cs --wasm --sym --O1 \
  -l zkp/node_modules -o .local/circom-adaptive-4004/build
cargo build --release --locked --manifest-path zkp/native-prover/Cargo.toml
cargo test --release --locked --manifest-path zkp/native-prover/Cargo.toml
node zkp/scripts/setup_adaptive_native.cjs .local/circom-adaptive-4004
node zkp/scripts/prove_adaptive_capture.cjs \
  .local/circom-adaptive-4004/artifacts.json input.json bundle.json
```

Compile the 4,004-candidate circuit into `WORK/build` before setup. Setup refuses to overwrite an existing key/manifest. Preserve the complete artifact directory and use the exact verification key when deploying either ledger. The worker checks SHA256 of the WASM, R1CS, native executable, proving key and verification key for every job. Rebuilding a binary or changing any artifact requires a new reviewed manifest; do not silently update a deployed circuit's key.

**This fallback performs a single-party testnet trusted setup using OS randomness. It does not use the downloaded Powers of Tau ceremony and must not be described as a multiparty setup.** No toxic waste is written to disk by this tool. A production deployment requires an appropriate independently reviewed setup/prover pipeline and new verifier deployments. The older snarkjs ceremony path remains available.

R1CS/witness parsers reject wrong field moduli, versions, section lengths, noncanonical scalars and invalid wire indices. Before proving, every original constraint is evaluated against the supplied witness. Uncompressed keys avoid point decompression overhead, but arkworks still validates group membership on loading. The native proof is checked locally by arkworks and then independently by snarkjs in the worker. `OptimizationGoal::None` preserves the compiled R1CS without reoptimizing it.

Resource limits matter: this circuit has 14,530,543 constraints. The initial snarkjs setup hit a 12 GiB V8 heap limit (about 25.7 GB process peak). Native runtime measurements and end-to-end status are recorded separately in the progress report. Compact-fixture interoperability tests do not establish that a 4,004-candidate proof has been generated or deployed.
