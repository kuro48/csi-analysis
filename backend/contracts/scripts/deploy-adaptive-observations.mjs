import { readFileSync, writeFileSync, mkdirSync, createReadStream } from 'node:fs';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { isDeepStrictEqual } from 'node:util';
import { createRequire } from 'node:module';
import { JsonRpcProvider, Wallet, ContractFactory, NonceManager, keccak256, getAddress } from 'ethers';
import { compile, root } from './build.mjs';
import { deploymentNetwork } from './networks.mjs';

const chainId = Number(process.env.ONCHAIN_CHAIN_ID || 11155111);
const network = deploymentNetwork(chainId);
if (!process.env.ADAPTIVE_ARTIFACT_MANIFEST || !process.env.ETHEREUM_RPC_URL) throw Error('Set ADAPTIVE_ARTIFACT_MANIFEST and ETHEREUM_RPC_URL');
if (!network.local && process.env.ONCHAIN_DEPLOY_PUBLIC !== 'true') throw Error('Set ONCHAIN_DEPLOY_PUBLIC=true');
const artifacts = JSON.parse(readFileSync(process.env.ADAPTIVE_ARTIFACT_MANIFEST));
if (artifacts.circuit !== 'csi_lomb_scargle_adaptive_4004' || artifacts.capacity !== 4004 || artifacts.publicSignalCount !== 70) throw Error('Wrong adaptive artifacts');
const native = artifacts.prover === 'arkworks-0.5';
if (artifacts.prover && !native && artifacts.prover !== 'snarkjs') throw Error('Unsupported prover');
for (const name of native ? ['provingKey', 'verificationKey'] : ['zkey', 'verificationKey']) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(artifacts.files[name])) hash.update(chunk);
  if (hash.digest('hex') !== artifacts.sha256[name]) throw Error(`Artifact hash mismatch: ${name}`);
}
const output = resolve(process.env.ADAPTIVE_DEPLOY_DIR || join(root, '../../.local/adaptive-evm', String(chainId)));
mkdirSync(output, { recursive: true });
const cli = resolve(root, 'node_modules/snarkjs/build/cli.cjs');
const verifierSource = join(output, 'Verifier.sol');
const keyPath = join(output, 'verification_key.json');
if (native) {
  const require = createRequire(import.meta.url);
  const ejs = createRequire(require.resolve('snarkjs'))('ejs');
  const vkey = JSON.parse(readFileSync(artifacts.files.verificationKey));
  if (vkey.nPublic !== 70 || vkey.IC.length !== 71 || vkey.protocol !== 'groth16' || vkey.curve !== 'bn128') throw Error('Invalid native verification key');
  writeFileSync(verifierSource, ejs.render(readFileSync(resolve(root, 'node_modules/snarkjs/templates/verifier_groth16.sol.ejs'), 'utf8'), vkey));
  writeFileSync(keyPath, readFileSync(artifacts.files.verificationKey));
} else {
  execFileSync(process.execPath, [cli, 'zkey', 'export', 'solidityverifier', artifacts.files.zkey, verifierSource]);
  execFileSync(process.execPath, [cli, 'zkey', 'export', 'verificationkey', artifacts.files.zkey, keyPath]);
}
if (!isDeepStrictEqual(JSON.parse(readFileSync(keyPath)), JSON.parse(readFileSync(artifacts.files.verificationKey)))) throw Error('Proving key and verification key mismatch');
// Use identical key bytes for the worker, EVM manifest, Fabric, and benchmarks.
writeFileSync(keyPath, readFileSync(artifacts.files.verificationKey));
const verifierArtifact = compile({ 'Verifier.sol': { content: readFileSync(verifierSource, 'utf8') } })['Verifier.sol'].Groth16Verifier;
const registryArtifact = compile({ 'Observation.sol': { content: readFileSync(join(root, 'AdaptiveBreathingObservationRegistry.sol'), 'utf8') } })['Observation.sol'].AdaptiveBreathingObservationRegistry;
if (verifierArtifact.evm.deployedBytecode.object.length / 2 > 24576) throw Error('Verifier exceeds EVM bytecode size limit');
const provider = new JsonRpcProvider(process.env.ETHEREUM_RPC_URL);
try {
  if (Number((await provider.getNetwork()).chainId) !== chainId) throw Error('Wrong RPC chain ID');
  if (!process.env.BLOCKCHAIN_PRIVATE_KEY && !(network.local && process.env.ONCHAIN_LOCAL_UNLOCKED === 'true')) throw Error('Set deployment key');
  const signer = new NonceManager(process.env.BLOCKCHAIN_PRIVATE_KEY
    ? new Wallet(process.env.BLOCKCHAIN_PRIVATE_KEY, provider) : await provider.getSigner());
  const recorderAddress = getAddress(process.env.OBSERVATION_RECORDER_ADDRESS || (network.local ? await signer.getAddress() : ''));
  const debugMode = process.env.OBSERVATION_DEBUG_INPUTS === 'true';
  async function deploy(artifact, args = []) {
    const factory = new ContractFactory(artifact.abi, '0x' + artifact.evm.bytecode.object, signer);
    const tx = await factory.getDeployTransaction(...args);
    const gasLimit = (await signer.estimateGas(tx)) * 12n / 10n;
    const fees = await provider.getFeeData();
    const fee = fees.maxFeePerGas ?? fees.gasPrice;
    if (gasLimit * fee > BigInt(process.env.ONCHAIN_MAX_DEPLOY_WEI || '50000000000000000')) throw Error('Deployment exceeds fee cap');
    const deployed = await factory.deploy(...args, { gasLimit });
    await deployed.waitForDeployment();
    return deployed;
  }
  const verifier = await deploy(verifierArtifact);
  const verifierAddress = await verifier.getAddress();
  const registry = await deploy(registryArtifact, [verifierAddress, recorderAddress, debugMode]);
  const registryAddress = await registry.getAddress();
  const receipt = await registry.deploymentTransaction().wait();
  const manifest = { version: 1, kind: 'breathing-observations', chainId, networkName: network.name,
    registryAddress, registryCodeHash: keccak256(await provider.getCode(registryAddress)), registryAbi: registryArtifact.abi,
    verifierAddress, verifierCodeHash: keccak256(await provider.getCode(verifierAddress)), recorderAddress, debugMode,
    deploymentBlock: receipt.blockNumber, deploymentTransaction: receipt.hash,
    circuit: artifacts.circuit, capacity: 4004, publicSignalCount: 70, isNormalIndex: 1,
    verificationKeyFile: 'verification_key.json', verificationKeyHash: '0x' + createHash('sha256').update(readFileSync(keyPath)).digest('hex') };
  writeFileSync(join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({ chainId, registryAddress, manifest: join(output, 'manifest.json') }));
} finally { provider.destroy(); }
