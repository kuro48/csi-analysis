import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JsonRpcProvider, Wallet, ContractFactory, NonceManager, keccak256, getAddress } from 'ethers';
import { build, compile, root } from './build.mjs';
import { deploymentNetwork } from './networks.mjs';

const chainId = Number(process.env.ONCHAIN_CHAIN_ID || 11155111);
const network = deploymentNetwork(chainId);
const rpc = process.env.ETHEREUM_RPC_URL;
if (!rpc) throw new Error('Set ETHEREUM_RPC_URL');
if (!network.local && process.env.ONCHAIN_DEPLOY_PUBLIC !== 'true') throw new Error('Set ONCHAIN_DEPLOY_PUBLIC=true');
const provider = new JsonRpcProvider(rpc);
try {
  if (Number((await provider.getNetwork()).chainId) !== chainId) throw new Error('Wrong RPC chain ID');
  if (!process.env.BLOCKCHAIN_PRIVATE_KEY && !(network.local && process.env.ONCHAIN_LOCAL_UNLOCKED === 'true')) throw new Error('Set deployment key');
  const signer = new NonceManager(process.env.BLOCKCHAIN_PRIVATE_KEY
    ? new Wallet(process.env.BLOCKCHAIN_PRIVATE_KEY, provider) : await provider.getSigner());
  const recorderAddress = getAddress(process.env.OBSERVATION_RECORDER_ADDRESS || (network.local ? await signer.getAddress() : ''));
  const debugMode = process.env.OBSERVATION_DEBUG_INPUTS === 'true';
  const compiled = build(['csi_breathing_certificate']);
  const circuit = compiled.circuits[0];
  if (circuit.publicSignalCount !== 1) throw new Error('This registry requires the one-output certificate');
  const verifier = await new ContractFactory(circuit.abi, circuit.bytecode, signer).deploy();
  await verifier.waitForDeployment();
  const verifierAddress = await verifier.getAddress();
  const artifact = compile({ 'Observation.sol': { content: readFileSync(resolve(root, 'BreathingObservationRegistry.sol'), 'utf8') } })['Observation.sol'].BreathingObservationRegistry;
  const registry = await new ContractFactory(artifact.abi, '0x' + artifact.evm.bytecode.object, signer).deploy(verifierAddress, recorderAddress, debugMode);
  await registry.waitForDeployment();
  const receipt = await registry.deploymentTransaction().wait();
  const address = await registry.getAddress();
  const manifest = { version: 1, kind: 'breathing-observations', chainId, networkName: network.name,
    registryAddress: address, registryCodeHash: keccak256(await provider.getCode(address)), registryAbi: artifact.abi,
    verifierAddress, verifierCodeHash: keccak256(await provider.getCode(verifierAddress)), recorderAddress, debugMode,
    deploymentBlock: receipt.blockNumber, deploymentTransaction: receipt.hash,
    // Debug metadata stays in the off-chain manifest; no circuit name/ID is stored in observations.
    circuit: circuit.name, verificationKeyHash: circuit.verificationKeyHash, publicSignalCount: 1 };
  const output = resolve(root, `build/onchain/observations-${chainId}.json`);
  writeFileSync(output, JSON.stringify(manifest, null, 2));
  console.log(`Observation registry: ${address}\nManifest: ${output}`);
} finally { provider.destroy(); }
