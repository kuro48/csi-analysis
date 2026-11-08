const path = require("path");
const assert = require("assert");
const wasmTester = require("circom_tester").wasm;

// Synthetic input only: no external candidate scoring or selection.
function makeInput(frequency = 0.25, winner = 13) {
  const times = Array.from({ length: 64 }, (_, i) => Math.round((i * 0.94 + 0.035 * Math.sin(i * 0.73)) * 1000));
  return {
    csiI: times.map(t => Array.from({ length: 64 }, (_, sc) => 2048 + Math.round(
      sc === winner ? 900 + 150 * Math.sin(2 * Math.PI * frequency * t / 1000) : 900,
    ))),
    csiQ: times.map(() => Array(64).fill(2048)),
    timestampsMs: times, candidateCount: 64, commitmentNonce: "12345678901234567890",
  };
}

describe("LombScargleCSIAdaptive: selection through classification", function () {
  this.timeout(3600000);
  let circuit;
  before(async () => {
    circuit = await wasmTester(path.join(__dirname, "../circuits/csi_lomb_scargle_adaptive.circom"), {
      include: [path.join(__dirname, "../node_modules")],
      ...(process.env.ADAPTIVE_BUILD_DIR ? { output: path.resolve(process.env.ADAPTIVE_BUILD_DIR) } : {}),
    });
  });
  it("finds a carrier omitted by evenly spaced eight-column sampling and classifies its peak", async () => {
    const w = await circuit.calculateWitness(makeInput(), true);
    assert.equal(Number(w[3]), 13);
    assert.equal(Number(w[2]), 1);
    assert.ok(Math.abs(Number(w[5]) - Math.round((0.25 - 0.05) / (29 / 2540))) <= 1);
    await circuit.checkConstraints(w);
  });
  it("keeps an out-of-band winner instead of searching for a normal result", async () => {
    const w = await circuit.calculateWitness(makeInput(0.39, 63), true);
    assert.equal(Number(w[3]), 63);
    assert.equal(Number(w[2]), 0);
    assert.ok(Number(w[5]) > 27);
  });
  it("supports a full 53-column pool with constrained zero padding", async () => {
    const data = makeInput(0.25, 52);
    data.candidateCount = 53;
    for (let i = 0; i < 64; i++) for (let sc = 53; sc < 64; sc++) data.csiI[i][sc] = 2048;
    const w = await circuit.calculateWitness(data, true);
    assert.equal(Number(w[3]), 52);
    assert.equal(Number(w[2]), 1);
  });
  it("rejects a non-increasing public time axis", async () => {
    const data = makeInput(); data.timestampsMs[20] = data.timestampsMs[19];
    await assert.rejects(() => circuit.calculateWitness(data, true));
  });
});
