const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deployer:", deployer.address);

  const Verifier = await ethers.getContractFactory("CsiFullSimilarityVerifier");
  const verifier = await Verifier.deploy();
  await verifier.waitForDeployment();
  const verifierAddress = await verifier.getAddress();
  console.log("CsiFullSimilarityVerifier:", verifierAddress);

  const Registry = await ethers.getContractFactory("FullSimilarityProofRegistry");
  const registry = await Registry.deploy(verifierAddress);
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();
  console.log("FullSimilarityProofRegistry:", registryAddress);

  if (process.env.DEPLOY_OUTPUT) {
    const fs = require("fs");
    const payload = {
      verifier: verifierAddress,
      registry: registryAddress,
      network: (await ethers.provider.getNetwork()).name,
    };
    fs.writeFileSync(process.env.DEPLOY_OUTPUT, JSON.stringify(payload, null, 2));
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
