# On-Chain Proof Verification (Groth16)

This guide explains how to verify `csi_full_similarity` proofs on-chain and record them for third parties.

## 1) Rebuild after public input changes

If you changed the public inputs in the circuit, you must recompile and regenerate keys:

```bash
cd zkp
npm run compile:full_similarity
npm run setup:full_similarity
```

## 2) Export Solidity verifier

```bash
cd zkp
npm run export:full_similarity:sol
```

This generates `zkp/src/CsiFullSimilarityVerifier.sol`.

## 3) Deploy contracts

### Hardhat (Ethereum/Polygon)

```bash
cd zkp/hardhat
npm install
cp .env.example .env
```

Edit `.env` with your RPC URL and private key, then:

```bash
npx hardhat compile
npx hardhat run scripts/deploy.js --network sepolia
```

This deploys in order:

1. `zkp/src/CsiFullSimilarityVerifier.sol`
2. `zkp/src/FullSimilarityProofRegistry.sol` (constructor receives verifier address)

`FullSimilarityProofRegistry` verifies proofs and stores their hashes on-chain.

## 4) Submit proofs

Call `FullSimilarityProofRegistry.submitProof(...)` with:

- `_pA`, `_pB`, `_pC`: Groth16 proof
- `_pubSignals`: `uint[247]` array (245 similarities + `minSimilarity` + `minIndex`)

The transaction verifies the proof and emits `ProofRecorded`.

## Notes

- Gas cost grows with the number of public signals. If you need cheaper verification,
  consider reducing public outputs in the circuit (e.g., only `minSimilarity` and `minIndex`).

## Backend Auto-Submit (Optional)

The backend can auto-submit proofs after generation. Configure in `backend/.env`:

```bash
ZKP_AUTO_SUBMIT=true
ZKP_SUBMIT_RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
ZKP_SUBMIT_PRIVATE_KEY=0x...
ZKP_SUBMIT_REGISTRY_ADDRESS=0x...
ZKP_SUBMIT_CHAIN_ID=11155111
```
