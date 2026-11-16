// Research runner. Inputs and optional full witness stay in the private workdir.
const fs = require('node:fs');
const path = require('node:path');
const { performance } = require('node:perf_hooks');
async function main() {
  const [wasm, inputPath, outputPath, witnessPath] = process.argv.slice(2);
  if (!outputPath) throw Error('Usage: sample_count_witness.cjs wasm input output [witness]');
  const input = JSON.parse(fs.readFileSync(inputPath));
  const n = input.timestampsMs.length;
  if (![64, 96, 128].includes(n)) throw Error('Unsupported sample count');
  const started = performance.now();
  const build = require(path.join(path.dirname(path.resolve(wasm)), 'witness_calculator.js'));
  const calculator = await build(fs.readFileSync(wasm));
  const raw = Buffer.from(await calculator.calculateWTNSBin(input, 1));
  const calculated = performance.now();
  if (raw.toString('ascii', 0, 4) !== 'wtns' || raw.readUInt32LE(4) !== 2) throw Error('Invalid witness');
  let offset = 12, size, values;
  for (let j = 0; j < raw.readUInt32LE(8); j++) {
    const type = raw.readUInt32LE(offset), length = Number(raw.readBigUInt64LE(offset + 4));
    offset += 12;
    if (type === 1) size = raw.readUInt32LE(offset);
    if (type === 2) {
      if (size !== 32 || length < (n + 7) * size) throw Error('Wrong witness schema');
      values = Array.from({ length: n + 7 }, (_, i) => BigInt('0x' + Buffer.from(raw.subarray(offset + i * size, offset + (i + 1) * size)).reverse().toString('hex')).toString());
    }
    offset += length;
  }
  if (!values || values.shift() !== '1' || Number(values[n + 5]) !== input.candidateCount
      || JSON.stringify(values.slice(5, n + 5).map(Number)) !== JSON.stringify(input.timestampsMs)) throw Error('Public schema mismatch');
  if (witnessPath) fs.writeFileSync(witnessPath, raw, { mode: 0o600 });
  fs.writeFileSync(outputPath, JSON.stringify({ publicSignals: values,
    witnessMs: calculated - started, witnessBytes: raw.length, witnessWriteMs: performance.now() - calculated }, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
