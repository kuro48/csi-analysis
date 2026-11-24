import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
import ganache from 'ganache';
import { BrowserProvider, ContractFactory, id } from 'ethers';
import { compile, root } from '../scripts/build.mjs';

test('full 4004 real capture: record, third-party verify, reject changed output', async () => {
  // Offline contract regression, NOT a Sepolia transaction or performance measurement.
  const evidence = resolve(root, '../../docs/progress/2026-11-09-adaptive-4004');
  const key = JSON.parse(readFileSync(resolve(evidence, 'verification_key.json')));
  const bundle = JSON.parse(readFileSync(resolve(evidence, 'evm-proof-bundle.json')));
  const require = createRequire(import.meta.url);
  const ejs = createRequire(require.resolve('snarkjs'))('ejs');
  const source = ejs.render(readFileSync(resolve(root, 'node_modules/snarkjs/templates/verifier_groth16.sol.ejs'), 'utf8'), key);
  const compiled = compile({ 'Verifier.sol': { content: source },
    'Observation.sol': { content: readFileSync(resolve(root, 'AdaptiveBreathingObservationRegistry.sol'), 'utf8') } });
  const rpc = ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } });
  const provider = new BrowserProvider(rpc);
  try {
    const writer = await provider.getSigner();
    const reader = await provider.getSigner(1);
    const deploy = async (artifact, args = []) => {
      const contract = await new ContractFactory(artifact.abi, '0x' + artifact.evm.bytecode.object, writer).deploy(...args);
      await contract.waitForDeployment(); return contract;
    };
    const verifier = await deploy(compiled['Verifier.sol'].Groth16Verifier);
    const registry = await deploy(compiled['Observation.sol'].AdaptiveBreathingObservationRegistry,
      [await verifier.getAddress(), await writer.getAddress(), true]);
    const { pi_a: a, pi_b: b, pi_c: c } = bundle.proof;
    const points = [a.slice(0, 2), [[b[0][1], b[0][0]], [b[1][1], b[1][0]]], c.slice(0, 2)];
    const args = [id('real-capture'), id('anonymous-observation'), 1779158991, 54, ...points, bundle.publicSignals];
    await assert.rejects(registry.connect(reader).recordObservation.staticCall(...args));
    await assert.rejects(registry.connect(reader).verifyObservation(id('missing')));
    await (await registry.recordObservation(...args)).wait();
    assert.equal(await registry.connect(reader).verifyObservation(id('real-capture')), bundle.publicSignals[1] === '1');
    const changed = [...bundle.publicSignals]; changed[1] = changed[1] === '0' ? '1' : '0';
    await (await registry.recordObservation(id('changed'), args[1], args[2], args[3], ...points, changed)).wait();
    await assert.rejects(registry.connect(reader).verifyObservation(id('changed')));
  } finally { provider.destroy(); await rpc.disconnect(); }
});
