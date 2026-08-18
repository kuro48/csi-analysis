pragma circom 2.0.0;

include "circomlib/circuits/comparators.circom";

/**
 * Lomb--Scargle比較アルゴリズムの正常判定証明。
 *
 * このファイルは scripts/generate_lomb_scargle_circuit.py から生成される。
 * Pythonで計算・0..1000000へ量子化した各PCのピリオドグラムを秘密入力とし、
 * 次を回路内で検証する。
 *   1. 全入力の範囲
 *   2. 正常帯域内ピークが最大のPCの選択
 *   3. 選択PCにおける全探索帯域のグローバルargmax
 *   4. グローバルピークが 6..40 BPM に入るか
 *
 * 注意: 不均一時刻を用いる浮動小数点Lomb--Scargle変換自体は回路外であり、
 * この回路は与えられたピリオドグラムに対する判定証明である。
 */
template LombScargleNormalityCheck(
    PCS,
    FREQS,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN,
    POWER_SCALE,
    POWER_BITS
) {
    signal input powers[PCS][FREQS];
    signal output isNormal;
    signal output selectedPc;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;

    component powerInRange[PCS][FREQS];
    for (var pc = 0; pc < PCS; pc++) {
        for (var f = 0; f < FREQS; f++) {
            powerInRange[pc][f] = LessEqThan(POWER_BITS);
            powerInRange[pc][f].in[0] <== powers[pc][f];
            powerInRange[pc][f].in[1] <== POWER_SCALE;
            powerInRange[pc][f].out === 1;
        }
    }

    // PCごとの正常帯域内argmax（Notebookの推定BPMとPC選択）。
    signal targetMax[PCS][390];
    signal targetMaxIdx[PCS][390];
    component targetGt[PCS][390];
    for (var pc = 0; pc < PCS; pc++) {
        targetMax[pc][0] <== powers[pc][NORMAL_LOW_BIN];
        targetMaxIdx[pc][0] <== NORMAL_LOW_BIN;
        for (var i = 1; i < 390; i++) {
            targetGt[pc][i] = GreaterThan(POWER_BITS);
            targetGt[pc][i].in[0] <== powers[pc][NORMAL_LOW_BIN + i];
            targetGt[pc][i].in[1] <== targetMax[pc][i - 1];
            targetMax[pc][i] <==
                targetGt[pc][i].out * (powers[pc][NORMAL_LOW_BIN + i] - targetMax[pc][i - 1])
                + targetMax[pc][i - 1];
            targetMaxIdx[pc][i] <==
                targetGt[pc][i].out * ((NORMAL_LOW_BIN + i) - targetMaxIdx[pc][i - 1])
                + targetMaxIdx[pc][i - 1];
        }
    }

    signal selectedTargetMax[PCS];
    signal selectedPcState[PCS];
    component pcGt[PCS];
    selectedTargetMax[0] <== targetMax[0][389];
    selectedPcState[0] <== 0;
    for (var pc = 1; pc < PCS; pc++) {
        pcGt[pc] = GreaterThan(POWER_BITS);
        pcGt[pc].in[0] <== targetMax[pc][389];
        pcGt[pc].in[1] <== selectedTargetMax[pc - 1];
        selectedTargetMax[pc] <==
            pcGt[pc].out * (targetMax[pc][389] - selectedTargetMax[pc - 1])
            + selectedTargetMax[pc - 1];
        selectedPcState[pc] <==
            pcGt[pc].out * (pc - selectedPcState[pc - 1]) + selectedPcState[pc - 1];
    }
    selectedPc <== selectedPcState[PCS - 1];

    // 各PCの全探索帯域argmax。
    signal globalMax[PCS][FREQS];
    signal globalMaxIdx[PCS][FREQS];
    component globalGt[PCS][FREQS];
    for (var pc = 0; pc < PCS; pc++) {
        globalMax[pc][0] <== powers[pc][0];
        globalMaxIdx[pc][0] <== 0;
        for (var f = 1; f < FREQS; f++) {
            globalGt[pc][f] = GreaterThan(POWER_BITS);
            globalGt[pc][f].in[0] <== powers[pc][f];
            globalGt[pc][f].in[1] <== globalMax[pc][f - 1];
            globalMax[pc][f] <==
                globalGt[pc][f].out * (powers[pc][f] - globalMax[pc][f - 1])
                + globalMax[pc][f - 1];
            globalMaxIdx[pc][f] <==
                globalGt[pc][f].out * (f - globalMaxIdx[pc][f - 1]) + globalMaxIdx[pc][f - 1];
        }
    }

    component selectedPcEq[PCS];
    signal estimatedTerms[PCS];
    signal globalTerms[PCS];
    var estimatedSum = 0;
    var globalSum = 0;
    for (var pc = 0; pc < PCS; pc++) {
        selectedPcEq[pc] = IsEqual();
        selectedPcEq[pc].in[0] <== selectedPc;
        selectedPcEq[pc].in[1] <== pc;
        estimatedTerms[pc] <== selectedPcEq[pc].out * targetMaxIdx[pc][389];
        globalTerms[pc] <== selectedPcEq[pc].out * globalMaxIdx[pc][FREQS - 1];
        estimatedSum += estimatedTerms[pc];
        globalSum += globalTerms[pc];
    }
    estimatedFrequencyBin <== estimatedSum;
    globalPeakFrequencyBin <== globalSum;

    component geLow = GreaterEqThan(11);
    component leHigh = LessEqThan(11);
    geLow.in[0] <== globalPeakFrequencyBin;
    geLow.in[1] <== NORMAL_LOW_BIN;
    leHigh.in[0] <== globalPeakFrequencyBin;
    leHigh.in[1] <== NORMAL_HIGH_BIN;
    isNormal <== geLow.out * leHigh.out;
}

// frequency(bin) = 0.05 + bin * (1.5 - 0.05) / (1000 - 1)
// normal bins: 35 (6.048 BPM)
//           .. 424 (39.925 BPM)
component main = LombScargleNormalityCheck(
    3,
    1000,
    35,
    424,
    1000000,
    21
);
