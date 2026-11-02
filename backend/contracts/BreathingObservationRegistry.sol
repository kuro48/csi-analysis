// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IBreathingVerifier {
    function verifyProof(uint256[2] calldata a, uint256[2][2] calldata b,
        uint256[2] calldata c, uint256[1] calldata signals) external view returns (bool);
}

/// @notice Record first, verify on read. Patient/time metadata is attested by
/// the recorder, NOT proven by the breathing circuit. Public chain, no secrecy.
contract BreathingObservationRegistry {
    IBreathingVerifier public immutable verifier;
    bytes32 public immutable verifierCodeHash;
    address public immutable recorder;
    bool public immutable debugMode;

    struct Observation {
        bytes32 patientRef;
        uint64 observedAt;
        uint32 durationSeconds;
        uint64 recordedBlock;
        bytes32 proofDigest;
        uint256[2] a;
        uint256[2][2] b;
        uint256[2] c;
        uint256[1] signals;
    }
    mapping(bytes32 => Observation) private observations;
    mapping(bytes32 => bool) private usedProofs;
    event ObservationRecorded(bytes32 indexed observationId, bytes32 indexed patientRef, uint64 observedAt);
    error Unauthorized();
    error InvalidObservation();
    error Duplicate();
    error InvalidProof();

    constructor(address verifierAddress, address recorderAddress, bool allowDebugInputs) {
        if (verifierAddress.code.length == 0 || recorderAddress == address(0)) revert InvalidObservation();
        verifier = IBreathingVerifier(verifierAddress);
        verifierCodeHash = verifierAddress.codehash;
        recorder = recorderAddress;
        debugMode = allowDebugInputs;
    }

    function recordObservation(bytes32 observationId, bytes32 patientRef,
        uint64 observedAt, uint32 durationSeconds, uint256[2] calldata a,
        uint256[2][2] calldata b, uint256[2] calldata c, uint256[1] calldata signals) external {
        if (msg.sender != recorder) revert Unauthorized();
        if (observationId == bytes32(0) || patientRef == bytes32(0) || observedAt == 0 ||
            durationSeconds == 0 || durationSeconds > 3600 ||
            uint256(observedAt) + durationSeconds > block.timestamp + 300 || signals[0] > 1)
            revert InvalidObservation();
        bytes32 digest = keccak256(abi.encode(a, b, c, signals));
        if (observations[observationId].recordedBlock != 0 || usedProofs[digest]) revert Duplicate();
        // Deliberately no verifier call here. A recorded proof is not a verified result.
        observations[observationId] = Observation(patientRef, observedAt, durationSeconds,
            uint64(block.number), digest, a, b, c, signals);
        usedProofs[digest] = true;
        emit ObservationRecorded(observationId, patientRef, observedAt);
    }

    function getObservation(bytes32 observationId) external view returns
        (bytes32 patientRef, uint64 observedAt, uint32 durationSeconds, uint64 recordedBlock, bytes32 proofDigest) {
        Observation storage item = observations[observationId];
        return (item.patientRef, item.observedAt, item.durationSeconds, item.recordedBlock, item.proofDigest);
    }

    /// @notice A boolean is returned ONLY after the stored proof passes verification.
    /// Invalid/missing proofs revert; false means a valid proof with output zero.
    function verifyObservation(bytes32 observationId) external view returns (bool isNormal) {
        Observation storage item = observations[observationId];
        if (item.recordedBlock == 0 || address(verifier).codehash != verifierCodeHash) revert InvalidProof();
        if (!verifier.verifyProof(item.a, item.b, item.c, item.signals)) revert InvalidProof();
        return item.signals[0] == 1;
    }
}
