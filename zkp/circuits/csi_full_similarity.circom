pragma circom 2.0.0;

include "circomlib/circuits/comparators.circom";

/**
 * CSI呼吸モニタリング正常判定回路
 *
 * 設計方針：
 * - 秘密入力：FFT適用済みCSIデータ（0.0～0.6Hz、0.02Hz刻み）
 * - 公開出力：生体情報が正常範囲内かどうか（isNormal）
 *
 * 処理フロー：
 * 1. コサイン類似度計算 → 最も変化量の大きいサブキャリアを選択（min cosine similarity）
 * 2. 選択サブキャリアのスペクトラムを追跡
 * 3. 選択スペクトラムのピーク周波数ビンを求める（argmax）
 * 4. ピークビンが正常範囲 [NORMAL_LOW_BIN, NORMAL_HIGH_BIN] 内なら isNormal=1
 *
 * 周波数マッピング（NUM_FREQ_POINTS=31, 0.02Hz刻み）:
 *   bin  0 →  0.00Hz
 *   bin  5 →  0.10Hz  ← NORMAL_LOW_BIN  (呼吸正常域下限)
 *   bin 12 →  0.24Hz  ← 成人平均呼吸数
 *   bin 25 →  0.50Hz  ← NORMAL_HIGH_BIN (呼吸正常域上限)
 *   bin 30 →  0.60Hz
 *
 * パラメータ:
 *   NUM_FREQ_POINTS   : 31   (0.00～0.60Hz, 0.02Hz刻み)
 *   NUM_SUBCARRIERS   : 245
 *   SCALE             : 10000 (固定小数点スケール)
 *   ITER              : 2     (Newton-Raphson反復)
 *   NORMAL_LOW_BIN    : 5     (0.10Hz)
 *   NORMAL_HIGH_BIN   : 25    (0.50Hz)
 */

// ===== サブ回路 =====

template VectorNormSquared(N) {
    signal input vector[N];
    signal output normSquared;

    signal squares[N];
    signal accumulator[N];

    for (var i = 0; i < N; i++) {
        squares[i] <== vector[i] * vector[i];
        if (i == 0) {
            accumulator[i] <== squares[i];
        } else {
            accumulator[i] <== accumulator[i-1] + squares[i];
        }
    }
    normSquared <== accumulator[N-1];
}

template DotProduct(N) {
    signal input vectorA[N];
    signal input vectorB[N];
    signal output dotProduct;

    signal products[N];
    signal accumulator[N];

    for (var i = 0; i < N; i++) {
        products[i] <== vectorA[i] * vectorB[i];
        if (i == 0) {
            accumulator[i] <== products[i];
        } else {
            accumulator[i] <== accumulator[i-1] + products[i];
        }
    }
    dotProduct <== accumulator[N-1];
}

/**
 * 逆平方根近似（Newton-Raphson法）
 * SCALEをテンプレートパラメータ（コンパイル時定数）にして非二次制約を回避
 */
template InvSqrtApprox(iterations, SCALE) {
    signal input x;
    signal output invSqrt;

    signal y[iterations + 1];
    signal y_sq[iterations];
    signal y2[iterations];
    signal xy2[iterations];
    signal half_xy2[iterations];
    signal term[iterations];
    signal y_raw[iterations];

    y[0] <== SCALE;

    for (var i = 0; i < iterations; i++) {
        y_sq[i]      <== y[i] * y[i];
        y2[i]        <== y_sq[i] / SCALE;
        xy2[i]       <== x * y2[i];
        half_xy2[i]  <== xy2[i] / (2 * SCALE);
        term[i]      <== (3 * SCALE) / 2 - half_xy2[i];
        y_raw[i]     <== y[i] * term[i];
        y[i + 1]     <== y_raw[i] / SCALE;
    }
    invSqrt <== y[iterations];
}

/**
 * サブキャリア1本のコサイン類似度計算
 */
