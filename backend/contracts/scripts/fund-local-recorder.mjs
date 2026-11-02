import { JsonRpcProvider, parseEther } from 'ethers';
const rpc = process.env.ETHEREUM_RPC_URL;
const url = new URL(rpc);
if (!['127.0.0.1', 'localhost'].includes(url.hostname)) throw new Error('Only loopback RPC allowed');
const provider = new JsonRpcProvider(rpc);
try {
  if (Number((await provider.getNetwork()).chainId) !== 31337) throw new Error('Only local chain 31337 allowed');
  const signer = await provider.getSigner();
  await (await signer.sendTransaction({ to: process.env.OBSERVATION_RECORDER_ADDRESS, value: parseEther('1') })).wait();
  console.log('Funded local test recorder. No public network used.');
} finally { provider.destroy(); }
