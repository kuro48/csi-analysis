const assert = require("assert");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");
const wasmTester = require("circom_tester").wasm;
const { buildPoseidon } = require("circomlibjs");

// Independent integer reference, used only as a test oracle. Production
// inputs contain neither scores nor a claimed selection.
function score(values) {
  const p = values.map(([i, q]) => BigInt(i - 2048) ** 2n + BigInt(q - 2048) ** 2n);
  const n = BigInt(p.length);
  const s = p.reduce((a, b) => a + b, 0n);
  const v = n * p.reduce((a, b) => a + b * b, 0n) - s * s;
  const d = p.slice(1).reduce((a, b, i) => a + (b - p[i]) ** 2n, 0n);
  const eligible = s >= n * 16n && v > 0n && v <= s * s;
  return [eligible ? v * v : 0n, (s * s + 1n) * (v + n * d + 1n)];
}

describe("CSIMotionSelector: constrained ranking and complete-pool commitment", function () {
  this.timeout(180000);
  let circuit, dir, poseidon;
  before(async () => {
    dir = await fs.mkdtemp(path.join(os.tmpdir(), "csi-selector-"));
    const src = path.join(dir, "selector.circom");
    await fs.writeFile(src, 'pragma circom 2.0.0;\ninclude "csi_motion_selector.circom";\ncomponent main {public [candidateCount]} = CSIMotionSelector(8, 4);\n');
    circuit = await wasmTester(src, {
      include: [path.join(__dirname, "../circuits"), path.join(__dirname, "../node_modules")],
    });
    poseidon = await buildPoseidon();
  });
  after(async () => { if (dir) await fs.rm(dir, { recursive: true, force: true }); });

  function input(columns, candidateCount = columns.length) {
    return {
      csiI: Array.from({ length: 8 }, (_, i) => Array.from({ length: 4 }, (_, sc) => 2048 + (columns[sc]?.[i] ?? 0))),
      csiQ: Array.from({ length: 8 }, () => Array(4).fill(2048)),
      candidateCount, commitmentNonce: "987654321",
    };
  }
  const motion = [800, 850, 900, 950, 1000, 950, 900, 850];
  const flat = Array(8).fill(900);

  it("selects motion instead of a constant, sparse spike or padded column", async () => {
    const data = input([flat, [0, 0, 0, 1800, 0, 0, 0, 0], motion]);
    const w = await circuit.calculateWitness(data, true);
    assert.equal(Number(w[2]), 2);
    await circuit.assertOut(w, { selectedI: motion.map(x => x + 2048), selectedQ: Array(8).fill(2048) });
    await circuit.checkConstraints(w);
  });

  it("uses the first index for equal scores", async () => {
    const w = await circuit.calculateWitness(input([motion, motion]), true);
    assert.equal(Number(w[2]), 0);
  });

  it("handles signed endpoints and motion present only in Q", async () => {
    const data = input([Array(8).fill(-2048), Array(8).fill(2047), flat, Array(8).fill(0)]);
    const q = [-2048, -1900, -1700, -1500, 1500, 1700, 1900, 2047];
    for (let i = 0; i < 8; i++) data.csiQ[i][3] = q[i] + 2048;
    const w = await circuit.calculateWitness(data, true);
    assert.equal(Number(w[2]), 3);
    await circuit.checkConstraints(w);
  });

  it("penalizes rapid fluctuations when the power distribution is identical", async () => {
    const smooth = [800, 800, 800, 800, 1000, 1000, 1000, 1000];
    const jagged = [800, 1000, 800, 1000, 800, 1000, 800, 1000];
    const w = await circuit.calculateWitness(input([jagged, smooth]), true);
    assert.equal(Number(w[2]), 1);
  });

  it("matches exact rational comparisons for varied I/Q inputs", async () => {
    let seed = 42;
    const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed; };
    for (let trial = 0; trial < 25; trial++) {
      const data = input([motion, motion, motion, motion]);
      data.csiI = data.csiI.map(row => row.map(() => 2048 + 500 + random() % 1000));
      data.csiQ = data.csiQ.map(row => row.map(() => 2048 - 300 + random() % 600));
      const scores = Array.from({ length: 4 }, (_, sc) => score(data.csiI.map((row, i) => [row[sc], data.csiQ[i][sc]])));
      let best = 0;
      for (let sc = 1; sc < 4; sc++) {
        if (scores[sc][0] * scores[best][1] > scores[best][0] * scores[sc][1]) best = sc;
      }
      const w = await circuit.calculateWitness(data, true);
      assert.equal(Number(w[2]), best, `trial ${trial}`);
      if (trial === 24) await circuit.checkConstraints(w);
    }
  });

  it("rejects missing eligible data, invalid count, padding, nonce and I/Q range", async () => {
    for (const columns of [[flat], [[1, 2, 1, 2, 1, 2, 1, 2]], [[0, 0, 0, 1800, 0, 0, 0, 0]]]) {
      await assert.rejects(() => circuit.calculateWitness(input(columns), true));
    }
    for (const candidateCount of [0, 5, -1]) {
      await assert.rejects(() => circuit.calculateWitness(input([motion], candidateCount), true));
    }
    const badPadding = input([motion]); badPadding.csiI[0][3] = 2049;
    const badRange = input([motion]); badRange.csiQ[2][0] = 4096;
    const negative = input([motion]); negative.csiI[2][0] = -1;
    const zeroNonce = input([motion]); zeroNonce.commitmentNonce = "0";
    for (const data of [badPadding, badRange, negative, zeroNonce]) {
      await assert.rejects(() => circuit.calculateWitness(data, true));
    }
  });

  it("binds all columns, shape, count and nonce with documented packing", async () => {
    const data = input([motion, flat]);
    const hash = xs => poseidon.F.toObject(poseidon(xs));
    let state = hash([2026110901n, 8n, 4n, 2n, BigInt(data.commitmentNonce)]);
    const pairs = data.csiI.flatMap((row, i) => row.map((x, sc) => BigInt(x) + 4096n * BigInt(data.csiQ[i][sc])));
    const packs = [];
    for (let j = 0; j < pairs.length; j += 10) {
      packs.push(pairs.slice(j, j + 10).reduce((a, b, k) => a + (b << BigInt(k * 24)), 0n));
    }
    while (packs.length % 15) packs.push(0n);
    for (let j = 0; j < packs.length; j += 15) state = hash([state, ...packs.slice(j, j + 15)]);
    const w = await circuit.calculateWitness(data, true);
    assert.equal(w[1].toString(), state.toString());
    const variants = [structuredClone(data), structuredClone(data), structuredClone(data)];
    variants[0].csiI[0][1]++;
    variants[1].commitmentNonce = "987654322";
    variants[2].candidateCount = 3;
    for (const variant of variants) {
      const changed = await circuit.calculateWitness(variant, true);
      assert.equal(Number(changed[2]), 0);
      assert.notEqual(changed[1].toString(), w[1].toString());
    }
  });

  it("rejects a forged winner, score or selected waveform in the R1CS", async () => {
    const w = await circuit.calculateWitness(input([flat, motion]), true);
    await circuit.loadSymbols();
    for (const name of ["main.selectedSubcarrier", "main.numerator[0]", "main.selectedI[0]"]) {
      const forged = w.slice();
      const index = circuit.symbols[name].varIdx;
      assert.ok(index > 0, name);
      forged[index] += 1n;
      await assert.rejects(() => circuit.checkConstraints(forged), undefined, name);
    }
  });
});
