// Worker entrypoint: uses pinned deployed artifacts, never runs trusted setup.
const fs = require("fs");
const path = require("path");
const { createHash } = require("crypto");
const { spawnSync } = require("child_process");
const snarkjs = require("snarkjs");
const { performance } = require("perf_hooks");

async function main() {
  const [manifestPath, inputPath, outputPath] = process.argv.slice(2);
  if (!outputPath) throw Error("Usage: prove_adaptive_capture.cjs artifacts.json input.json bundle.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath));
  const started = performance.now();
  if (manifest.circuit !== "csi_lomb_scargle_adaptive_4004" || manifest.capacity !== 4004 || manifest.publicSignalCount !== 70) {
    throw Error("Unsupported adaptive artifacts");
  }
  const native = manifest.prover === "arkworks-0.5";
  if (manifest.prover && !native && manifest.prover !== "snarkjs") throw Error("Unsupported prover");
  for (const name of native ? ["wasm", "provingKey", "verificationKey", "r1cs", "prover"] : ["wasm", "zkey", "verificationKey"]) {
    const hash = createHash("sha256");
    for await (const chunk of fs.createReadStream(manifest.files[name])) hash.update(chunk);
    if (hash.digest("hex") !== manifest.sha256[name]) throw Error(`Artifact hash mismatch: ${name}`);
  }
  const key = JSON.parse(fs.readFileSync(manifest.files.verificationKey));
  const witness = path.join(path.dirname(outputPath), "witness.wtns");
  const generator = path.join(path.dirname(manifest.files.wasm), "generate_witness.js");
  const witnessStart = performance.now();
  const generated = spawnSync(process.execPath, [generator, manifest.files.wasm, inputPath, witness], { stdio: "inherit" });
  if (generated.error || generated.status !== 0) throw Error("Adaptive witness failed");
  const proveStart = performance.now();
  let proof, publicSignals;
  if (native) {
    const nativeOutput = path.join(path.dirname(outputPath), "native-bundle.json");
    const result = spawnSync(manifest.files.prover, ["prove", manifest.files.r1cs, manifest.files.provingKey, witness, nativeOutput], { stdio: "inherit" });
    if (result.error || result.status !== 0) throw Error("Native adaptive proof failed");
    ({ proof, publicSignals } = JSON.parse(fs.readFileSync(nativeOutput)));
  } else {
    ({ proof, publicSignals } = await snarkjs.groth16.prove(manifest.files.zkey, witness));
  }
  const verifyStart = performance.now();
  if (publicSignals.length !== 70 || !await snarkjs.groth16.verify(key, publicSignals, proof)) throw Error("Adaptive verification failed");
  const finished = performance.now();
  const metrics = {
    artifactCheckMs: witnessStart - started, witnessMs: proveStart - witnessStart,
    proveMs: verifyStart - proveStart, verifyMs: finished - verifyStart, totalProverMs: finished - started,
  };
  fs.writeFileSync(outputPath, JSON.stringify({ proof, publicSignals, metrics }), { mode: 0o600 });
}
main().then(() => process.exit(0)).catch(error => { console.error(error.message); process.exit(1); });
