const path = require("path");
const assert = require("assert");
const wasmTester = require("circom_tester").wasm;

describe("LombScargleTimestampCheck", function () {
  this.timeout(3600000);

  let circuit;

  before(async () => {
    const cachedOutput = process.env.LOMB_SCARGLE_TEST_OUTPUT;
    circuit = await wasmTester(
      path.join(__dirname, "..", "circuits", "csi_lomb_scargle_normality.circom"),
      {
        include: [path.join(__dirname, "..", "node_modules")],
        ...(cachedOutput ? { output: cachedOutput, recompile: false } : {}),
      },
    );
  });

  it("proves the dominant frequency of an irregularly sampled PCA waveform", async () => {
    const sampleCount = 384;
    const sampleOffset = 1024;
    const scale = 1000;

    const times = Array.from({ length: sampleCount }, (_, index) =>
      index * 0.1 + 0.012 * Math.sin(index * 0.73),
    );
    const encodeSignal = (frequency) =>
      times.map((time) => Math.round(Math.sin(2 * Math.PI * frequency * time) * scale) + sampleOffset);

    const input = {
      samples: [encodeSignal(0.25), encodeSignal(0.8), encodeSignal(1.1)],
      timestampsMs: times.map((time) => Math.round((time - times[0]) * 1000)),
      commitmentNonce: "12345678901234567890",
      parentCommitment: "987654321",
    };
    const witness = await circuit.calculateWitness(input, true);

    // Loading the multi-GB .sym through assertOut exceeds Node's maximum
    // string length. Public outputs occupy witness indices 1..5 in declaration
    // order, so inspect them directly as the following test already does.
    assert.strictEqual(Number(witness[1]), 1);
    assert.strictEqual(Number(witness[2]), 0);
    assert.strictEqual(Number(witness[3]), 18);
    assert.strictEqual(Number(witness[4]), 18);
    assert.notStrictEqual(witness[5].toString(), "0", "Poseidon intermediate hash must be non-zero");
    await circuit.checkConstraints(witness);
  });

  it("keeps circuit peak estimates within one bin of the floating-point frequency", async () => {
    const sampleCount = 384;
    const sampleOffset = 1024;
    const scale = 1000;
    const frequencyMin = 0.05;
    const frequencyStep = (1.5 - frequencyMin) / 127;
    const times = Array.from({ length: sampleCount }, (_, index) =>
      index * 0.1 + 0.012 * Math.sin(index * 0.73),
    );
    const encodeSignal = (frequency) =>
      times.map((time) => Math.round(Math.sin(2 * Math.PI * frequency * time) * scale) + sampleOffset);
    const timestampsMs = times.map((time) => Math.round((time - times[0]) * 1000));

    for (const frequency of [0.12, 0.25, 0.4, 0.6]) {
      const input = {
        samples: [encodeSignal(frequency), encodeSignal(0.8), encodeSignal(1.1)],
        timestampsMs,
        commitmentNonce: "12345678901234567890",
        parentCommitment: "987654321",
      };
      const witness = await circuit.calculateWitness(input, true);
      const expectedBin = Math.round((frequency - frequencyMin) / frequencyStep);
      const estimatedBin = Number(witness[3]);
      const globalBin = Number(witness[4]);

      assert.ok(Math.abs(estimatedBin - expectedBin) <= 1, `${frequency} Hz estimated bin ${estimatedBin}`);
      assert.ok(Math.abs(globalBin - expectedBin) <= 1, `${frequency} Hz global bin ${globalBin}`);
      await circuit.checkConstraints(witness);
    }
  });
});
