// Evaluation only: execute the compiled circuit with witness sanity checks.
// This is not a new Groth16 proof or an independent full R1CS check.
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const [wasm, input, output] = process.argv.slice(2);
  if (!output) throw Error('Usage: node selection_witness.cjs circuit.wasm input.json public.json');
  const build = require(path.join(path.dirname(path.resolve(wasm)), 'witness_calculator.js'));
  const calculator = await build(fs.readFileSync(wasm));
  const raw = Buffer.from(await calculator.calculateWTNSBin(JSON.parse(fs.readFileSync(input)), 1));
  if (raw.toString('ascii', 0, 4) !== 'wtns' || raw.readUInt32LE(4) !== 2) throw Error('Invalid witness');
  let position = 12, fieldBytes, values;
  for (let i = 0; i < raw.readUInt32LE(8); i++) {
    const type = raw.readUInt32LE(position);
    const size = Number(raw.readBigUInt64LE(position + 4));
    position += 12;
    if (type === 1) fieldBytes = raw.readUInt32LE(position);
    if (type === 2) {
      if (fieldBytes !== 32 || size < 71 * fieldBytes) throw Error('Unexpected witness schema');
      values = Array.from({ length: 71 }, (_, j) => {
        const bytes = raw.subarray(position + j * fieldBytes, position + (j + 1) * fieldBytes);
        return BigInt('0x' + Buffer.from(bytes).reverse().toString('hex')).toString();
      });
    }
    position += size;
  }
  if (!values || values[0] !== '1') throw Error('Missing witness values');
  fs.writeFileSync(output, JSON.stringify(values.slice(1)));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
