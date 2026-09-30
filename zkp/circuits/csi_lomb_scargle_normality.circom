pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";
include "lomb_scargle_timestamp_basis.circom";

/**
 * 不均一時刻PCA波形の固定小数点Lomb--Scargle証明。
 *
 * 秘密入力:
 *   samples[PCS][SAMPLES]   中心化PCA波形を SAMPLE_OFFSET で符号化
 * 公開入力:
 *   timestampsMs            先頭を0とした不均一時刻（ミリ秒）
 *
 * 回路内で次を制約化する。
 *   1. 秘密波形の11-bit範囲
 *   2. timestampからの近似sin/cos基底生成
 *   3. τを消去したGram行列形式のLomb--Scargleスコア
 *   4. 正常帯域ピークによるPC選択
 *   5. 選択PCの全帯域argmaxと正常帯域判定
 *
 * sin/cosは象限縮約したTaylor近似で16周波数binごとに再計算し、
 * アンカー間だけ周波数方向の複素回転で回路内生成する。
 */
template LombScargleFixedPointCheck(
    PCS,
    SAMPLE_COUNT,
    FREQS,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN,
    SAMPLE_OFFSET,
    TRIG_OFFSET,
    INPUT_BITS,
    RATIO_BITS
) {
    signal input samples[PCS][SAMPLE_COUNT];
    signal input timestampsMs[SAMPLE_COUNT];

    signal output isNormal;
    signal output selectedPc;
    signal output estimatedFrequencyBin;
    signal output globalPeakFrequencyBin;

    timestampsMs[0] === 0;
    component timestampBits[SAMPLE_COUNT];
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        timestampBits[i] = Num2Bits(24);
        timestampBits[i].in <== timestampsMs[i];
    }

    component timestampBasis = LombTimestampBasis(SAMPLE_COUNT, FREQS, 16);
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        timestampBasis.timestampsMs[i] <== timestampsMs[i];
    }

    // 秘密波形を0..2047へ拘束する。公開基底の11-bit範囲は検証者が
    // 公開入力として検査する（バックエンドの_prepare_inputでも強制）。
    component sampleBits[PCS][SAMPLE_COUNT];
    for (var pc = 0; pc < PCS; pc++) {
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            sampleBits[pc][i] = Num2Bits(INPUT_BITS);
            sampleBits[pc][i].in <== samples[pc][i];
        }
    }

    signal signalSquares[PCS][SAMPLE_COUNT];
    signal signalNorm[PCS];
    component signalNonZero[PCS];
    for (var pc = 0; pc < PCS; pc++) {
        var yy = 0;
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            signalSquares[pc][i] <==
                (samples[pc][i] - SAMPLE_OFFSET) * (samples[pc][i] - SAMPLE_OFFSET);
            yy += signalSquares[pc][i];
        }
        signalNorm[pc] <== yy;
        signalNonZero[pc] = IsZero();
        signalNonZero[pc].in <== signalNorm[pc];
        signalNonZero[pc].out === 0;
    }

    // score = (SS*C^2 - 2*CS*C*S + CC*S^2) / ((CC*SS-CS^2)*YY)
    // これはτ回転で基底を直交化した標準式と代数的に等価。
    // 除算を避け、argmaxでは分子・分母を交差乗算して比較する。
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
                (timestampBasis.cosBasis[f][i] - TRIG_OFFSET) * (timestampBasis.cosBasis[f][i] - TRIG_OFFSET);
            sinSquares[f][i] <==
                (timestampBasis.sinBasis[f][i] - TRIG_OFFSET) * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
            basisCrossProducts[f][i] <==
                (timestampBasis.cosBasis[f][i] - TRIG_OFFSET) * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
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

    signal cosineProjection[PCS][FREQS];
    signal sineProjection[PCS][FREQS];
    signal cosineProducts[PCS][FREQS][SAMPLE_COUNT];
    signal sineProducts[PCS][FREQS][SAMPLE_COUNT];
    signal cosineProjectionSquared[PCS][FREQS];
    signal sineProjectionSquared[PCS][FREQS];
    signal projectionCross[PCS][FREQS];
    signal cosineScoreTerm[PCS][FREQS];
    signal sineScoreTerm[PCS][FREQS];
    signal mixedScoreTerm[PCS][FREQS];
    signal scoreNumerator[PCS][FREQS];
    signal scoreDenominator[PCS][FREQS];
    for (var pc = 0; pc < PCS; pc++) {
        for (var f = 0; f < FREQS; f++) {
            var cProjection = 0;
            var sProjection = 0;
            for (var i = 0; i < SAMPLE_COUNT; i++) {
                cosineProducts[pc][f][i] <==
                    (samples[pc][i] - SAMPLE_OFFSET) * (timestampBasis.cosBasis[f][i] - TRIG_OFFSET);
                sineProducts[pc][f][i] <==
                    (samples[pc][i] - SAMPLE_OFFSET) * (timestampBasis.sinBasis[f][i] - TRIG_OFFSET);
                cProjection += cosineProducts[pc][f][i];
                sProjection += sineProducts[pc][f][i];
            }
            cosineProjection[pc][f] <== cProjection;
            sineProjection[pc][f] <== sProjection;
            cosineProjectionSquared[pc][f] <==
                cosineProjection[pc][f] * cosineProjection[pc][f];
            sineProjectionSquared[pc][f] <==
                sineProjection[pc][f] * sineProjection[pc][f];
            projectionCross[pc][f] <== cosineProjection[pc][f] * sineProjection[pc][f];
            cosineScoreTerm[pc][f] <== cosineProjectionSquared[pc][f] * sinNorm[f];
            sineScoreTerm[pc][f] <== sineProjectionSquared[pc][f] * cosNorm[f];
            mixedScoreTerm[pc][f] <== 2 * projectionCross[pc][f] * basisCrossNorm[f];
            scoreNumerator[pc][f] <== cosineScoreTerm[pc][f] + sineScoreTerm[pc][f] - mixedScoreTerm[pc][f];
            scoreDenominator[pc][f] <== determinantBasis[f] * signalNorm[pc];
        }
    }

    // PCごとの正常帯域argmax。
    signal targetMaxNumerator[PCS][50];
    signal targetMaxDenominator[PCS][50];
    signal targetMaxIndex[PCS][50];
    signal targetCandidateCross[PCS][50];
    signal targetCurrentCross[PCS][50];
    component targetGt[PCS][50];
    for (var pc = 0; pc < PCS; pc++) {
        targetMaxNumerator[pc][0] <== scoreNumerator[pc][NORMAL_LOW_BIN];
        targetMaxDenominator[pc][0] <== scoreDenominator[pc][NORMAL_LOW_BIN];
        targetMaxIndex[pc][0] <== NORMAL_LOW_BIN;
        for (var j = 1; j < 50; j++) {
            targetCandidateCross[pc][j] <==
                scoreNumerator[pc][NORMAL_LOW_BIN + j] * targetMaxDenominator[pc][j - 1];
            targetCurrentCross[pc][j] <==
                targetMaxNumerator[pc][j - 1] * scoreDenominator[pc][NORMAL_LOW_BIN + j];
            targetGt[pc][j] = GreaterThan(RATIO_BITS);
            targetGt[pc][j].in[0] <== targetCandidateCross[pc][j];
            targetGt[pc][j].in[1] <== targetCurrentCross[pc][j];
            targetMaxNumerator[pc][j] <==
                targetGt[pc][j].out
                * (scoreNumerator[pc][NORMAL_LOW_BIN + j] - targetMaxNumerator[pc][j - 1])
                + targetMaxNumerator[pc][j - 1];
            targetMaxDenominator[pc][j] <==
                targetGt[pc][j].out
                * (scoreDenominator[pc][NORMAL_LOW_BIN + j] - targetMaxDenominator[pc][j - 1])
                + targetMaxDenominator[pc][j - 1];
            targetMaxIndex[pc][j] <==
                targetGt[pc][j].out * ((NORMAL_LOW_BIN + j) - targetMaxIndex[pc][j - 1])
                + targetMaxIndex[pc][j - 1];
        }
    }

    // 正常帯域ピークの正規化スコアが最大のPCを選ぶ。
    signal selectedNumerator[PCS];
    signal selectedDenominator[PCS];
    signal selectedPcState[PCS];
    signal pcCandidateCross[PCS];
    signal pcCurrentCross[PCS];
    component pcGt[PCS];
    selectedNumerator[0] <== targetMaxNumerator[0][49];
    selectedDenominator[0] <== targetMaxDenominator[0][49];
    selectedPcState[0] <== 0;
    for (var pc = 1; pc < PCS; pc++) {
        pcCandidateCross[pc] <==
            targetMaxNumerator[pc][49] * selectedDenominator[pc - 1];
        pcCurrentCross[pc] <==
            selectedNumerator[pc - 1] * targetMaxDenominator[pc][49];
        pcGt[pc] = GreaterThan(RATIO_BITS);
        pcGt[pc].in[0] <== pcCandidateCross[pc];
        pcGt[pc].in[1] <== pcCurrentCross[pc];
        selectedNumerator[pc] <==
            pcGt[pc].out
            * (targetMaxNumerator[pc][49] - selectedNumerator[pc - 1])
            + selectedNumerator[pc - 1];
        selectedDenominator[pc] <==
            pcGt[pc].out
            * (targetMaxDenominator[pc][49] - selectedDenominator[pc - 1])
            + selectedDenominator[pc - 1];
        selectedPcState[pc] <==
            pcGt[pc].out * (pc - selectedPcState[pc - 1]) + selectedPcState[pc - 1];
    }
    selectedPc <== selectedPcState[PCS - 1];

    // 各PCの全探索帯域argmax。
    signal globalMaxNumerator[PCS][FREQS];
    signal globalMaxDenominator[PCS][FREQS];
    signal globalMaxIndex[PCS][FREQS];
    signal globalCandidateCross[PCS][FREQS];
    signal globalCurrentCross[PCS][FREQS];
    component globalGt[PCS][FREQS];
    for (var pc = 0; pc < PCS; pc++) {
        globalMaxNumerator[pc][0] <== scoreNumerator[pc][0];
        globalMaxDenominator[pc][0] <== scoreDenominator[pc][0];
        globalMaxIndex[pc][0] <== 0;
        for (var f = 1; f < FREQS; f++) {
            globalCandidateCross[pc][f] <== scoreNumerator[pc][f] * globalMaxDenominator[pc][f - 1];
            globalCurrentCross[pc][f] <== globalMaxNumerator[pc][f - 1] * scoreDenominator[pc][f];
            globalGt[pc][f] = GreaterThan(RATIO_BITS);
            globalGt[pc][f].in[0] <== globalCandidateCross[pc][f];
            globalGt[pc][f].in[1] <== globalCurrentCross[pc][f];
            globalMaxNumerator[pc][f] <==
                globalGt[pc][f].out * (scoreNumerator[pc][f] - globalMaxNumerator[pc][f - 1])
                + globalMaxNumerator[pc][f - 1];
            globalMaxDenominator[pc][f] <==
                globalGt[pc][f].out * (scoreDenominator[pc][f] - globalMaxDenominator[pc][f - 1])
                + globalMaxDenominator[pc][f - 1];
            globalMaxIndex[pc][f] <==
                globalGt[pc][f].out * (f - globalMaxIndex[pc][f - 1]) + globalMaxIndex[pc][f - 1];
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
        estimatedTerms[pc] <== selectedPcEq[pc].out * targetMaxIndex[pc][49];
        globalTerms[pc] <== selectedPcEq[pc].out * globalMaxIndex[pc][FREQS - 1];
        estimatedSum += estimatedTerms[pc];
        globalSum += globalTerms[pc];
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

// frequency(bin) = 0.05 + bin * (1.5 - 0.05) / (128 - 1)
// normal bins: 5 (6.425 BPM)
//           .. 54 (39.992 BPM)
component main {public [timestampsMs]} = LombScargleFixedPointCheck(
    3,
    384,
    128,
    5,
    54,
    1024,
    1024,
    11,
    180
);
