// Run with --env-file-if-exists=.env.sepolia.local from the repository root.
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { Wallet, JsonRpcProvider, formatEther } from 'ethers';

const root = resolve(import.meta.dirname, '../../..');
if (process.env.ONCHAIN_CHAIN_ID && process.env.ONCHAIN_CHAIN_ID !== '11155111') throw Error('Sepolia only');
const load = filename => {
  if (statSync(filename).mode & 0o077) throw Error('Key files must have mode 0600');
  return readFileSync(filename, 'utf8').trim();
};
const keyPath = process.env.ADAPTIVE_SEPOLIA_DEPLOYER_KEY_FILE || resolve(root, '.local/sepolia-adaptive/deployer.key');
const recorderPath = process.env.ADAPTIVE_RECORDER_KEY_FILE || resolve(root, '.local/sepolia-adaptive/recorder.key');
const key = load(keyPath);
const deployer = new Wallet(key);
const recorder = new Wallet(load(recorderPath));
const rpc = process.env.ETHEREUM_RPC_URL || 'https://ethereum-sepolia-rpc.publicnode.com';
const provider = new JsonRpcProvider(rpc);
try {
  if (Number((await provider.getNetwork()).chainId) !== 11155111) throw Error('Wrong RPC chain');
  const balance = await provider.getBalance(deployer.address);
  const recorderBalance = await provider.getBalance(recorder.address);
  console.log(JSON.stringify({ chainId: 11155111, deployer: deployer.address, deployerTestEth: formatEther(balance), recorder: recorder.address, recorderTestEth: formatEther(recorderBalance) }));
  if (balance === 0n || recorderBalance === 0n) throw Error('Fund both addresses with Sepolia test ETH before deployment');
} finally { provider.destroy(); }
Object.assign(process.env, {
  ETHEREUM_RPC_URL: rpc, BLOCKCHAIN_PRIVATE_KEY: key, ONCHAIN_CHAIN_ID: '11155111', ONCHAIN_DEPLOY_PUBLIC: 'true',
  OBSERVATION_RECORDER_ADDRESS: recorder.address,
  ADAPTIVE_ARTIFACT_MANIFEST: process.env.ADAPTIVE_ARTIFACT_MANIFEST || resolve(root, '.local/circom-adaptive-4004/artifacts.json'),
  ADAPTIVE_DEPLOY_DIR: process.env.ADAPTIVE_DEPLOY_DIR || resolve(root, '.local/adaptive-evm/11155111'),
});
await import('./deploy-adaptive-observations.mjs');
