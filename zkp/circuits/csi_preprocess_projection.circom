pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/poseidon.circom";

/*
 * Phase-2 incremental preprocessor verifier.
 *
 * It proves an exact fixed-point PCA projection for a 32x8 reduced witness.
 * SNR selection, filtering, and maximal-eigenvector verification remain outside
 * this circuit and are explicitly reported as an unproved prefix.
 */
template PreprocessProjection(T, N) {
    signal input centeredX[T][N];
    signal input weights[N];
    signal input commitmentNonce;
    signal input inputCommitment;
    signal output projectionCommitment;

    component inputSeed = Poseidon(3);
    inputSeed.inputs[0] <== 1129531650; // 0x43534902
    inputSeed.inputs[1] <== commitmentNonce;
    inputSeed.inputs[2] <== 1;

    signal inputMetadataState[5];
    inputMetadataState[0] <== inputSeed.out;
    var inputMetadata[4] = [T, N, 128, 128];
    component inputMetadataHash[4];
    for (var metadataIndex = 0; metadataIndex < 4; metadataIndex++) {
        inputMetadataHash[metadataIndex] = Poseidon(2);
        inputMetadataHash[metadataIndex].inputs[0] <== inputMetadataState[metadataIndex];
        inputMetadataHash[metadataIndex].inputs[1] <== inputMetadata[metadataIndex];
        inputMetadataState[metadataIndex + 1] <== inputMetadataHash[metadataIndex].out;
    }

    component matrixBits[T][N];
    component matrixHash[T * N];
    signal matrixState[T * N + 1];
    matrixState[0] <== inputMetadataState[4];
    for (var t = 0; t < T; t++) {
        for (var n = 0; n < N; n++) {
            var position = t * N + n;
            matrixBits[t][n] = Num2Bits(8);
            matrixBits[t][n].in <== centeredX[t][n] + 128;
            matrixHash[position] = Poseidon(2);
            matrixHash[position].inputs[0] <== matrixState[position];
            matrixHash[position].inputs[1] <== centeredX[t][n] + 128;
            matrixState[position + 1] <== matrixHash[position].out;
        }
    }

    component weightBits[N];
    component weightHash[N];
    signal weightState[N + 1];
    weightState[0] <== matrixState[T * N];
    for (var n = 0; n < N; n++) {
        weightBits[n] = Num2Bits(8);
        weightBits[n].in <== weights[n] + 128;
        weightHash[n] = Poseidon(2);
        weightHash[n].inputs[0] <== weightState[n];
        weightHash[n].inputs[1] <== weights[n] + 128;
        weightState[n + 1] <== weightHash[n].out;
    }
    weightState[N] === inputCommitment;

    signal projected[T];
    signal projectionTerm[T][N];
    signal projectionPartial[T][N];
    for (var t = 0; t < T; t++) {
        projectionTerm[t][0] <== centeredX[t][0] * weights[0];
        projectionPartial[t][0] <== projectionTerm[t][0];
        for (var n = 1; n < N; n++) {
            projectionTerm[t][n] <== centeredX[t][n] * weights[n];
            projectionPartial[t][n] <== projectionPartial[t][n - 1] + projectionTerm[t][n];
        }
        projected[t] <== projectionPartial[t][N - 1];
    }

    component outputSeed = Poseidon(3);
    outputSeed.inputs[0] <== 1129531651; // 0x43534903
    outputSeed.inputs[1] <== commitmentNonce;
    outputSeed.inputs[2] <== 1;
    component outputLengthHash = Poseidon(2);
    outputLengthHash.inputs[0] <== outputSeed.out;
    outputLengthHash.inputs[1] <== T;
    component outputOffsetHash = Poseidon(2);
    outputOffsetHash.inputs[0] <== outputLengthHash.out;
    outputOffsetHash.inputs[1] <== 131072;

    component projectedBits[T];
    component projectedHash[T];
    signal projectedState[T + 1];
    projectedState[0] <== outputOffsetHash.out;
    for (var t = 0; t < T; t++) {
        projectedBits[t] = Num2Bits(18);
        projectedBits[t].in <== projected[t] + 131072;
        projectedHash[t] = Poseidon(2);
        projectedHash[t].inputs[0] <== projectedState[t];
        projectedHash[t].inputs[1] <== projected[t] + 131072;
        projectedState[t + 1] <== projectedHash[t].out;
    }
    projectionCommitment <== projectedState[T];
}

component main {public [inputCommitment]} = PreprocessProjection(32, 8);
