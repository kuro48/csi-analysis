pragma circom 2.0.0;

include "csi_motion_selector.circom";
include "lomb_scargle_csi_core.circom";

// Research profiles only. Existing 64-point observation deployments keep their
// original main and keys. Each N here needs its own setup and ledger verifier.
template LombScargleCSIAdaptiveSamples(N, C) {
    assert(N >= 64 && N <= 128);
    signal input csiI[N][C];
    signal input csiQ[N][C];
    signal input timestampsMs[N];
    signal input candidateCount;
    signal input commitmentNonce;
    signal output csiCommitment;
    signal output isNormal;
    signal output selectedSubcarrier;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;

    component selector = CSIMotionSelector(N, C);
    selector.candidateCount <== candidateCount;
    selector.commitmentNonce <== commitmentNonce;
    for (var i = 0; i < N; i++) {
        for (var sc = 0; sc < C; sc++) {
            selector.csiI[i][sc] <== csiI[i][sc];
            selector.csiQ[i][sc] <== csiQ[i][sc];
        }
    }
    // With |I|,|Q|<=2048 and |trig|<=1024, YY<=N^3*2^46,
    // det<=N^2*2^40. The PSD Gram projection implies numerator<=det*YY.
    // Cross products <=N^10*2^172 <=2^242 at N<=128, below 246 bits.
    component lomb = LombScargleCSIEndToEnd(N, 1, 32, 5, 27, 23, 2048, 12, 1024, N <= 64 ? 236 : 246);
    lomb.commitmentNonce <== commitmentNonce;
    for (var i = 0; i < N; i++) {
        lomb.csiI[i][0] <== selector.selectedI[i];
        lomb.csiQ[i][0] <== selector.selectedQ[i];
        lomb.timestampsMs[i] <== timestampsMs[i];
    }
    csiCommitment <== selector.csiCommitment;
    isNormal <== lomb.isNormal;
    selectedSubcarrier <== selector.selectedSubcarrier;
    estimatedFrequencyBin <== lomb.estimatedFrequencyBin;
    globalPeakFrequencyBin <== lomb.globalPeakFrequencyBin;
}