template SubcarrierCosine(NUM_FREQ_POINTS, SCALE, ITER) {
    signal input ref[NUM_FREQ_POINTS];
    signal input cand[NUM_FREQ_POINTS];
    signal output similarity;

    component normCalcA = VectorNormSquared(NUM_FREQ_POINTS);
    component normCalcB = VectorNormSquared(NUM_FREQ_POINTS);
    for (var i = 0; i < NUM_FREQ_POINTS; i++) {
        normCalcA.vector[i] <== ref[i];
        normCalcB.vector[i] <== cand[i];
    }

    component dotCalc = DotProduct(NUM_FREQ_POINTS);
    for (var j = 0; j < NUM_FREQ_POINTS; j++) {
        dotCalc.vectorA[j] <== ref[j];
        dotCalc.vectorB[j] <== cand[j];
    }

    component normACheck = GreaterThan(128);
    normACheck.in[0] <== normCalcA.normSquared;
    normACheck.in[1] <== 0;

    component normBCheck = GreaterThan(128);
    normBCheck.in[0] <== normCalcB.normSquared;
    normBCheck.in[1] <== 0;

    signal isValid <== normACheck.out * normBCheck.out;

    component invSqrt = InvSqrtApprox(ITER, SCALE);
    invSqrt.x <== normCalcA.normSquared * normCalcB.normSquared;

    signal cos_raw   <== dotCalc.dotProduct * invSqrt.invSqrt;
    signal cos_approx <== cos_raw / SCALE;
    similarity <== cos_approx * isValid;
}

// ===== メイン回路 =====

