pragma circom 2.0.0;
include "lomb_scargle_timestamp_basis.circom";

// Research-only grid; reuse constrained integer trigonometric primitives.
template LombTimestampBasisGrid(SAMPLES, FREQS, ANCHOR_INTERVAL, PERIOD, START, STEP, PERIOD_BITS) {
    signal input timestampsMs[SAMPLES];
    signal output cosBasis[FREQS][SAMPLES];
    signal output sinBasis[FREQS][SAMPLES];

    component step[SAMPLES];
    for (var i=0; i<SAMPLES; i++) {
        step[i] = LombApproxSinCos(PERIOD, STEP, PERIOD_BITS);
        step[i].timeMs <== timestampsMs[i];
    }

    var ANCHORS = (FREQS + ANCHOR_INTERVAL - 1) \ ANCHOR_INTERVAL;
    component anchors[ANCHORS][SAMPLES];
    component rotations[FREQS-ANCHORS][SAMPLES];
    var rotationIndex = 0;
    for (var f=0; f<FREQS; f++) {
        for (var i=0; i<SAMPLES; i++) {
            if (f % ANCHOR_INTERVAL == 0) {
                anchors[f \ ANCHOR_INTERVAL][i] = LombApproxSinCos(PERIOD, START + STEP*f, PERIOD_BITS);
                anchors[f \ ANCHOR_INTERVAL][i].timeMs <== timestampsMs[i];
                cosBasis[f][i] <== anchors[f \ ANCHOR_INTERVAL][i].cosEncoded;
                sinBasis[f][i] <== anchors[f \ ANCHOR_INTERVAL][i].sinEncoded;
            } else {
                rotations[rotationIndex][i] = LombRotateTrig();
                rotations[rotationIndex][i].cosCurrent <== cosBasis[f-1][i];
                rotations[rotationIndex][i].sinCurrent <== sinBasis[f-1][i];
                rotations[rotationIndex][i].cosStep <== step[i].cosEncoded;
                rotations[rotationIndex][i].sinStep <== step[i].sinEncoded;
                cosBasis[f][i] <== rotations[rotationIndex][i].cosNext;
                sinBasis[f][i] <== rotations[rotationIndex][i].sinNext;
            }
        }
        if (f % ANCHOR_INTERVAL != 0) {
            rotationIndex++;
        }
    }
}
