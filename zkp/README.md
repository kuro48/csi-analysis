# CSI Breathing Rate ZKP Circuit

Zero-Knowledge Proof (ZKP) implementation for verifying CSI-based breathing rate analysis without revealing raw CSI data.

## Overview

This circuit implements a simplified verification system for breathing rate extraction from CSI (Channel State Information) data using zero-knowledge proofs. The implementation uses:

- **Circuit Language**: circom 2.0
- **Proof System**: Groth16 (via snarkjs)
- **Hash Function**: Poseidon
- **Curve**: bn128

## Features

The ZKP circuit verifies the following properties:

1. **CSI Data Commitment**: Proves knowledge of CSI data matching a public commitment (Poseidon hash)
2. **Breathing Rate Range**: Validates breathing rate is within 0-50 bpm
3. **Frequency-Rate Consistency**: Verifies breathing frequency and rate are mathematically consistent
4. **Confidence Threshold**: Ensures confidence score is above 70%
5. **Amplitude Validity**: Checks all CSI amplitude values are within valid range (0-10000)

## Installation

### Prerequisites

- Node.js 16+
- circom 2.0+
- snarkjs 0.7+

### Install Dependencies

```bash
cd zkp
npm install
```

### Install circom

```bash
# On macOS
brew install circom

# On Linux
git clone https://github.com/iden3/circom.git
cd circom
cargo build --release
cargo install --path circom
```

## Usage

### 1. Compile Circuit

Compile the circom circuit to generate R1CS, WASM, and symbol files:

```bash
npm run compile
```

This generates:
- `build/breathing_verifier.r1cs` - Rank-1 Constraint System
- `build/breathing_verifier_js/` - WebAssembly files
- `build/breathing_verifier.sym` - Symbol file

### 2. Setup (Powers of Tau + zKey Generation)

Download Powers of Tau ceremony file and generate proving/verification keys:

```bash
npm run setup
```

This will:
1. Download Powers of Tau file (~200MB) from Hermez
2. Generate zKey (proving key)
3. Export verification key (JSON)
4. Generate Solidity verifier contract

Generated files:
- `keys/powersOfTau28_hez_final_15.ptau` - Powers of Tau
- `keys/breathing_verifier.zkey` - Proving key
- `keys/breathing_verifier_verification_key.json` - Verification key
- `keys/breathing_verifier_verifier.sol` - Solidity verifier contract

### 3. Generate Proof

Generate a zero-knowledge proof using sample data:

```bash
npm run prove
```

This generates:
- `build/proof.json` - The ZK proof
- `build/public.json` - Public inputs
- `build/witness.wtns` - Witness file

### 4. Verify Proof

Verify the generated proof:

```bash
npm run verify
```

Expected output:
```
✅ Proof is VALID! (verified in 0.XXXs)

📋 Public Inputs:
   CSI Commitment: 12345678901234567890
   Breathing Rate: 15 bpm
   Confidence Score: 85 %
   Timestamp: 1234567890
```

### 5. Run Tests

Run the test suite:

```bash
npm test
```

Tests cover:
- Valid input scenarios
- Boundary conditions
- Invalid input rejection
- Performance benchmarks

## Circuit Specifications

### Public Inputs

| Input | Type | Description |
|-------|------|-------------|
| `csiCommitment` | Field | Poseidon hash of CSI data + salt |
| `breathingRate` | Field | Breathing rate (0-50 bpm) |
| `confidenceScore` | Field | Confidence score (0-100%) |
| `timestamp` | Field | Unix timestamp |

### Private Inputs

| Input | Type | Description |
|-------|------|-------------|
| `csiData[64]` | Field[] | CSI amplitude time series (64 samples) |
| `breathingFrequency` | Field | Breathing frequency in Hz × 1000 |
| `salt` | Field | Random salt for commitment |

### Output

| Output | Type | Description |
|--------|------|-------------|
| `isValid` | Field | 1 if all validations pass, 0 otherwise |

### Constraints

Estimated circuit constraints: ~10,000

This makes it practical for Groth16 proof system with target proof generation time < 10 seconds.

## Integration with Backend

### Python Integration

Example Python code for backend integration:

```python
import subprocess
import json
from typing import Dict, List

class ZKPProofGenerator:
    def __init__(self, zkp_dir: str):
        self.zkp_dir = zkp_dir

    async def generate_proof(
        self,
        csi_data: List[float],
        breathing_rate: float,
        confidence_score: float,
        timestamp: int
    ) -> Dict:
        """Generate ZKP for breathing rate analysis"""

        # 1. Prepare input
        input_data = {
            "csiData": [int(x) for x in csi_data[:64]],
            "breathingRate": int(breathing_rate),
            "confidenceScore": int(confidence_score * 100),
            "timestamp": timestamp,
            "breathingFrequency": int(breathing_rate / 60 * 1000),
            "salt": random.randint(0, 1000000)
        }

        # 2. Calculate commitment
        commitment = self._calculate_commitment(
            input_data["csiData"],
            input_data["salt"]
        )
        input_data["csiCommitment"] = commitment

        # 3. Generate proof (call Node.js script)
        proof, public_signals = await self._call_prove_script(input_data)

        return {
            "proof": proof,
            "publicSignals": public_signals,
            "commitment": commitment
        }
```

### API Endpoint

Example FastAPI endpoint:

```python
@router.post("/breathing-analysis/{session_id}/zkp")
async def generate_zkp_proof(
    session_id: str,
    zkp_service: ZKPService = Depends()
):
    """Generate ZKP for breathing analysis result"""

    # Get breathing analysis result
    result = await breathing_service.get_latest_result(session_id)

    # Generate ZKP
    proof_data = await zkp_service.generate_proof(
        csi_data=result.csi_amplitude_series,
        breathing_rate=result.breathing_rate,
        confidence_score=result.confidence,
        timestamp=result.timestamp
    )

    # Store proof on blockchain (optional)
    tx_hash = await blockchain_service.submit_proof(proof_data)

    return {
        "proof": proof_data["proof"],
        "publicSignals": proof_data["publicSignals"],
        "transactionHash": tx_hash
    }
```

## Performance Targets

- **Proof Generation**: < 10 seconds
- **Proof Verification**: < 1 second
- **Proof Size**: ~200 bytes
- **Verification Key Size**: ~1 KB

## Security Considerations

1. **Privacy**: Raw CSI data is never revealed, only commitment is public
2. **Integrity**: Proof guarantees the claimed breathing rate is consistent with hidden CSI data
3. **Non-Repudiation**: Proof is cryptographically bound to specific CSI data
4. **Trust Assumptions**:
   - Trusted setup (Powers of Tau ceremony)
   - Off-chain FFT computation is trusted
   - Peak detection logic is trusted

## Future Enhancements

1. **Full FFT Verification**: Include complete FFT computation in circuit (higher constraints)
2. **Multi-Session Proofs**: Batch multiple breathing measurements in single proof
3. **Recursive Proofs**: Enable proof composition for complex workflows
4. **Hardware Acceleration**: Optimize proof generation with GPU/FPGA

## References

- [circom Documentation](https://docs.circom.io/)
- [snarkjs Repository](https://github.com/iden3/snarkjs)
- [Groth16 Paper](https://eprint.iacr.org/2016/260.pdf)
- [Poseidon Hash](https://eprint.iacr.org/2019/458.pdf)

## License

MIT
