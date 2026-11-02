// Each call produces distinct randomized real Groth16 proofs. No CSI acquisition is simulated.
import { groth16 } from "snarkjs";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { createHash } from "node:crypto";
const root = resolve(import.meta.dirname, "../..");
const output = resolve(process.argv[2] || ".local/fabric/fixtures.json");
const count = Number(process.argv[3] || 6);
if (!Number.isInteger(count) || count < 2 || count > 100)
  throw Error("Fixture count must be 2..100");
const key = resolve(
  process.env.FABRIC_VKEY ||
    `${root}/backend/contracts/build/onchain/csi_breathing_certificate.vkey.json`,
);
const vkey = JSON.parse(readFileSync(key));
const samples = [];
for (let i = 0; i < count; i++) {
  const wave = Array.from({ length: 300 }, (_, n) =>
    Math.round(80 * Math.sin((2 * Math.PI * (i % 2 ? 0.8 : 0.25) * n) / 5)),
  );
  const input = {
    vmdInput: wave,
    modes: [wave, ...Array.from({ length: 4 }, () => Array(300).fill(0))],
    sel: [1, 0, 0, 0, 0],
  };
  const start = performance.now();
  const result = await groth16.fullProve(
    input,
    `${root}/zkp/build/csi_breathing_certificate_js/csi_breathing_certificate.wasm`,
    `${root}/zkp/keys/csi_breathing_certificate_final.zkey`,
  );
  const proofGenerationMs = performance.now() - start;
  if (!(await groth16.verify(vkey, result.publicSignals, result.proof)))
    throw Error("Generated proof invalid");
  samples.push({ ...result, proofGenerationMs });
  console.log(`Generated fixture ${i + 1}/${count}`);
}
mkdirSync(dirname(output), { recursive: true });
writeFileSync(
  output,
  JSON.stringify(
    {
      version: 1,
      inputKind: "synthetic-signal",
      proofGenerationScope:
        "snarkjs fullProve (witness + prove); local validation excluded",
      debugMode: true,
      verificationKeyHash:
        "0x" + createHash("sha256").update(readFileSync(key)).digest("hex"),
      samples,
    },
    null,
    2,
  ),
);
process.exit(0); // snarkjs worker pool intentionally closed at CLI process boundary.
