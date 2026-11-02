import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deploymentNetwork, sepoliaEnvironment } from '../scripts/networks.mjs';

test('testnet policy rejects mainnet and unknown chains before connecting', () => {
  for (const chainId of [1, 10, 137, 8453, 42161, 0, NaN, '11155111']) {
    assert.throws(() => deploymentNetwork(chainId), /Only Ethereum Sepolia/);
  }
  assert.equal(deploymentNetwork(11155111).name, 'Ethereum Sepolia');
  assert.equal(deploymentNetwork(31337).local, true);
  assert.equal(deploymentNetwork(1337).local, true);
});

test('Sepolia entrypoint pins the chain without silently overriding another target', () => {
  assert.throws(() => sepoliaEnvironment({ ONCHAIN_CHAIN_ID: '1' }), /11155111/);
  assert.equal(sepoliaEnvironment({}).ONCHAIN_CHAIN_ID, '11155111');
  assert.equal(sepoliaEnvironment({}).ONCHAIN_EXPLORER_URL, 'https://sepolia.etherscan.io');
  assert.equal(sepoliaEnvironment({ ETHEREUM_RPC_URL: 'https://rpc.example' }).ETHEREUM_RPC_URL, 'https://rpc.example');
});
