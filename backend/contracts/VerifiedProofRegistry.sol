// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Immutable, permissionless registry. A record can only be created by a
/// successful Groth16 verifier call in the SAME transaction. No admin override.
/// Public signals and proof calldata are public; never submit raw CSI or identifiers.
contract VerifiedProofRegistry {
    uint256 constant SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617;

    struct Circuit {
        address verifier;
        bytes4 selector;
        uint32 publicSignalCount;
        bytes32 verificationKeyHash;
        bytes32 codeHash;
    }
    struct Record {
        bytes32 circuitId;
        bytes32 statementHash;
        address submitter;
        uint64 timestamp;
        uint64 blockNumber;
    }
    mapping(bytes32 => Circuit) public circuits;
    mapping(bytes32 => Record) public records;
    uint256 public totalVerified;

    event ProofVerified(bytes32 indexed proofId, bytes32 indexed circuitId, address indexed submitter, bytes32 statementHash);
    error InvalidConfiguration();
    error InvalidProof();
    error AlreadyVerified(bytes32 proofId);

    constructor(bytes32[] memory ids, Circuit[] memory configs) {
        if (ids.length == 0 || ids.length != configs.length) revert InvalidConfiguration();
        for (uint256 i; i < ids.length; ++i) {
            Circuit memory c = configs[i];
            if (ids[i] == bytes32(0) || circuits[ids[i]].verifier != address(0) ||
                c.verifier.code.length == 0 || c.verifier.codehash != c.codeHash ||
                c.publicSignalCount == 0 || c.publicSignalCount > 256 ||
                c.verificationKeyHash == bytes32(0)) revert InvalidConfiguration();
            circuits[ids[i]] = c;
        }
    }

    /// @dev The ID includes the proof, circuit and public signals. Identical proofs
    /// cannot be replayed; distinct captures with identical boolean outputs can coexist.
    function verifyAndRecord(bytes32 circuitId, uint256[2] calldata a,
        uint256[2][2] calldata b, uint256[2] calldata c, uint256[] calldata signals)
        external returns (bytes32 proofId)
    {
        Circuit memory circuit = circuits[circuitId];
        if (circuit.verifier == address(0) || signals.length != circuit.publicSignalCount ||
            circuit.verifier.codehash != circuit.codeHash) revert InvalidProof();
        for (uint256 i; i < signals.length; ++i) {
            if (signals[i] >= SCALAR_FIELD) revert InvalidProof();
        }
        proofId = keccak256(abi.encode(circuitId, a, b, c, signals));
        if (records[proofId].submitter != address(0)) revert AlreadyVerified(proofId);
        // snarkjs verifier expects a FIXED public input array: no ABI offset or length.
        bytes memory payload = abi.encodePacked(circuit.selector, abi.encode(a, b, c), abi.encodePacked(signals));
        (bool success, bytes memory result) = circuit.verifier.staticcall(payload);
        if (!success || result.length != 32 || !abi.decode(result, (bool))) revert InvalidProof();
        bytes32 statementHash = keccak256(abi.encode(circuitId, signals));
        records[proofId] = Record(circuitId, statementHash, msg.sender, uint64(block.timestamp), uint64(block.number));
        ++totalVerified;
        emit ProofVerified(proofId, circuitId, msg.sender, statementHash);
    }
}
