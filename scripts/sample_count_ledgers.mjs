// Isolated local-chain experiments. Never deploys to Sepolia or production namespaces.
import { readFileSync, writeFileSync, mkdirSync, existsSync, openSync, closeSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
import { compile } from '../backend/contracts/scripts/build.mjs';
import { openGateway } from '../fabric/gateway.mjs';

const root = resolve(import.meta.dirname, '..');
const require = createRequire(join(root, 'backend/contracts/package.json'));
const { JsonRpcProvider, ContractFactory, Contract, NonceManager, id, keccak256 } = require('ethers');
const snarkjs = createRequire(join(root, 'zkp/package.json'))('snarkjs');
const ejs = createRequire(require.resolve('snarkjs'))('ejs');
const [stage, workArg, nArg, kArg] = process.argv.slice(2);
const k = kArg === undefined ? 32 : Number(kArg);
if (![32,64,128].includes(k)) throw Error("Unsupported frequency grid");
const gridExperiment = k !== 32;
const n = Number(nArg), work = resolve(workArg || '.local/sample-count');
if (!['deploy', 'measure'].includes(stage) || ![64, 96, 128].includes(n)) throw Error('Usage: sample_count_ledgers.mjs deploy|measure WORK 64|96|128');
const dir = join(work, gridExperiment ? `n${n}k${k}` : `n${n}`), count = n + 6;
const read = path => JSON.parse(readFileSync(path));
const save = (path, value) => writeFileSync(path, JSON.stringify(value, (_, v) => typeof v === 'bigint' ? v.toString() : v, 2) + '\n');
const hash = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const base = read(n === 64 && !gridExperiment ? join(root, '.local/circom-adaptive-4004/artifacts.json') : join(dir, 'artifacts.json'));
const artifacts = { ...base, experiment: gridExperiment ? 'frequency-grid-v1' : 'sample-count-v1', sampleCount: n, capacity: 4004,
  ...(gridExperiment ? { frequencyGridCount: k } : {}),
  circuit: gridExperiment ? `csi_lomb_scargle_adaptive_n${n}_k${k}_c4004` : `csi_lomb_scargle_adaptive_n${n}_c4004`, publicSignalCount: count, isNormalIndex: 1 };
assert.equal(hash(base.files.verificationKey), base.sha256.verificationKey);
const key = read(base.files.verificationKey);
const bundle = read(join(dir, 'csi_20260519_114943/bundle.json'));
assert.equal(key.nPublic, count);
assert.equal(bundle.publicSignals.length, count);
assert.equal(await snarkjs.groth16.verify(key, bundle.publicSignals, bundle.proof), true);
const points = p => [p.pi_a.slice(0, 2), [[p.pi_b[0][1], p.pi_b[0][0]], [p.pi_b[1][1], p.pi_b[1][0]]], p.pi_c.slice(0, 2)];
// Each verification must reach the node; disable provider request caching/batching.
const provider = new JsonRpcProvider('http://127.0.0.1:8545', undefined, { cacheTimeout: -1, batchMaxCount: 1 });
provider.pollingInterval = 100;
assert.equal(Number((await provider.getNetwork()).chainId), 1337);
const signer = new NonceManager(await provider.getSigner());
const fabricDir = join(dir, 'fabric');
const network = join(root, '.local/fabric/fabric-samples/test-network');
const chaincodeName = gridExperiment ? `csisamples${n}k${k}v1` : `csisamples${n}v1`;

function run(command, args, log, env = process.env, cwd = root) {
  return new Promise((accept, reject) => {
    const fd = openSync(log, 'w');
    const child = spawn(command, args, { cwd, env, stdio: ['ignore', fd, fd] });
    child.on('error', error => { closeSync(fd); reject(error); });
    child.on('exit', code => { closeSync(fd); code === 0 ? accept() : reject(Error(`${command} exit ${code}; see ${log}`)); });
  });
}
const stats = values => {
  const sorted = [...values].sort((a, b) => a - b);
  return { count: values.length, medianMs: (sorted[Math.floor((sorted.length - 1)/2)] + sorted[Math.floor(sorted.length/2)])/2,
    minMs: sorted[0], maxMs: sorted.at(-1), meanMs: values.reduce((a, b) => a+b, 0)/values.length };
};

try {
  if (stage === 'deploy') {
    save(join(dir, 'ledger-artifacts.json'), artifacts);
    if (!existsSync(join(dir, 'evm.json'))) {
      const verifierSource = ejs.render(readFileSync(join(root, 'backend/contracts/node_modules/snarkjs/templates/verifier_groth16.sol.ejs'), 'utf8'), key);
      // Exact production registry semantics, specialized to N+6 public inputs.
      const registrySource = readFileSync(join(root, 'backend/contracts/AdaptiveBreathingObservationRegistry.sol'), 'utf8')
        .replace(/\b70\b/g, String(count)).replace(/\b69\b/g, String(count - 1));
      writeFileSync(join(dir, 'Verifier.sol'), verifierSource);
      writeFileSync(join(dir, 'Registry.sol'), registrySource);
      const compiled = compile({ 'Verifier.sol': { content: verifierSource }, 'Registry.sol': { content: registrySource } });
      const verifierArtifact = compiled['Verifier.sol'].Groth16Verifier;
      const registryArtifact = compiled['Registry.sol'].AdaptiveBreathingObservationRegistry;
      assert.ok(verifierArtifact.evm.deployedBytecode.object.length/2 <= 24576, 'EVM verifier size limit');
      const start = performance.now();
      const verifier = await new ContractFactory(verifierArtifact.abi, '0x'+verifierArtifact.evm.bytecode.object, signer).deploy();
      await verifier.waitForDeployment();
      const registry = await new ContractFactory(registryArtifact.abi, '0x'+registryArtifact.evm.bytecode.object, signer)
        .deploy(await verifier.getAddress(), await signer.getAddress(), true);
      await registry.waitForDeployment();
      save(join(dir, 'evm.json'), { chainId: 1337, sampleCount: n, publicSignalCount: count,
        verifierAddress: await verifier.getAddress(), verifierAbi: verifierArtifact.abi,
        registryAddress: await registry.getAddress(), registryAbi: registryArtifact.abi,
        registryCodeHash: keccak256(await provider.getCode(await registry.getAddress())),
        verifierCodeHash: keccak256(await provider.getCode(await verifier.getAddress())),
        verificationKeyHash: hash(base.files.verificationKey), deploymentMs: performance.now()-start });
    }
    mkdirSync(fabricDir, { recursive: true });
    await run('node', [join(root, 'fabric/scripts/prepare-chaincode.mjs')], join(fabricDir, 'prepare.log'), {
      ...process.env, FABRIC_WORK_DIR: fabricDir, FABRIC_NETWORK_DIR: network, FABRIC_CHAINCODE_NAME: chaincodeName,
      FABRIC_VKEY: base.files.verificationKey, ADAPTIVE_ARTIFACT_MANIFEST: join(dir, 'ledger-artifacts.json'), FABRIC_DEBUG_MODE: 'true',
    });
    if (!existsSync(join(fabricDir, 'deployed.json'))) {
      const started = performance.now();
      await run('bash', ['network.sh', 'deployCC', '-c', 'csi', '-ccn', chaincodeName,
        '-ccp', join(fabricDir, 'chaincode'), '-ccl', 'javascript', '-ccv', '1.0', '-ccs', '1',
        '-ccep', "AND('Org1MSP.peer','Org2MSP.peer')"], join(fabricDir, 'deploy.log'), process.env, network);
      save(join(fabricDir, 'deployed.json'), { chaincodeName, deploymentMs: performance.now()-started });
    }
    console.log(`Deployed isolated n${n} EVM and Fabric verifiers`);
  } else {
    const resultPath = join(dir, 'ledger-measurements.json');
    if (existsSync(resultPath)) throw Error('Existing measurement: use its saved receipt, do not duplicate writes');
    const evm = read(join(dir, 'evm.json'));
    assert.equal(keccak256(await provider.getCode(evm.registryAddress)), evm.registryCodeHash);
    assert.equal(keccak256(await provider.getCode(evm.verifierAddress)), evm.verifierCodeHash);
    const registry = new Contract(evm.registryAddress, evm.registryAbi, signer);
    const verifier = new Contract(evm.verifierAddress, evm.verifierAbi, provider);
    const writer = openGateway(read(join(fabricDir, 'gateway-writer.json')), 'writer');
    const reader = openGateway(read(join(fabricDir, 'gateway-reader.json')), 'reader');
    const progressPath = join(dir, 'ledger-progress.json');
    const report = existsSync(progressPath) ? read(progressPath) : { sampleCount: n, frequencyGridCount: k, publicSignalCount: count, capture: 'csi_20260519_114943',
      candidateCount: 4004, recordedProofSha256: hash(join(dir, 'csi_20260519_114943/bundle.json')),
      recordRepetitions: 1, verifyWarmRepetitions: 10,
      verificationMode: 'EVM eth_call / Fabric evaluateTransaction: ledger state read plus in-chain verifier, not a new transaction',
      evm: {}, fabric: {}, local: {} };
    assert.equal(report.recordedProofSha256, hash(join(dir, 'csi_20260519_114943/bundle.json')));
    try {
      await writer.configuration(); await reader.configuration();
      const observationId = report.observationId || id(`sample-count:${n}:${randomUUID()}`), patientRef = id('sample-count-real-capture');
      report.observationId = observationId;
      const payload = { observationId, patientRef, observedAt: 1779158991, durationSeconds: 54,
        proof: bundle.proof, publicSignals: bundle.publicSignals };
      const expected = bundle.publicSignals[1] === '1';
      const args = [observationId, patientRef, payload.observedAt, payload.durationSeconds, ...points(bundle.proof), bundle.publicSignals];
      // Gas estimation is explicitly outside the recording timer for all N.
      if (!report.evm.transactionHash) {
        const gasLimit = (await registry.recordObservation.estimateGas(...args))*12n/10n;
        const started = performance.now();
        const tx = await registry.recordObservation(...args, { gasLimit });
        const submitted = performance.now();
        const receipt = await tx.wait(1);
        assert.equal(receipt.status, 1);
        report.evm = { recordCommitMs: performance.now()-started, submitMs: submitted-started,
          transactionHash: receipt.hash, blockNumber: receipt.blockNumber, gasUsed: receipt.gasUsed.toString(),
          feeWei: receipt.fee.toString(), pollingIntervalMs: 100, rpcCacheDisabled: true, registryAddress: evm.registryAddress };
        save(progressPath, report);
      }
      if (!report.fabric.transactionId) {
        const recorded = await writer.record(payload);
        assert.equal(recorded.result.reused, false, 'Cannot measure an idempotent retry as a fresh record');
        report.fabric = { ...recorded.timings, ...recorded.commit, chaincodeName };
        save(progressPath, report);
      }
      const localTimes = [], evmTimes = [], fabricTimes = [];
      for (let i = 0; i < 11; i++) {
        let start = performance.now();
        assert.equal(await snarkjs.groth16.verify(key, bundle.publicSignals, bundle.proof), true);
        localTimes.push(performance.now()-start);
        start = performance.now();
        assert.equal(await registry.verifyObservation(observationId), expected);
        evmTimes.push(performance.now()-start);
        const verified = await reader.verify(observationId);
        assert.equal(verified.result.isNormal, expected);
        fabricTimes.push(verified.timings.verifyReadMs);
      }
      for (const [label, values] of [['local', localTimes], ['evm', evmTimes], ['fabric', fabricTimes]]) {
        Object.assign(report[label], { firstVerifyMs: values[0], warmVerifyMs: values.slice(1), warmSummary: stats(values.slice(1)) });
      }
      save(progressPath, report);
      const changed = [...bundle.publicSignals]; changed[1] = changed[1] === '0' ? '1' : '0';
      assert.equal(await snarkjs.groth16.verify(key, changed, bundle.proof), false);
      assert.equal(await verifier.verifyProof(...points(bundle.proof), changed), false);
      const badId = id(`sample-count-negative:${observationId}`);
      const badRecord = await writer.record({ ...payload, observationId: badId, publicSignals: changed });
      // Reader health has just been established by eleven successful real reads.
      await assert.rejects(reader.verify(badId), error =>
        /Invalid proof|verification failed/i.test(String(error) + JSON.stringify(error.details)));
      report.negativeControl = { modifiedIsNormalRejected: true, fabricTransactionId: badRecord.commit.transactionId };
      report.completedAt = new Date().toISOString();
      save(resultPath, report);
      console.log(JSON.stringify({ n, evm: report.evm, fabric: report.fabric }));
    } finally { writer.close(); reader.close(); }
  }
} finally { provider.destroy(); }
process.exit(0);
