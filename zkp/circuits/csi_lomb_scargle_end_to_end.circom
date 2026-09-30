pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/poseidon.circom";
include "lomb_scargle_timestamp_basis.circom";

/**
 * End-to-end private-CSI Lomb--Scargle breathing estimator.
 *
 * Private inputs:
 *   csiI/csiQ       signed CSI components encoded with CSI_OFFSET
 *   commitmentNonce random field element used to salt the CSI commitment
 *
 * Public input:
 *   timestampsMs    strictly increasing relative capture timestamps
 *
 * Public outputs:
 *   csiCommitment          Poseidon chain binding every private I/Q sample
 *   selectedSubcarrier     subcarrier with the strongest normal-band score
 *   estimatedFrequencyBin  its strongest normal-band bin
 *   globalPeakFrequencyBin its strongest bin across the full search grid
 *   isNormal               1 iff the global peak is in 6--22 BPM
 *
 * No CSI value, amplitude, centered waveform, projection, or spectrum is
 * exposed. Magnitude-squared is used instead of sqrt(I^2+Q^2), avoiding an
 * unnecessary square-root witness while retaining amplitude modulation.
 *
 * The frequency grid is shared with LombTimestampBasis:
 *   frequency(bin) = (127 + 29*bin) / 2540 Hz.
 */
