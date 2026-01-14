// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

interface ICsiFullSimilarityVerifier {
    function verifyProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[247] calldata _pubSignals
    ) external view returns (bool);
}

contract FullSimilarityProofRegistry {
    // 245 subcarriers + 2 outputs (minSimilarity, minIndex)
    uint256 public constant NUM_PUBLIC_SIGNALS = 247;

    ICsiFullSimilarityVerifier public immutable verifier;
    mapping(bytes32 => bool) public recordedProofs;

    event ProofRecorded(bytes32 proofHash, address indexed submitter, uint256 minSimilarity, uint256 minIndex);

    constructor(address verifierAddress) {
        require(verifierAddress != address(0), "verifier required");
        verifier = ICsiFullSimilarityVerifier(verifierAddress);
    }

    function submitProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[NUM_PUBLIC_SIGNALS] calldata _pubSignals
    ) external returns (bytes32 proofHash) {
        bool ok = verifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        require(ok, "invalid proof");

        proofHash = keccak256(abi.encodePacked(_pA, _pB, _pC, _pubSignals));
        require(!recordedProofs[proofHash], "already recorded");
        recordedProofs[proofHash] = true;

        uint256 minSimilarity = _pubSignals[NUM_PUBLIC_SIGNALS - 2];
        uint256 minIndex = _pubSignals[NUM_PUBLIC_SIGNALS - 1];

        emit ProofRecorded(proofHash, msg.sender, minSimilarity, minIndex);
    }
}
