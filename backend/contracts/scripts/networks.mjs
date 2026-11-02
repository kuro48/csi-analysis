// Deployment policy for the testnet phase. Mainnets are intentionally absent.
export const NETWORKS = {
  11155111: { name: 'Ethereum Sepolia', explorerUrl: 'https://sepolia.etherscan.io', local: false },
  31337: { name: 'Local EVM', explorerUrl: '', local: true },
  1337: { name: 'Local EVM', explorerUrl: '', local: true },
};

export function deploymentNetwork(chainId) {
  const network = Number.isSafeInteger(chainId) ? NETWORKS[chainId] : undefined;
  if (!network) throw new Error('Only Ethereum Sepolia (11155111) and local EVMs (31337/1337) are enabled');
  return network;
}

export function sepoliaEnvironment(env) {
  if (env.ONCHAIN_CHAIN_ID && env.ONCHAIN_CHAIN_ID !== '11155111') {
    throw new Error('deploy:sepolia requires ONCHAIN_CHAIN_ID=11155111');
  }
  return { ...env, ONCHAIN_CHAIN_ID: '11155111', ONCHAIN_DEPLOY_PUBLIC: 'true',
    ONCHAIN_NETWORK_NAME: NETWORKS[11155111].name, ONCHAIN_EXPLORER_URL: NETWORKS[11155111].explorerUrl };
}
