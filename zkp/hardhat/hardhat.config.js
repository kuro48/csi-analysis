require("dotenv").config();
require("@nomicfoundation/hardhat-ethers");

const {
  PRIVATE_KEY,
  SEPOLIA_RPC_URL,
  MAINNET_RPC_URL,
  POLYGON_RPC_URL,
  MUMBAI_RPC_URL,
} = process.env;

const accounts = PRIVATE_KEY ? [PRIVATE_KEY] : [];

module.exports = {
  solidity: "0.8.17",
  paths: {
    sources: "../src",
    artifacts: "./artifacts",
    cache: "./cache",
  },
  networks: {
    sepolia: {
      url: SEPOLIA_RPC_URL || "",
      accounts,
    },
    mainnet: {
      url: MAINNET_RPC_URL || "",
      accounts,
    },
    polygon: {
      url: POLYGON_RPC_URL || "",
      accounts,
    },
    mumbai: {
      url: MUMBAI_RPC_URL || "",
      accounts,
    },
  },
};
