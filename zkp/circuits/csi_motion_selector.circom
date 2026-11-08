pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/poseidon.circom";

// Private-CSI selection. No score, index or rank is supplied by the prover.
// This is a motion-sensitivity heuristic, not a classifier of motion sources.
template CSIMotionSelector(N, C) {
    assert(N >= 4 && N <= 64);
    assert(C >= 1 && C <= 4096);
    signal input csiI[N][C];
    signal input csiQ[N][C];
    signal input candidateCount;
    signal input commitmentNonce;
    signal output csiCommitment;
    signal output selectedSubcarrier;
    signal output selectedI[N];
    signal output selectedQ[N];

    component countBits = Num2Bits(16);
    countBits.in <== candidateCount;
    component countMin = GreaterEqThan(16);
    component countMax = LessEqThan(16);
    countMin.in[0] <== candidateCount;
    countMin.in[1] <== 1;
    countMin.out === 1;
    countMax.in[0] <== candidateCount;
    countMax.in[1] <== C;
    countMax.out === 1;
    component nonceZero = IsZero();
    nonceZero.in <== commitmentNonce;
    nonceZero.out === 0;

    component active[C];
    component iBits[N][C];
    component qBits[N][C];
    signal iSquared[N][C];
    signal qSquared[N][C];
    signal power[N][C];
    signal powerSquared[N][C];
    signal deltaSquared[N - 1][C];
    signal total[C];
    signal totalSquared[C];
    signal variation[C];
    signal roughness[C];
    signal numerator[C];
    signal denominator[C];
    component strong[C];
    component variable[C];
    component notImpulsive[C];
    signal eligibleA[C];
    signal eligibleB[C];
    signal eligible[C];
    signal eligibleNumerator[C];

    for (var sc = 0; sc < C; sc++) {
        active[sc] = LessThan(16);
        active[sc].in[0] <== sc;
        active[sc].in[1] <== candidateCount;
        var sumP = 0;
        var sumP2 = 0;
        var sumD = 0;
        for (var i = 0; i < N; i++) {
            iBits[i][sc] = Num2Bits(12);
            qBits[i][sc] = Num2Bits(12);
            iBits[i][sc].in <== csiI[i][sc];
            qBits[i][sc].in <== csiQ[i][sc];
            // Padding has exactly one encoding and cannot win selection.
            (1 - active[sc].out) * (csiI[i][sc] - 2048) === 0;
            (1 - active[sc].out) * (csiQ[i][sc] - 2048) === 0;
            iSquared[i][sc] <== (csiI[i][sc] - 2048) * (csiI[i][sc] - 2048);
            qSquared[i][sc] <== (csiQ[i][sc] - 2048) * (csiQ[i][sc] - 2048);
            power[i][sc] <== iSquared[i][sc] + qSquared[i][sc];
            powerSquared[i][sc] <== power[i][sc] * power[i][sc];
            sumP += power[i][sc];
            sumP2 += powerSquared[i][sc];
            if (i > 0) {
                deltaSquared[i - 1][sc] <== (power[i][sc] - power[i - 1][sc])
                    * (power[i][sc] - power[i - 1][sc]);
                sumD += deltaSquared[i - 1][sc];
            }
        }
        total[sc] <== sumP;
        totalSquared[sc] <== total[sc] * total[sc];
        variation[sc] <== N * sumP2 - totalSquared[sc];
        roughness[sc] <== sumD;
        // Score = relative power variation * smoothness, without division:
        // V^2 / ((S^2 + 1) * (V + N*D + 1)).
        numerator[sc] <== variation[sc] * variation[sc];
        denominator[sc] <== (totalSquared[sc] + 1)
            * (variation[sc] + N * roughness[sc] + 1);
        strong[sc] = GreaterEqThan(30);
        strong[sc].in[0] <== total[sc];
        strong[sc].in[1] <== N * 16;
        variable[sc] = IsZero();
        variable[sc].in <== variation[sc];
        // Power CV^2 <= 1 rejects very sparse spikes/deep fades cheaply.
        notImpulsive[sc] = LessEqThan(59);
        notImpulsive[sc].in[0] <== variation[sc];
        notImpulsive[sc].in[1] <== totalSquared[sc];
        eligibleA[sc] <== active[sc].out * strong[sc].out;
        eligibleB[sc] <== eligibleA[sc] * (1 - variable[sc].out);
        eligible[sc] <== eligibleB[sc] * notImpulsive[sc].out;
        eligibleNumerator[sc] <== eligible[sc] * numerator[sc];
    }

    // Bounds with N <= 64 and 12-bit encoded I/Q:
    // p <= 2^23, S <= 2^29, 0 <= V < 2^58, D < 2^52;
    // numerator < 2^116, denominator < 2^118, products < 2^234.
    // Comparison at 240 bits therefore cannot wrap the BN254 scalar field.
    signal bestNumerator[C + 1];
    signal bestDenominator[C + 1];
    signal bestIndex[C + 1];
    signal left[C];
    signal right[C];
    component better[C];
    bestNumerator[0] <== 0;
    bestDenominator[0] <== 1;
    bestIndex[0] <== 0;
    for (var sc = 0; sc < C; sc++) {
        left[sc] <== eligibleNumerator[sc] * bestDenominator[sc];
        right[sc] <== bestNumerator[sc] * denominator[sc];
        better[sc] = GreaterThan(240);
        better[sc].in[0] <== left[sc];
        better[sc].in[1] <== right[sc];
        bestNumerator[sc + 1] <== bestNumerator[sc]
            + better[sc].out * (eligibleNumerator[sc] - bestNumerator[sc]);
        bestDenominator[sc + 1] <== bestDenominator[sc]
            + better[sc].out * (denominator[sc] - bestDenominator[sc]);
        bestIndex[sc + 1] <== bestIndex[sc] + better[sc].out * (sc - bestIndex[sc]);
    }
    // No eligible carrier is an error, never a fabricated breathing result.
    component noWinner = IsZero();
    noWinner.in <== bestNumerator[C];
    noWinner.out === 0;
    selectedSubcarrier <== bestIndex[C];

    component chosen[C];
    signal chosenI[N][C];
    signal chosenQ[N][C];
    // Large flat symbolic sums make Circom compilation quadratic in C.
    // Materialize 16-column partial sums; preserve the original <=64 R1CS.
    var GROUPS = C > 64 ? (C + 15) \ 16 : 0;
    signal groupI[N][GROUPS];
    signal groupQ[N][GROUPS];
    for (var sc = 0; sc < C; sc++) {
        chosen[sc] = IsEqual();
        chosen[sc].in[0] <== selectedSubcarrier;
        chosen[sc].in[1] <== sc;
    }
    for (var i = 0; i < N; i++) {
        var sumI = 0;
        var sumQ = 0;
        var chunkI = 0;
        var chunkQ = 0;
        for (var sc = 0; sc < C; sc++) {
            chosenI[i][sc] <== chosen[sc].out * csiI[i][sc];
            chosenQ[i][sc] <== chosen[sc].out * csiQ[i][sc];
            if (C <= 64) {
                sumI += chosenI[i][sc];
                sumQ += chosenQ[i][sc];
            } else {
                chunkI += chosenI[i][sc];
                chunkQ += chosenQ[i][sc];
                if (sc % 16 == 15 || sc == C - 1) {
                    groupI[i][sc \ 16] <== chunkI;
                    groupQ[i][sc \ 16] <== chunkQ;
                    chunkI = 0;
                    chunkQ = 0;
                }
            }
        }
        for (var g = 0; g < GROUPS; g++) {
            sumI += groupI[i][g];
            sumQ += groupQ[i][g];
        }
        selectedI[i] <== sumI;
        selectedQ[i] <== sumQ;
    }

    // Commit the entire candidate pool, including losing carriers.
    // Pack ten 24-bit I/Q pairs into each field (< 2^240 < BN254).
    // Header binds the version, shape, real column count, and private nonce.
    component header = Poseidon(5);
    header.inputs[0] <== 2026110901;
    header.inputs[1] <== N;
    header.inputs[2] <== C;
    header.inputs[3] <== candidateCount;
    header.inputs[4] <== commitmentNonce;
    var PACKS = (N * C + 9) \ 10;
    var BLOCKS = (PACKS + 14) \ 15;
    signal packed[PACKS];
    for (var j = 0; j < PACKS; j++) {
        var value = 0;
        for (var k = 0; k < 10; k++) {
            var pos = 10 * j + k;
            if (pos < N * C) {
                value += (csiI[pos \ C][pos % C] + 4096 * csiQ[pos \ C][pos % C]) * (2 ** (24 * k));
            }
        }
        packed[j] <== value;
    }
    component hash[BLOCKS];
    signal state[BLOCKS + 1];
    state[0] <== header.out;
    for (var b = 0; b < BLOCKS; b++) {
        hash[b] = Poseidon(16);
        hash[b].inputs[0] <== state[b];
        for (var j = 0; j < 15; j++) {
            if (15 * b + j < PACKS) {
                hash[b].inputs[j + 1] <== packed[15 * b + j];
            } else {
                hash[b].inputs[j + 1] <== 0;
            }
        }
        state[b + 1] <== hash[b].out;
    }
    csiCommitment <== state[BLOCKS];
}
