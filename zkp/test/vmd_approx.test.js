const path = require('path');
const assert = require('assert');
const { wasm } = require('circom_tester');
const { execFileSync } = require('child_process');

const N = 128, FS = 2;
function tone(hz, amp = 80) { return Array.from({length:N}, (_,t)=>Math.round(amp*Math.sin(2*Math.PI*hz*t/FS))); }
function reference(waveform) {
  const script = "import json,sys; sys.path.insert(0,'" + path.resolve(__dirname, '../scripts') + "'); from vmd_approx_reference import vmd_approx; print(json.dumps(vmd_approx(json.load(sys.stdin))))";
  return JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', script], {input:JSON.stringify(waveform), encoding:'utf8'}));
}
function checkInternals(circuit, w, ref) {
  const P = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
  const read = name => BigInt(w[circuit.symbols['main.' + name].varIdx]);
  for (let k=0;k<3;k++) assert.equal(read(`center[4][${k}]`), BigInt(ref.centers[k]));
  for (let k=0;k<3;k++) for (let j=0;j<63;j++) {
    const rr = (BigInt(ref.spectra[k][j][0]) % P + P) % P;
    const ii = (BigInt(ref.spectra[k][j][1]) % P + P) % P;
    assert.equal(read(`ur[3][${k}][${j}]`), rr);
    assert.equal(read(`ui[3][${k}][${j}]`), ii);
  }
}

describe('input-only approximate VMD', function () {
  this.timeout(180000);
  let circuit;
  before(async () => { circuit = await wasm(path.join(__dirname, '../circuits/csi_vmd_approx.circom'), { include: [path.join(__dirname, '../node_modules')] }); await circuit.loadSymbols(); });
  for (const [hz, expected] of [[.25,16],[.5,32],[.8,51]]) {
    it(`accepts ${hz}Hz and reports expected bin`, async () => {
      const w = await circuit.calculateWitness({waveform:tone(hz)}, true);
      await circuit.checkConstraints(w);
      const ref = reference(tone(hz));
      assert.equal(ref.peak_bin, expected);
      checkInternals(circuit, w, ref);
      await circuit.assertOut(w, {isNormal: ref.is_normal ? 1 : 0, estimatedFrequencyBin: ref.peak_bin, selectedMode0based: ref.selected_mode});
    });
  }
  it('returns false for zero waveform', async () => {
    const w = await circuit.calculateWitness({waveform:Array(N).fill(0)}, true);
    await circuit.checkConstraints(w);
    await circuit.assertOut(w, {isNormal: 0, estimatedFrequencyBin: 0, selectedMode0based: 0});
  });
  it('matches reference on mixture and seeded waveform', async () => {
    const mixed = tone(.25, 60).map((x,i)=>x + tone(.75,25)[i]);
    const random = Array.from({length:N}, (_,i)=>((i*1103515245+12345>>>0)%201)-100);
    for (const waveform of [mixed, random]) {
      const w = await circuit.calculateWitness({waveform}, true);
      const ref = reference(waveform);
      await circuit.assertOut(w, {isNormal: ref.is_normal ? 1 : 0, estimatedFrequencyBin: ref.peak_bin, selectedMode0based: ref.selected_mode});
      checkInternals(circuit, w, ref);
    }
  });
  it('rejects out of range samples', async () => {
    await assert.rejects(() => circuit.calculateWitness({waveform:Array(N).fill(101)}, true));
    await assert.rejects(() => circuit.calculateWitness({waveform:Array(N).fill(-101)}, true));
  });
  it('rejects tampered output witness', async () => {
    const w = await circuit.calculateWitness({waveform:tone(.25)}, true);
    const bad = w.slice(); bad[1] = bad[1] + 1n;
    await assert.rejects(() => circuit.checkConstraints(bad));
  });
  it('rejects tampered division witness', async () => {
    const w = await circuit.calculateWitness({waveform:tone(.25)}, true);
    const idx = circuit.symbols['main.q0_0_0.qm'].varIdx;
    const bad = w.slice(); bad[idx] = bad[idx] + 1n;
    await assert.rejects(() => circuit.checkConstraints(bad));
  });
});
