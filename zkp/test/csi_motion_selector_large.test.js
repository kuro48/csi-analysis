const assert = require("assert");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");
const wasmTester = require("circom_tester").wasm;

describe("CSIMotionSelector grouped waveform sums", function () {
  this.timeout(180000);
  it("selects the last candidate across full and partial 16-column groups", async () => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "csi-selector-large-"));
    try {
      const source = path.join(dir, "large.circom");
      await fs.writeFile(source, 'pragma circom 2.0.0;\ninclude "csi_motion_selector.circom";\ncomponent main = CSIMotionSelector(8, 65);\n');
      const circuit = await wasmTester(source, { include: [path.join(__dirname, "../circuits"), path.join(__dirname, "../node_modules")] });
      const motion = [800, 850, 900, 950, 1000, 950, 900, 850];
      const data = {
        csiI: motion.map(x => [...Array(64).fill(2948), x + 2048]),
        csiQ: motion.map(() => Array(65).fill(2048)), candidateCount: 65, commitmentNonce: "12345",
      };
      const witness = await circuit.calculateWitness(data, true);
      assert.equal(Number(witness[2]), 64);
      await circuit.assertOut(witness, { selectedI: motion.map(x => x + 2048), selectedQ: Array(8).fill(2048) });
      await circuit.checkConstraints(witness);
    } finally { await fs.rm(dir, { recursive: true, force: true }); }
  });
});
