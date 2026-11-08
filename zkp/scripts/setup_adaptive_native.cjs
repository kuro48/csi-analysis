// Testnet-only, single-party Groth16 setup; never invoked by an observation worker.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');

async function main() {
  const [workArg] = process.argv.slice(2);
  if (!workArg) throw Error('Usage: node zkp/scripts/setup_adaptive_native.cjs WORK_DIR');
  const work = path.resolve(workArg);
  const name = 'csi_lomb_scargle_adaptive_4004';
  const native = path.resolve(__dirname, '../native-prover/target/release/csi-native-prover');
  const files = {
    r1cs: path.join(work, 'build', name + '.r1cs'),
    wasm: path.join(work, 'build', name + '_js', name + '.wasm'),
    prover: native,
    provingKey: path.join(work, 'native', 'proving_key.ark'),
    verificationKey: path.join(work, 'native', 'verification_key.json'),
  };
  const manifestPath = path.join(work, 'artifacts.json');
  if (fs.existsSync(manifestPath) || fs.existsSync(files.provingKey) || fs.existsSync(files.verificationKey)) throw Error('Refusing to replace an existing setup');
  for (const item of ['r1cs', 'wasm', 'prover']) fs.accessSync(files[item]);
  fs.mkdirSync(path.dirname(files.provingKey), { recursive: true, mode: 0o700 });
  const setup = spawnSync(native, ['setup', files.r1cs, files.provingKey, files.verificationKey], { stdio: 'inherit' });
  if (setup.error || setup.status !== 0) throw Error('Native setup failed: no artifact manifest was published');
  const sha256 = {};
  for (const [name, filename] of Object.entries(files)) {
    const hash = createHash('sha256');
    for await (const chunk of fs.createReadStream(filename)) hash.update(chunk);
    sha256[name] = hash.digest('hex');
  }
  const manifest = { version: 1, prover: 'arkworks-0.5', setup: 'single-party-local-csprng-testnet-only',
    circuit: name, capacity: 4004, sampleCount: 64, publicSignalCount: 70, isNormalIndex: 1, files, sha256 };
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  console.log(manifestPath);
}
main().catch(error => { console.error(error.message); process.exit(1); });