template NormalBreathingCheck(
    NUM_FREQ_POINTS,
    NUM_SUBCARRIERS,
    SCALE,
    ITER,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN
) {
    // 秘密入力：FFT適用済みCSIデータ
    signal input referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal input candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];

    // 公開出力：正常範囲内かどうか（0 or 1）
    signal output isNormal;

    // ===== ステップ1: コサイン類似度計算 + 最小類似度サブキャリア選択 =====
    // 同時に、そのサブキャリアのcandidateスペクトラムを追跡する

    component subcos[NUM_SUBCARRIERS];
    signal similarities[NUM_SUBCARRIERS];
    signal minSim[NUM_SUBCARRIERS];

    // minSim追跡の中間シグナル（lt * A + (1-lt) * B の2積を分離）
    signal sim_term_a[NUM_SUBCARRIERS];   // lt.out * similarities[sc]
    signal sim_term_b[NUM_SUBCARRIERS];   // lt.out * minSim[sc-1]

    // 選択スペクトラム追跡（minSimが更新された場合にcandidateスペクトラムを更新）
    signal selectedSpec[NUM_SUBCARRIERS][NUM_FREQ_POINTS];
    signal spec_term_a[NUM_SUBCARRIERS][NUM_FREQ_POINTS]; // lt.out * candidateMatrix[f][sc]
    signal spec_term_b[NUM_SUBCARRIERS][NUM_FREQ_POINTS]; // lt.out * selectedSpec[sc-1][f]

    component lt[NUM_SUBCARRIERS];

    for (var sc = 0; sc < NUM_SUBCARRIERS; sc++) {
        subcos[sc] = SubcarrierCosine(NUM_FREQ_POINTS, SCALE, ITER);
        for (var f = 0; f < NUM_FREQ_POINTS; f++) {
            subcos[sc].ref[f]  <== referenceMatrix[f][sc];
            subcos[sc].cand[f] <== candidateMatrix[f][sc];
        }
        similarities[sc] <== subcos[sc].similarity;

        if (sc == 0) {
            minSim[0]        <== similarities[0];
            sim_term_a[0]    <== 0;
            sim_term_b[0]    <== 0;
            for (var f = 0; f < NUM_FREQ_POINTS; f++) {
                selectedSpec[0][f] <== candidateMatrix[f][0];
                spec_term_a[0][f]  <== 0;
                spec_term_b[0][f]  <== 0;
            }
        } else {
            // similarities[sc] < minSim[sc-1] なら lt.out = 1（新しい最小）
            lt[sc] = LessThan(128);
            lt[sc].in[0] <== similarities[sc];
            lt[sc].in[1] <== minSim[sc - 1];

            // minSim更新: lt*sim + (1-lt)*prev = lt*sim - lt*prev + prev
            sim_term_a[sc] <== lt[sc].out * similarities[sc];
            sim_term_b[sc] <== lt[sc].out * minSim[sc - 1];
            minSim[sc] <== sim_term_a[sc] - sim_term_b[sc] + minSim[sc - 1];

            // 選択スペクトラム更新（同じlt.outを使って各周波数ビンを更新）
            for (var f = 0; f < NUM_FREQ_POINTS; f++) {
                spec_term_a[sc][f] <== lt[sc].out * candidateMatrix[f][sc];
                spec_term_b[sc][f] <== lt[sc].out * selectedSpec[sc - 1][f];
                selectedSpec[sc][f] <== spec_term_a[sc][f] - spec_term_b[sc][f] + selectedSpec[sc - 1][f];
            }
        }
    }

    // ===== ステップ2: 選択スペクトラムのargmax（ピーク周波数ビン）=====

    signal maxVal[NUM_FREQ_POINTS];
    signal maxIdx[NUM_FREQ_POINTS];

    // 中間シグナル（2積の分離）
    signal argmax_val_a[NUM_FREQ_POINTS]; // gt.out * selectedSpec[f]
    signal argmax_val_b[NUM_FREQ_POINTS]; // gt.out * maxVal[f-1]
    signal argmax_idx_a[NUM_FREQ_POINTS]; // gt.out * f  （fはコンパイル時定数 → linear）
    signal argmax_idx_b[NUM_FREQ_POINTS]; // gt.out * maxIdx[f-1]

    component argmax_gt[NUM_FREQ_POINTS]; // gt.out = 1 if selectedSpec[f] > maxVal[f-1]

    maxVal[0] <== selectedSpec[NUM_SUBCARRIERS - 1][0];
    maxIdx[0] <== 0;
    argmax_val_a[0] <== 0;
    argmax_val_b[0] <== 0;
    argmax_idx_a[0] <== 0;
    argmax_idx_b[0] <== 0;

    for (var f = 1; f < NUM_FREQ_POINTS; f++) {
        argmax_gt[f] = GreaterThan(128);
        argmax_gt[f].in[0] <== selectedSpec[NUM_SUBCARRIERS - 1][f];
        argmax_gt[f].in[1] <== maxVal[f - 1];

        // maxVal更新
        argmax_val_a[f] <== argmax_gt[f].out * selectedSpec[NUM_SUBCARRIERS - 1][f];
        argmax_val_b[f] <== argmax_gt[f].out * maxVal[f - 1];
        maxVal[f] <== argmax_val_a[f] - argmax_val_b[f] + maxVal[f - 1];

        // maxIdx更新（fはコンパイル時定数なので linear）
        argmax_idx_a[f] <== argmax_gt[f].out * f;
        argmax_idx_b[f] <== argmax_gt[f].out * maxIdx[f - 1];
        maxIdx[f] <== argmax_idx_a[f] - argmax_idx_b[f] + maxIdx[f - 1];
    }

    // ===== ステップ3: ピークビンが正常範囲 [NORMAL_LOW_BIN, NORMAL_HIGH_BIN] か判定 =====

    var peakBin = maxIdx[NUM_FREQ_POINTS - 1];

    component geLow = GreaterEqThan(8);  // bin値は最大30 < 2^5 → 8bit余裕あり
    geLow.in[0] <== peakBin;
    geLow.in[1] <== NORMAL_LOW_BIN;

    component leHigh = LessEqThan(8);
    leHigh.in[0] <== peakBin;
    leHigh.in[1] <== NORMAL_HIGH_BIN;

    isNormal <== geLow.out * leHigh.out;
}

/**
 * パラメータ設定:
 *   NUM_FREQ_POINTS = 31  (0.00~0.60Hz, 0.02Hz刻み)
 *   NUM_SUBCARRIERS = 245
 *   SCALE           = 10000
 *   ITER            = 2
 *   NORMAL_LOW_BIN  = 5   (0.10Hz = 5番ビン)
 *   NORMAL_HIGH_BIN = 25  (0.50Hz = 25番ビン)
 */
component main = NormalBreathingCheck(31, 245, 10000, 2, 5, 25);
