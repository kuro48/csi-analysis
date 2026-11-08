const assert = require("assert");
const { prepareInput, syntheticInput } = require("../scripts/adaptive_lomb_input.cjs");

describe("Adaptive Lomb input formatting (no external selection)", () => {
  it("preserves every column, order and sample and adds only canonical padding", () => {
    const raw = syntheticInput();
    raw.csiI = raw.csiI.map(row => row.slice(0, 53));
    raw.csiQ = raw.csiQ.map(row => row.slice(0, 53));
    const result = prepareInput(raw);
    assert.equal(result.candidateCount, 53);
    assert.ok(BigInt(result.commitmentNonce) > 0n);
    for (let i = 0; i < 64; i++) for (const name of ["csiI", "csiQ"]) {
      assert.deepEqual(result[name][i].slice(0, 53), raw[name][i]);
      assert.deepEqual(result[name][i].slice(53), Array(11).fill(2048));
    }
    assert.equal(raw.csiI[0].length, 53);
  });
  it("rejects too many columns instead of selecting a subset outside Circom", () => {
    const raw = syntheticInput();
    raw.csiI = raw.csiI.map(() => Array(4004).fill(2948));
    raw.csiQ = raw.csiQ.map(() => Array(4004).fill(2048));
    assert.throws(() => prepareInput(raw), /All 4004 columns/);
  });
  it("rejects inconsistent shapes/counts, unsafe numbers, invalid times and nonce", () => {
    const mutations = [
      x => { x.csiI[0].pop(); },
      x => { x.csiQ.pop(); },
      x => { x.csiQ[0][0] = 4096; },
      x => { x.csiI[0][0] = 1.5; },
      x => { x.candidateCount = 1; },
      x => { x.timestampsMs[2] = x.timestampsMs[1]; },
      x => { x.commitmentNonce = 123456789; },
      x => { x.commitmentNonce = "0"; },
    ];
    for (const mutate of mutations) {
      const raw = syntheticInput(); mutate(raw);
      assert.throws(() => prepareInput(raw));
    }
  });
});
