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
    if (!["--build", "--ptau", "--input", "--capacity", "--stage"].includes(args[i]) || !args[i + 1]) {
      throw Error("Usage: node scripts/prove_adaptive_lomb.cjs --build DIR --ptau FILE [--input unpadded-encoded-csi.json]");
    }
    options[args[i]] = args[i] === "--capacity" ? Number(args[i + 1]) : args[i] === "--stage" ? args[i + 1] : path.resolve(args[i + 1]);
  }
  if (!options["--build"] || !options["--ptau"]) throw Error("--build and --ptau are required; see docs/circom-adaptive-selection.md");
  if (options["--stage"] && options["--stage"] !== "setup") throw Error("Only --stage setup is supported");
  const build = options["--build"];
  const capacity = options["--capacity"] || 64;
  if (![64, 4004].includes(capacity)) throw Error("Supported capacities: 64, 4004");
  const base = capacity === 64 ? "csi_lomb_scargle_adaptive" : "csi_lomb_scargle_adaptive_4004";
  const r1cs = path.join(build, `${base}.r1cs`);
  const wasmDir = path.join(build, `${base}_js`);
  for (const file of [r1cs, path.join(wasmDir, `${base}.wasm`), options["--ptau"]]) {
    if (!fs.existsSync(file)) throw Error(`Missing ${file}; compile the matching circuit first`);
  }
  const runDir = fs.mkdtempSync(path.join(build, "proof-run-"));
  const file = name => path.join(runDir, name);
  console.log(`Artifacts: ${runDir}`);
  const raw = options["--input"] ? JSON.parse(fs.readFileSync(options["--input"], "utf8")) : syntheticInput();
  const input = prepareInput(raw, capacity);
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
  fs.writeFileSync(file("verification_key.json"), JSON.stringify(vkey, null, 2) + "\n");
  async function sha256(filename) {
    const hash = createHash("sha256");
    for await (const chunk of fs.createReadStream(filename)) hash.update(chunk);
    return hash.digest("hex");
  }
  const artifactFiles = { wasm: path.join(wasmDir, `${base}.wasm`), zkey: file("final.zkey"),
    verificationKey: file("verification_key.json"), r1cs };
  const hashes = {};
  for (const [name, filename] of Object.entries(artifactFiles)) hashes[name] = await sha256(filename);
  fs.writeFileSync(file("artifacts.json"), JSON.stringify({ version: 1, circuit: base,
    capacity, sampleCount: 64, publicSignalCount: 70, isNormalIndex: 1,
    files: artifactFiles, sha256: hashes }, null, 2) + "\n");
  if (options["--stage"] === "setup") {
    fs.writeFileSync(file("setup-timings.json"), JSON.stringify(timings, null, 2) + "\n");
    console.log(`Setup complete: ${file("artifacts.json")}`);
    return;
  }
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
    circuitId: `csi-lomb-scargle-adaptive-${capacity}-v1-experimental`,
    data: options["--input"] ? "provided-encoded-csi" : "synthetic-64-candidates-0.25Hz-index13",
    constraints: info.nConstraints, wires: info.nVars, publicSignalCount: publicSignals.length,
    r1csSha256: hashes.r1cs,
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
