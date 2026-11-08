pragma circom 2.0.0;

include "csi_motion_selector.circom";
include "lomb_scargle_csi_core.circom";

template LombScargleCSIAdaptive(CANDIDATES) {
    signal input csiI[64][CANDIDATES];
    signal input csiQ[64][CANDIDATES];
    signal input timestampsMs[64];
    signal input candidateCount;
    signal input commitmentNonce;
    signal output csiCommitment;
    signal output isNormal;
    signal output selectedSubcarrier;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;

    component selector = CSIMotionSelector(64, CANDIDATES);
    selector.candidateCount <== candidateCount;
    selector.commitmentNonce <== commitmentNonce;
    for (var i = 0; i < 64; i++) {
        for (var sc = 0; sc < CANDIDATES; sc++) {
            selector.csiI[i][sc] <== csiI[i][sc];
            selector.csiQ[i][sc] <== csiQ[i][sc];
        }
    }
    // Compute the full spectrum only for the in-circuit winner.
    component lomb = LombScargleCSIEndToEnd(64, 1, 32, 5, 27, 23, 2048, 12, 1024, 236);
    lomb.commitmentNonce <== commitmentNonce;
    for (var i = 0; i < 64; i++) {
        lomb.csiI[i][0] <== selector.selectedI[i];
        lomb.csiQ[i][0] <== selector.selectedQ[i];
        lomb.timestampsMs[i] <== timestampsMs[i];
    }
    csiCommitment <== selector.csiCommitment;
    selectedSubcarrier <== selector.selectedSubcarrier;
    isNormal <== lomb.isNormal;
    estimatedFrequencyBin <== lomb.estimatedFrequencyBin;
    globalPeakFrequencyBin <== lomb.globalPeakFrequencyBin;
}
