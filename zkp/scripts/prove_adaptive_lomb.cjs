// Standalone experimental proof runner; never updates deployed keys/verifiers.
const fs = require("fs");
const path = require("path");
const { randomBytes, createHash } = require("crypto");
const { spawnSync } = require("child_process");
const { performance } = require("perf_hooks");
const snarkjs = require("snarkjs");
const { prepareInput, syntheticInput } = require("./adaptive_lomb_input.cjs");

async function main() {
  const args = process.argv.slice(2);
  const options = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!["--build", "--ptau", "--input"].includes(args[i]) || !args[i + 1]) {
      throw Error("Usage: node scripts/prove_adaptive_lomb.cjs --build DIR --ptau FILE [--input unpadded-encoded-csi.json]");
    }
    options[args[i]] = path.resolve(args[i + 1]);
  }
  if (!options["--build"] || !options["--ptau"]) throw Error("--build and --ptau are required; see docs/circom-adaptive-selection.md");
  const build = options["--build"];
  const base = "csi_lomb_scargle_adaptive";
  const r1cs = path.join(build, `${base}.r1cs`);
  const wasmDir = path.join(build, `${base}_js`);
  for (const file of [r1cs, path.join(wasmDir, `${base}.wasm`), options["--ptau"]]) {
    if (!fs.existsSync(file)) throw Error(`Missing ${file}; compile the 64-candidate circuit first`);
  }
  const runDir = fs.mkdtempSync(path.join(build, "proof-run-"));
  const file = name => path.join(runDir, name);
  const raw = options["--input"] ? JSON.parse(fs.readFileSync(options["--input"], "utf8")) : syntheticInput();
  const input = prepareInput(raw, 64);
  fs.writeFileSync(file("input.json"), JSON.stringify(input), { mode: 0o600 });
  const timings = {};
  async function timed(name, task) {
    const start = performance.now();
    const result = await task();
    timings[name] = Number(((performance.now() - start) / 1000).toFixed(3));
    console.log(`${name}: ${timings[name]} s`);
    return result;
  }
  await timed("witness", async () => {
    const result = spawnSync(process.execPath, [path.join(wasmDir, "generate_witness.js"),
      path.join(wasmDir, `${base}.wasm`), file("input.json"), file("witness.wtns")], { stdio: "inherit" });
    if (result.error || result.status !== 0) throw Error("Witness generation failed");
    fs.chmodSync(file("witness.wtns"), 0o600);
  });
  await timed("witness_check", async () => {
    if (!await snarkjs.wtns.check(r1cs, file("witness.wtns"))) throw Error("R1CS check failed");
  });
  await timed("setup", () => snarkjs.zKey.newZKey(r1cs, options["--ptau"], file("initial.zkey")));
  // Fresh local contribution for experimentation, never fixed demo entropy.
  await timed("contribution", () => snarkjs.zKey.contribute(file("initial.zkey"), file("final.zkey"),
    "adaptive-lomb-local-experiment", randomBytes(64).toString("hex")));
  const vkey = await snarkjs.zKey.exportVerificationKey(file("final.zkey"));
  const { proof, publicSignals } = await timed("prove", () => snarkjs.groth16.prove(file("final.zkey"), file("witness.wtns")));
  if (publicSignals.length !== 70) throw Error(`Unexpected protocol: ${publicSignals.length} public signals`);
  const valid = await timed("verify", () => snarkjs.groth16.verify(vkey, publicSignals, proof));
  if (!valid) throw Error("Groth16 verification failed");
  const tamperChecks = {};
  for (const [name, index] of [["commitment", 0], ["isNormal", 1], ["selectedSubcarrier", 2],
    ["timestamp", 6], ["candidateCount", 69]]) {
    const changed = [...publicSignals];
    changed[index] = (BigInt(changed[index]) + 1n).toString();
    tamperChecks[name] = !await snarkjs.groth16.verify(vkey, changed, proof);
    if (!tamperChecks[name]) throw Error(`Tampered ${name} was accepted`);
  }
  const info = await snarkjs.r1cs.info(r1cs);
  const report = {
    circuitId: "csi-lomb-scargle-adaptive-64-v1-experimental",
    data: options["--input"] ? "provided-encoded-csi" : "synthetic-64-candidates-0.25Hz-index13",
    constraints: info.nConstraints, wires: info.nVars, publicSignalCount: publicSignals.length,
    r1csSha256: createHash("sha256").update(fs.readFileSync(r1cs)).digest("hex"),
    verificationPassed: valid, tamperChecks, timingsSeconds: timings,
    result: { isNormal: Number(publicSignals[1]), selectedSubcarrier: Number(publicSignals[2]),
      estimatedFrequencyBin: Number(publicSignals[3]), globalPeakFrequencyBin: Number(publicSignals[4]),
      candidateCount: Number(publicSignals[69]) },
    deployed: false,
  };
  for (const [name, value] of [["verification_key.json", vkey], ["proof.json", proof],
    ["public.json", publicSignals], ["report.json", report]]) {
    fs.writeFileSync(file(name), JSON.stringify(value, null, 2) + "\n", { mode: 0o600 });
  }
  console.log(JSON.stringify(report, null, 2));
  console.log(`Artifacts: ${runDir}`);
}

main().then(() => process.exit(0)).catch(error => { console.error(error.message); process.exit(1); });
