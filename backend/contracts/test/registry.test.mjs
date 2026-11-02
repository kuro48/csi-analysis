import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import ganache from 'ganache';
import { BrowserProvider, ContractFactory, keccak256, ZeroHash, AbiCoder } from 'ethers';
import { root } from '../scripts/build.mjs';

test('real Groth16 proof: atomic verification, invalid inputs, duplicate and immutable binding', async () => {
  const rpc = ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } });
  const provider = new BrowserProvider(rpc);
  try {
    const signer = await provider.getSigner();
    const build = JSON.parse(readFileSync(resolve(root, 'build/onchain/compiled.json')));
    const bundle = JSON.parse(readFileSync(resolve(root, 'build/onchain/synthetic-proof.json')));
    const circuit = build.circuits.find(c => c.name === bundle.circuit);
    const verifier = await new ContractFactory(circuit.abi, circuit.bytecode, signer).deploy();
    await verifier.waitForDeployment();
    const address = await verifier.getAddress();
    const registry = await new ContractFactory(build.registry.abi, build.registry.bytecode, signer).deploy([circuit.circuitId], [[address, circuit.selector, circuit.publicSignalCount, circuit.verificationKeyHash, keccak256(await provider.getCode(address))]]);
    await registry.waitForDeployment();
    const { pi_a: pa, pi_b: pb, pi_c: pc } = bundle.proof;
    const a = pa.slice(0, 2), b = [[pb[0][1], pb[0][0]], [pb[1][1], pb[1][0]]], c = pc.slice(0, 2);
    const signals = bundle.publicSignals;
    const fn = registry.verifyAndRecord;
    assert.equal(await verifier.verifyProof(a, b, c, signals), true);
    await assert.rejects(fn.staticCall(circuit.circuitId, a, b, c, [signals[0] === '1' ? '0' : '1']), /revert/);
    await assert.rejects(fn.staticCall(circuit.circuitId, ['0', '0'], b, c, signals), /revert/);
    await assert.rejects(fn.staticCall(circuit.circuitId, a, b, c, []), /revert/);
    await assert.rejects(fn.staticCall(circuit.circuitId, a, b, c, ['21888242871839275222246405745257275088548364400416034343698204186575808495617']), /revert/);
    await assert.rejects(fn.staticCall(ZeroHash, a, b, c, signals), /revert/);
    // Bypass estimation and mine a failing transaction: no successful record/event.
    await assert.rejects(async () => {
      const tx = await fn(circuit.circuitId, ['0', '0'], b, c, signals, { gasLimit: 500000 });
      await tx.wait();
    }, /revert/);
    assert.equal(await registry.totalVerified(), 0n);
    const proofId = await fn.staticCall(circuit.circuitId, a, b, c, signals);
    const receipt = await (await fn(circuit.circuitId, a, b, c, signals)).wait();
    assert.equal(receipt.status, 1);
    assert.equal(await registry.totalVerified(), 1n);
    const record = await registry.records(proofId);
    assert.equal(record.submitter, await signer.getAddress());
    assert.equal(record.statementHash, keccak256(AbiCoder.defaultAbiCoder().encode(['bytes32', 'uint256[]'], [circuit.circuitId, signals])));
    const event = receipt.logs.map(log => registry.interface.parseLog(log)).find(log => log?.name === 'ProofVerified');
    assert.equal(event.args.proofId, proofId);
    await assert.rejects(fn.staticCall(circuit.circuitId, a, b, c, signals), /revert/);
    assert.equal(registry.interface.hasFunction('markProofAsVerified'), false);
    console.log(JSON.stringify({ proofId, gasUsed: receipt.gasUsed.toString(), block: receipt.blockNumber, signal: signals[0] }));
  } finally { provider.destroy(); await rpc.disconnect(); }
});
