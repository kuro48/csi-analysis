import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JsonRpcProvider, Wallet, ContractFactory, keccak256, NonceManager } from 'ethers';
import { root } from './build.mjs';
import { deploymentNetwork } from './networks.mjs';

// Explicit network + explicit signer. Never fall back to an unlocked public RPC account.
const rpc = process.env.ETHEREUM_RPC_URL;
const expected = Number(process.env.ONCHAIN_CHAIN_ID);
if (!rpc || !Number.isSafeInteger(expected) || expected <= 0) throw new Error('Set ETHEREUM_RPC_URL and ONCHAIN_CHAIN_ID');
const network = deploymentNetwork(expected);
const local = network.local;
if (!local && process.env.ONCHAIN_DEPLOY_PUBLIC !== 'true') throw new Error('Set ONCHAIN_DEPLOY_PUBLIC=true to deploy to a public testnet');
if (!process.env.BLOCKCHAIN_PRIVATE_KEY && !(local && process.env.ONCHAIN_LOCAL_UNLOCKED === 'true')) throw new Error('Set BLOCKCHAIN_PRIVATE_KEY');
const provider = new JsonRpcProvider(rpc);
if (Number((await provider.getNetwork()).chainId) !== expected) throw new Error('Wrong RPC chain ID');
const signer = new NonceManager(process.env.BLOCKCHAIN_PRIVATE_KEY ? new Wallet(process.env.BLOCKCHAIN_PRIVATE_KEY, provider) : await provider.getSigner());
const build = JSON.parse(readFileSync(resolve(root, 'build/onchain/compiled.json')));
const circuits = [];
for (const circuit of build.circuits) {
  const verifier = await new ContractFactory(circuit.abi, circuit.bytecode, signer).deploy();
  await verifier.waitForDeployment();
  const address = await verifier.getAddress();
  const { bytecode, abi, ...metadata } = circuit;
  circuits.push({ ...metadata, address, codeHash: keccak256(await provider.getCode(address)) });
}
const registry = await new ContractFactory(build.registry.abi, build.registry.bytecode, signer).deploy(
  circuits.map(c => c.circuitId), circuits.map(c => [c.address, c.selector, c.publicSignalCount, c.verificationKeyHash, c.codeHash]));
await registry.waitForDeployment();
const receipt = await registry.deploymentTransaction().wait();
const registryAddress = await registry.getAddress();
const manifest = { version: 1, chainId: expected, networkName: network.name,
  explorerUrl: network.explorerUrl, registryAddress,
  registryCodeHash: keccak256(await provider.getCode(registryAddress)), deploymentBlock: receipt.blockNumber,
  deploymentTransaction: receipt.hash, circuits, registryAbi: build.registry.abi };
const output = resolve(root, `build/onchain/deployment-${expected}.json`);
writeFileSync(output, JSON.stringify(manifest, null, 2));
console.log(`Deployed: ${registryAddress}\nManifest: ${output}\nSet ONCHAIN_MANIFEST=${output}`);
provider.destroy();
