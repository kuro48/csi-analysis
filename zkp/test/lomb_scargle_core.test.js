const path = require("path");
const wasmTester = require("circom_tester").wasm;

describe("LombScargleTimestampCheck", function () {
  this.timeout(600000);

  let circuit;

  before(async () => {
    circuit = await wasmTester(
      path.join(__dirname, "..", "circuits", "csi_lomb_scargle_normality.circom"),
      { include: [path.join(__dirname, "..", "node_modules")] },
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
    };
    const witness = await circuit.calculateWitness(input, true);

    await circuit.assertOut(witness, {
      isNormal: 1,
      selectedPc: 0,
      estimatedFrequencyBin: 18,
      globalPeakFrequencyBin: 18,
    });
    await circuit.checkConstraints(witness);
  });
});
