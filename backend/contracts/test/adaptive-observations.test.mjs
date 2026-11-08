import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
import ganache from 'ganache';
import { BrowserProvider, ContractFactory, id } from 'ethers';
import { compile, root } from '../scripts/build.mjs';
const require = createRequire(import.meta.url);
const ejs = createRequire(require.resolve('snarkjs'))('ejs');

test('70-signal observation protocol with a real compact-circuit fixture', async () => {
  // The committed 64-candidate fixture exercises the same public interface.
  // Full 4004-candidate deployment is separately tested against its own key.
  const evidence = resolve(root, '../../docs/progress/2026-11-09-circom-adaptive');
  const vkey = JSON.parse(readFileSync(resolve(evidence, 'verification_key.json')));
  const proof = JSON.parse(readFileSync(resolve(evidence, 'proof.json')));
  const signals = JSON.parse(readFileSync(resolve(evidence, 'public.json')));
  const template = readFileSync(resolve(root, 'node_modules/snarkjs/templates/verifier_groth16.sol.ejs'), 'utf8');
  const verifierArtifact = compile({ 'Verifier.sol': { content: ejs.render(template, vkey) } })['Verifier.sol'].Groth16Verifier;
  assert.ok(verifierArtifact.evm.deployedBytecode.object.length / 2 <= 24576);
  const artifact = compile({ 'Observation.sol': { content: readFileSync(resolve(root, 'AdaptiveBreathingObservationRegistry.sol'), 'utf8') } })['Observation.sol'].AdaptiveBreathingObservationRegistry;
  const rpc = ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } });
  const provider = new BrowserProvider(rpc);
  try {
    const signer = await provider.getSigner();
    const reader = await provider.getSigner(1);
    const verifier = await new ContractFactory(verifierArtifact.abi, '0x' + verifierArtifact.evm.bytecode.object, signer).deploy();
    await verifier.waitForDeployment();
    const registry = await new ContractFactory(artifact.abi, '0x' + artifact.evm.bytecode.object, signer).deploy(await verifier.getAddress(), await signer.getAddress(), false);
    await registry.waitForDeployment();
    const { pi_a: a, pi_b: b, pi_c: c } = proof;
    const points = [a.slice(0, 2), [[b[0][1], b[0][0]], [b[1][1], b[1][0]]], c.slice(0, 2)];
    const time = (await provider.getBlock('latest')).timestamp - 60;
    const args = [id('adaptive'), id('patient'), time, 60, ...points, signals];
    await assert.rejects(registry.connect(reader).recordObservation.staticCall(...args), /revert/);
    await assert.rejects(registry.verifyObservation(id('missing')), /revert/);
    await (await registry.recordObservation(...args)).wait();
    assert.equal(await registry.connect(reader).verifyObservation(id('adaptive')), signals[1] === '1');
    assert.equal((await registry.getObservation(id('adaptive'))).length, 5);
    await assert.rejects(registry.recordObservation.staticCall(...args), /revert/);
    for (const index of [0, 1, 2, 6, 69]) {
      const changed = [...signals];
      changed[index] = index === 1 ? '0' : (BigInt(changed[index]) + 1n).toString();
      const key = id(`tamper-${index}`);
      await (await registry.recordObservation(key, id('patient'), time, 60, ...points, changed)).wait();
      await assert.rejects(registry.connect(reader).verifyObservation(key), /revert/);
    }
  } finally { provider.destroy(); await rpc.disconnect(); }
});
