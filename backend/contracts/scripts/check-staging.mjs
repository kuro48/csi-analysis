// Read-only RPC check. Never loads private keys or sends transactions.
import { JsonRpcProvider, formatEther } from "ethers";
import { writeFileSync } from "node:fs";
const provider = new JsonRpcProvider(process.env.ADAPTIVE_ETHEREUM_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com");
const result = { checkedAt: new Date().toISOString(), target: "sepolia", readOnly: true, deploymentChecked: false };
try {
  const network = await provider.getNetwork();
  result.chainId = Number(network.chainId);
  if (result.chainId !== 11155111) throw Error("Wrong chain");
  result.blockNumber = await provider.getBlockNumber();
  result.wallets = await Promise.all([
    ["deployer", process.env.DEPLOYER_ADDRESS || "0xec77D2B256e1c9079CbA30869ca74bBFBb28C32f"],
    ["recorder", process.env.RECORDER_ADDRESS || "0xbe0EEc5d93231938Cf743a792516fbb103B48651"],
  ].map(async ([role, address]) => ({ role, address, testETH: formatEther(await provider.getBalance(address)) })));
  result.funded = result.wallets.every(wallet => Number(wallet.testETH) > 0);
  if (!result.funded) { result.blocker = "Fund both wallets with Sepolia test ETH"; process.exitCode = 2; }
} catch {
  result.blocker = "Sepolia RPC unavailable or chain mismatch";
  process.exitCode = 1;
} finally { provider.destroy(); }
const serialized = JSON.stringify(result, null, 2) + "\n";
if (process.argv[2]) writeFileSync(process.argv[2], serialized);
console.log(serialized);