template LombScargleCSIEndToEnd(
    SAMPLE_COUNT,
    SUBCARRIERS,
    FREQS,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN,
    NORMAL_BINS,
    CSI_OFFSET,
    CSI_BITS,
    TRIG_OFFSET,
    RATIO_BITS
) {
    signal input csiI[SAMPLE_COUNT][SUBCARRIERS];
    signal input csiQ[SAMPLE_COUNT][SUBCARRIERS];
    signal input commitmentNonce;
    signal input timestampsMs[SAMPLE_COUNT];

    signal output csiCommitment;
    signal output isNormal;
    signal output selectedSubcarrier;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;

    // Timestamps are public but fully constrained: 24-bit, relative to zero,
    // and strictly increasing. This prevents a prover from using a degenerate
    // or reordered time axis.
    timestampsMs[0] === 0;
    component timestampBits[SAMPLE_COUNT];
    component timestampIncreasing[SAMPLE_COUNT - 1];
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        timestampBits[i] = Num2Bits(24);
        timestampBits[i].in <== timestampsMs[i];
        if (i > 0) {
            timestampIncreasing[i - 1] = LessThan(24);
            timestampIncreasing[i - 1].in[0] <== timestampsMs[i - 1];
            timestampIncreasing[i - 1].in[1] <== timestampsMs[i];
            timestampIncreasing[i - 1].out === 1;
        }
    }

    component timestampBasis = LombTimestampBasis(SAMPLE_COUNT, FREQS, 16);
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        timestampBasis.timestampsMs[i] <== timestampsMs[i];
    }

    // Range-constrain the encoded signed I/Q values and commit to them in a
    // canonical sample-major/subcarrier-major order. The private nonce makes
    // offline dictionary attacks against small synthetic captures impractical.
    component iBits[SAMPLE_COUNT][SUBCARRIERS];
    component qBits[SAMPLE_COUNT][SUBCARRIERS];
    component commitmentStep[SAMPLE_COUNT * SUBCARRIERS];
    signal commitmentState[SAMPLE_COUNT * SUBCARRIERS + 1];
    commitmentState[0] <== commitmentNonce;
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        for (var sc = 0; sc < SUBCARRIERS; sc++) {
            var position = i * SUBCARRIERS + sc;
            iBits[i][sc] = Num2Bits(CSI_BITS);
            qBits[i][sc] = Num2Bits(CSI_BITS);
            iBits[i][sc].in <== csiI[i][sc];
            qBits[i][sc].in <== csiQ[i][sc];

            commitmentStep[position] = Poseidon(3);
            commitmentStep[position].inputs[0] <== commitmentState[position];
            commitmentStep[position].inputs[1] <== csiI[i][sc];
            commitmentStep[position].inputs[2] <== csiQ[i][sc];
            commitmentState[position + 1] <== commitmentStep[position].out;
        }
    }
    csiCommitment <== commitmentState[SAMPLE_COUNT * SUBCARRIERS];

    // Compute magnitude squared and exact zero-mean signals without division:
    // centered = SAMPLE_COUNT * magnitudeSquared - sum(magnitudeSquared).
    // Scaling every sample by the same constant does not change the normalized
    // Lomb--Scargle score.
    signal signedI[SAMPLE_COUNT][SUBCARRIERS];
    signal signedQ[SAMPLE_COUNT][SUBCARRIERS];
    signal iSquared[SAMPLE_COUNT][SUBCARRIERS];
    signal qSquared[SAMPLE_COUNT][SUBCARRIERS];
    signal magnitudeSquared[SAMPLE_COUNT][SUBCARRIERS];
    signal magnitudeSum[SUBCARRIERS];
    signal centered[SAMPLE_COUNT][SUBCARRIERS];
    signal centeredSquared[SAMPLE_COUNT][SUBCARRIERS];
    signal signalNorm[SUBCARRIERS];
    component signalNonZero[SUBCARRIERS];
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        var magnitudeAccumulator = 0;
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            signedI[i][sc] <== csiI[i][sc] - CSI_OFFSET;
            signedQ[i][sc] <== csiQ[i][sc] - CSI_OFFSET;
            iSquared[i][sc] <== signedI[i][sc] * signedI[i][sc];
            qSquared[i][sc] <== signedQ[i][sc] * signedQ[i][sc];
            magnitudeSquared[i][sc] <== iSquared[i][sc] + qSquared[i][sc];
            magnitudeAccumulator += magnitudeSquared[i][sc];
        }
        magnitudeSum[sc] <== magnitudeAccumulator;

        var normAccumulator = 0;
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            centered[i][sc] <== SAMPLE_COUNT * magnitudeSquared[i][sc] - magnitudeSum[sc];
            centeredSquared[i][sc] <== centered[i][sc] * centered[i][sc];
            normAccumulator += centeredSquared[i][sc];
        }
        signalNorm[sc] <== normAccumulator;
        signalNonZero[sc] = IsZero();
        signalNonZero[sc].in <== signalNorm[sc];
        signalNonZero[sc].out === 0;
    }

    // Gram matrix of the non-orthogonal timestamp-derived sin/cos basis.
    signal cosSquares[FREQS][SAMPLE_COUNT];
    signal sinSquares[FREQS][SAMPLE_COUNT];
    signal basisCrossProducts[FREQS][SAMPLE_COUNT];
    signal cosNorm[FREQS];
    signal sinNorm[FREQS];
    signal basisCrossNorm[FREQS];
    signal normProduct[FREQS];
    signal basisCrossSquared[FREQS];
    signal determinantBasis[FREQS];
    component determinantNonZero[FREQS];
    for (var f = 0; f < FREQS; f++) {
        var cc = 0;
        var ss = 0;
        var cs = 0;
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            cosSquares[f][i] <==
                (timestampBasis.cosBasis[f][i] - TRIG_OFFSET)
                * (timestampBasis.cosBasis[f][i] - TRIG_OFFSET);
            sinSquares[f][i] <==
                (timestampBasis.sinBasis[f][i] - TRIG_OFFSET)
                * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
            basisCrossProducts[f][i] <==
                (timestampBasis.cosBasis[f][i] - TRIG_OFFSET)
                * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
            cc += cosSquares[f][i];
            ss += sinSquares[f][i];
            cs += basisCrossProducts[f][i];
        }
        cosNorm[f] <== cc;
        sinNorm[f] <== ss;
        basisCrossNorm[f] <== cs;
        normProduct[f] <== cosNorm[f] * sinNorm[f];
        basisCrossSquared[f] <== basisCrossNorm[f] * basisCrossNorm[f];
        determinantBasis[f] <== normProduct[f] - basisCrossSquared[f];
        determinantNonZero[f] = IsZero();
        determinantNonZero[f].in <== determinantBasis[f];
        determinantNonZero[f].out === 0;
    }

    // Division-free normalized Lomb--Scargle score:
    // (SS*C^2 - 2*CS*C*S + CC*S^2) / ((CC*SS-CS^2)*YY).
    signal cosineProjection[SUBCARRIERS][FREQS];
    signal sineProjection[SUBCARRIERS][FREQS];
    signal cosineProducts[SUBCARRIERS][FREQS][SAMPLE_COUNT];
    signal sineProducts[SUBCARRIERS][FREQS][SAMPLE_COUNT];
    signal cosineProjectionSquared[SUBCARRIERS][FREQS];
    signal sineProjectionSquared[SUBCARRIERS][FREQS];
    signal projectionCross[SUBCARRIERS][FREQS];
    signal cosineScoreTerm[SUBCARRIERS][FREQS];
    signal sineScoreTerm[SUBCARRIERS][FREQS];
    signal mixedScoreTerm[SUBCARRIERS][FREQS];
    signal scoreNumerator[SUBCARRIERS][FREQS];
    signal scoreDenominator[SUBCARRIERS][FREQS];
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        for (var f = 0; f < FREQS; f++) {
            var cProjection = 0;
            var sProjection = 0;
            for (var i = 0; i < SAMPLE_COUNT; i++) {
                cosineProducts[sc][f][i] <==
                    centered[i][sc] * (timestampBasis.cosBasis[f][i] - TRIG_OFFSET);
                sineProducts[sc][f][i] <==
                    centered[i][sc] * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
                cProjection += cosineProducts[sc][f][i];
                sProjection += sineProducts[sc][f][i];
            }
            cosineProjection[sc][f] <== cProjection;
            sineProjection[sc][f] <== sProjection;
            cosineProjectionSquared[sc][f] <== cosineProjection[sc][f] * cosineProjection[sc][f];
            sineProjectionSquared[sc][f] <== sineProjection[sc][f] * sineProjection[sc][f];
            projectionCross[sc][f] <== cosineProjection[sc][f] * sineProjection[sc][f];
            cosineScoreTerm[sc][f] <== cosineProjectionSquared[sc][f] * sinNorm[f];
            sineScoreTerm[sc][f] <== sineProjectionSquared[sc][f] * cosNorm[f];
            mixedScoreTerm[sc][f] <== 2 * projectionCross[sc][f] * basisCrossNorm[f];
            scoreNumerator[sc][f] <==
                cosineScoreTerm[sc][f] + sineScoreTerm[sc][f] - mixedScoreTerm[sc][f];
            scoreDenominator[sc][f] <== determinantBasis[f] * signalNorm[sc];
        }
    }

    // Per-subcarrier argmax in the normal breathing band.
    signal targetMaxNumerator[SUBCARRIERS][NORMAL_BINS];
    signal targetMaxDenominator[SUBCARRIERS][NORMAL_BINS];
    signal targetMaxIndex[SUBCARRIERS][NORMAL_BINS];
    signal targetCandidateCross[SUBCARRIERS][NORMAL_BINS];
    signal targetCurrentCross[SUBCARRIERS][NORMAL_BINS];
    component targetGt[SUBCARRIERS][NORMAL_BINS];
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        targetMaxNumerator[sc][0] <== scoreNumerator[sc][NORMAL_LOW_BIN];
        targetMaxDenominator[sc][0] <== scoreDenominator[sc][NORMAL_LOW_BIN];
        targetMaxIndex[sc][0] <== NORMAL_LOW_BIN;
        for (var j = 1; j < NORMAL_BINS; j++) {
            targetCandidateCross[sc][j] <==
                scoreNumerator[sc][NORMAL_LOW_BIN + j] * targetMaxDenominator[sc][j - 1];
            targetCurrentCross[sc][j] <==
                targetMaxNumerator[sc][j - 1] * scoreDenominator[sc][NORMAL_LOW_BIN + j];
            targetGt[sc][j] = GreaterThan(RATIO_BITS);
            targetGt[sc][j].in[0] <== targetCandidateCross[sc][j];
            targetGt[sc][j].in[1] <== targetCurrentCross[sc][j];
            targetMaxNumerator[sc][j] <==
                targetGt[sc][j].out
                * (scoreNumerator[sc][NORMAL_LOW_BIN + j] - targetMaxNumerator[sc][j - 1])
                + targetMaxNumerator[sc][j - 1];
            targetMaxDenominator[sc][j] <==
                targetGt[sc][j].out
                * (scoreDenominator[sc][NORMAL_LOW_BIN + j] - targetMaxDenominator[sc][j - 1])
                + targetMaxDenominator[sc][j - 1];
            targetMaxIndex[sc][j] <==
                targetGt[sc][j].out * ((NORMAL_LOW_BIN + j) - targetMaxIndex[sc][j - 1])
                + targetMaxIndex[sc][j - 1];
        }
    }

    // Choose the subcarrier with the strongest normalized normal-band peak.
    signal selectedNumerator[SUBCARRIERS];
    signal selectedDenominator[SUBCARRIERS];
    signal selectedSubcarrierState[SUBCARRIERS];
    signal subcarrierCandidateCross[SUBCARRIERS];
    signal subcarrierCurrentCross[SUBCARRIERS];
    component subcarrierGt[SUBCARRIERS];
    selectedNumerator[0] <== targetMaxNumerator[0][NORMAL_BINS - 1];
    selectedDenominator[0] <== targetMaxDenominator[0][NORMAL_BINS - 1];
    selectedSubcarrierState[0] <== 0;
    for (var sc = 1; sc < SUBCARRIERS; sc++) {
        subcarrierCandidateCross[sc] <==
            targetMaxNumerator[sc][NORMAL_BINS - 1] * selectedDenominator[sc - 1];
        subcarrierCurrentCross[sc] <==
            selectedNumerator[sc - 1] * targetMaxDenominator[sc][NORMAL_BINS - 1];
        subcarrierGt[sc] = GreaterThan(RATIO_BITS);
        subcarrierGt[sc].in[0] <== subcarrierCandidateCross[sc];
        subcarrierGt[sc].in[1] <== subcarrierCurrentCross[sc];
        selectedNumerator[sc] <==
            subcarrierGt[sc].out
            * (targetMaxNumerator[sc][NORMAL_BINS - 1] - selectedNumerator[sc - 1])
            + selectedNumerator[sc - 1];
        selectedDenominator[sc] <==
            subcarrierGt[sc].out
            * (targetMaxDenominator[sc][NORMAL_BINS - 1] - selectedDenominator[sc - 1])
            + selectedDenominator[sc - 1];
        selectedSubcarrierState[sc] <==
            subcarrierGt[sc].out * (sc - selectedSubcarrierState[sc - 1])
            + selectedSubcarrierState[sc - 1];
    }
    selectedSubcarrier <== selectedSubcarrierState[SUBCARRIERS - 1];

    // Full-grid argmax for every subcarrier, followed by private selection.
    signal globalMaxNumerator[SUBCARRIERS][FREQS];
    signal globalMaxDenominator[SUBCARRIERS][FREQS];
    signal globalMaxIndex[SUBCARRIERS][FREQS];
    signal globalCandidateCross[SUBCARRIERS][FREQS];
    signal globalCurrentCross[SUBCARRIERS][FREQS];
    component globalGt[SUBCARRIERS][FREQS];
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        globalMaxNumerator[sc][0] <== scoreNumerator[sc][0];
        globalMaxDenominator[sc][0] <== scoreDenominator[sc][0];
        globalMaxIndex[sc][0] <== 0;
        for (var f = 1; f < FREQS; f++) {
            globalCandidateCross[sc][f] <==
                scoreNumerator[sc][f] * globalMaxDenominator[sc][f - 1];
            globalCurrentCross[sc][f] <==
                globalMaxNumerator[sc][f - 1] * scoreDenominator[sc][f];
            globalGt[sc][f] = GreaterThan(RATIO_BITS);
            globalGt[sc][f].in[0] <== globalCandidateCross[sc][f];
            globalGt[sc][f].in[1] <== globalCurrentCross[sc][f];
            globalMaxNumerator[sc][f] <==
                globalGt[sc][f].out
                * (scoreNumerator[sc][f] - globalMaxNumerator[sc][f - 1])
                + globalMaxNumerator[sc][f - 1];
            globalMaxDenominator[sc][f] <==
                globalGt[sc][f].out
                * (scoreDenominator[sc][f] - globalMaxDenominator[sc][f - 1])
                + globalMaxDenominator[sc][f - 1];
            globalMaxIndex[sc][f] <==
                globalGt[sc][f].out * (f - globalMaxIndex[sc][f - 1])
                + globalMaxIndex[sc][f - 1];
        }
    }

    component selectedSubcarrierEq[SUBCARRIERS];
    signal estimatedTerms[SUBCARRIERS];
    signal globalTerms[SUBCARRIERS];
    var estimatedSum = 0;
    var globalSum = 0;
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        selectedSubcarrierEq[sc] = IsEqual();
        selectedSubcarrierEq[sc].in[0] <== selectedSubcarrier;
        selectedSubcarrierEq[sc].in[1] <== sc;
        estimatedTerms[sc] <== selectedSubcarrierEq[sc].out * targetMaxIndex[sc][NORMAL_BINS - 1];
        globalTerms[sc] <== selectedSubcarrierEq[sc].out * globalMaxIndex[sc][FREQS - 1];
        estimatedSum += estimatedTerms[sc];
        globalSum += globalTerms[sc];
    }
    estimatedFrequencyBin <== estimatedSum;
    globalPeakFrequencyBin <== globalSum;

    component geLow = GreaterEqThan(8);
    component leHigh = LessEqThan(8);
    geLow.in[0] <== globalPeakFrequencyBin;
    geLow.in[1] <== NORMAL_LOW_BIN;
    leHigh.in[0] <== globalPeakFrequencyBin;
    leHigh.in[1] <== NORMAL_HIGH_BIN;
    isNormal <== geLow.out * leHigh.out;
}

// Feasibility-sized end-to-end circuit:
// - 64 irregular samples
// - 8 private CSI subcarriers
// - 32 frequency bins from 0.05 through approximately 0.404 Hz
// - normal bins 5..27 = approximately 6.43 through 21.50 BPM
//
// RATIO_BITS=236 follows a conservative integer bound for 12-bit I/Q,
// 64 samples, 11-bit trigonometric values, and cross-multiplied scores.
component main {public [timestampsMs]} = LombScargleCSIEndToEnd(
    64,
    8,
    32,
    5,
    27,
    23,
    2048,
    12,
    1024,
    236
);
