#!/usr/bin/env node
const { randomBytes } = require("node:crypto");
const { spawnSync } = require("node:child_process");

function run(args, input) {
  const result = spawnSync("npx", ["snarkjs", ...args], {
    cwd: require("node:path").resolve(__dirname, ".."),
    stdio: [input == null ? "inherit" : "pipe", "inherit", "inherit"],
    input,
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run([
  "groth16", "setup", "build/csi_vmd_approx.r1cs",
  "keys/powersOfTau28_hez_final_19.ptau",
  "keys/csi_vmd_approx_0000.zkey",
]);
run([
  "zkey", "contribute", "keys/csi_vmd_approx_0000.zkey",
  "keys/csi_vmd_approx_final.zkey", "--name=VMD approximation contribution", "-v",
], `${randomBytes(64).toString("hex")}\n`);
run([
  "zkey", "export", "verificationkey", "keys/csi_vmd_approx_final.zkey",
  "keys/csi_vmd_approx_verification_key.json",
]);
