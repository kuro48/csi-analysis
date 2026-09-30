const path = require("path");
const assert = require("assert");
const wasmTester = require("circom_tester").wasm;

describe("LombScargleCSIEndToEnd", function () {
  this.timeout(3600000);

  let circuit;

  before(async () => {
    circuit = await wasmTester(
      path.join(__dirname, "..", "circuits", "csi_lomb_scargle_end_to_end.circom"),
      { include: [path.join(__dirname, "..", "node_modules")] },
    );
  });

  const sampleCount = 64;
  const subcarriers = 8;
  const csiOffset = 2048;
  const frequencyMin = 0.05;
  const frequencyStep = 29 / 2540;

  function makeInput(frequencies) {
    const times = Array.from({ length: sampleCount }, (_, index) =>
      index * 0.94 + 0.035 * Math.sin(index * 0.73),
    );
    const csiI = times.map((time, sampleIndex) =>
      Array.from({ length: subcarriers }, (_, subcarrier) => {
        const frequency = frequencies[subcarrier];
        const amplitude = subcarrier === 0 ? 150 : 80;
        const phase = subcarrier * 0.37;
        const rawI = Math.round(900 + amplitude * Math.sin(2 * Math.PI * frequency * time + phase));
        return rawI + csiOffset;
      }),
    );
    const csiQ = times.map((time) =>
      Array.from({ length: subcarriers }, (_, subcarrier) => {
        const frequency = frequencies[subcarrier];
        const rawQ = Math.round(40 * Math.sin(2 * Math.PI * frequency * time + 0.21 * subcarrier));
        return rawQ + csiOffset;
      }),
    );

    return {
      csiI,
      csiQ,
      commitmentNonce: "12345678901234567890",
      timestampsMs: times.map((time) => Math.round((time - times[0]) * 1000)),
    };
  }

  it("estimates a normal breathing peak directly from private CSI I/Q", async () => {
    const input = makeInput([0.25, 0.4, 0.395, 0.4, 0.395, 0.4, 0.395, 0.4]);
    const witness = await circuit.calculateWitness(input, true);
    const expectedBin = Math.round((0.25 - frequencyMin) / frequencyStep);

    // Outputs occupy witness indices 1..5 in declaration order.
    const isNormal = Number(witness[2]);
    const selectedSubcarrier = Number(witness[3]);
    const estimatedBin = Number(witness[4]);
    const globalBin = Number(witness[5]);

    assert.notStrictEqual(witness[1].toString(), "0", "Poseidon commitment must be non-zero");
    assert.strictEqual(isNormal, 1);
    assert.strictEqual(selectedSubcarrier, 0);
    assert.ok(Math.abs(estimatedBin - expectedBin) <= 1, `estimated bin ${estimatedBin}`);
    assert.ok(Math.abs(globalBin - expectedBin) <= 1, `global bin ${globalBin}`);
    await circuit.checkConstraints(witness);
  });

  it("rejects an out-of-band global peak", async () => {
    const input = makeInput([0.39, 0.4, 0.395, 0.39, 0.4, 0.395, 0.39, 0.4]);
    const witness = await circuit.calculateWitness(input, true);

    assert.strictEqual(Number(witness[2]), 0);
    assert.ok(Number(witness[5]) > 27, `global bin ${Number(witness[5])}`);
    await circuit.checkConstraints(witness);
  });

  it("does not accept a non-increasing public time axis", async () => {
    const input = makeInput([0.25, 0.4, 0.395, 0.4, 0.395, 0.4, 0.395, 0.4]);
    input.timestampsMs[20] = input.timestampsMs[19];
    await assert.rejects(() => circuit.calculateWitness(input, true));
  });
});
