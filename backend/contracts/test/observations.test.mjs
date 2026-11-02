import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import ganache from 'ganache';
import { BrowserProvider, ContractFactory, id } from 'ethers';
import { compile, root } from '../scripts/build.mjs';

test('record first; third-party verifies stored proof; invalid output never returned', async () => {
  const rpc = ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } });
  const provider = new BrowserProvider(rpc);
  try {
    const signer = await provider.getSigner();
    const thirdParty = await provider.getSigner(1);
    const build = JSON.parse(readFileSync(resolve(root, 'build/onchain/compiled.json')));
    const bundle = JSON.parse(readFileSync(resolve(root, 'build/onchain/synthetic-proof.json')));
    const circuit = build.circuits.find(c => c.name === 'csi_breathing_certificate');
    const verifier = await new ContractFactory(circuit.abi, circuit.bytecode, signer).deploy();
    await verifier.waitForDeployment();
    const artifact = compile({ 'Observation.sol': { content: readFileSync(resolve(root, 'BreathingObservationRegistry.sol'), 'utf8') } })['Observation.sol'].BreathingObservationRegistry;
    const registry = await new ContractFactory(artifact.abi, '0x' + artifact.evm.bytecode.object, signer).deploy(await verifier.getAddress(), await signer.getAddress(), false);
    await registry.waitForDeployment();
    assert.equal(await registry.debugMode(), false);
    const { pi_a: a, pi_b: b, pi_c: c } = bundle.proof;
    const proof = [a.slice(0, 2), [[b[0][1], b[0][0]], [b[1][1], b[1][0]]], c.slice(0, 2), bundle.publicSignals];
    const time = (await provider.getBlock('latest')).timestamp - 60;
    const args = [id('capture'), id('patient'), time, 60, ...proof];
    await assert.rejects(registry.connect(thirdParty).recordObservation.staticCall(...args), /revert/);
    await assert.rejects(registry.verifyObservation(id('missing')), /revert/);
    await (await registry.recordObservation(...args)).wait();
    assert.equal(await registry.connect(thirdParty).verifyObservation(id('capture')), bundle.publicSignals[0] === '1');
    assert.equal((await registry.getObservation(id('capture'))).patientRef, id('patient'));
    await assert.rejects(registry.recordObservation.staticCall(...args), /revert/);
    await assert.rejects(registry.recordObservation.staticCall(id('reassigned'), id('other-patient'), time, 60, ...proof), /revert/);
    // Invalid proof can be recorded, but result retrieval MUST revert, not return false.
    const invalid = [...proof.slice(0, 3), [bundle.publicSignals[0] === '1' ? '0' : '1']];
    await (await registry.recordObservation(id('invalid'), id('patient'), time, 60, ...invalid)).wait();
    await assert.rejects(registry.connect(thirdParty).verifyObservation(id('invalid')), /revert/);
    assert.equal(registry.interface.hasFunction('setVerifier'), false);
    assert.equal(registry.interface.hasFunction('setResult'), false);
  } finally { provider.destroy(); await rpc.disconnect(); }
});
