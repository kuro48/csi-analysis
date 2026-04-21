pragma circom 2.0.0;

include "circomlib/circuits/comparators.circom";

/**
 * CSI呼吸モニタリング正常判定回路（MUSIC法版）
 *
 * 設計方針：
 *   秘密入力：MUSIC擬似スペクトル（log圧縮+min-max正規化済み、0.0～0.6Hz、0.02Hz刻み、31点）
 *             ※ Python側でlog10圧縮・サブキャリア単位正規化・線形31点に再ビン化したもの
 *   公開出力：isNormal（ピーク周波数が正常呼吸域内、かつピークが十分に顕著かどうか）
 *
 * 処理フロー：
 *   1. 各サブキャリアの dot・normRef²・normCand² を計算
 *   2. コサイン類似度が最小のサブキャリアを選択（最も参照との乖離が大きい）
 *   3. 選択サブキャリアの candidate スペクトラムを追跡
 *   4. そのスペクトラムの argmax（ピーク周波数ビン）を求める
 *   5. ピーク信頼性チェック: peakVal × CONF_DENOM × NUM_FREQ > totalSum × CONF_NUMER
 *      （MUSIC擬似スペクトルは鋭いピークを持つため、平均値より有意に大きいことを確認）
 *   6. ピークビンが [NORMAL_LOW_BIN, NORMAL_HIGH_BIN] 内 AND 信頼性あり → isNormal = 1
 *
 * コサイン類似度の除算・平方根なし比較:
 *   cos(A) < cos(B)
 *     ⟺  dot_A² × nrB × ncB < dot_B² × nrA × ncA   （全値非負のため成立）
 *
 * ピーク信頼性（除算なし）:
 *   peakVal / mean > CONF_NUMER / CONF_DENOM
 *     ⟺  peakVal × CONF_DENOM × NUM_FREQ_POINTS > totalSum × CONF_NUMER
 *
 * ビット幅（ZKP_SCALE=10000, N=31）:
 *   dot ≤ 31 × 10000² ≈ 3.1×10⁹ < 2^32
 *   dot_sq < 2^64 ;  nrB×ncB < 2^64
 *   lhs_cos = dot_sq × (nrB×ncB) < 2^128  → LessThan(128) を使用
 *   totalSum ≤ 31 × 10000 = 310000 < 2^19
 *   lhsConf = peakVal × CONF_DENOM × NUM_FREQ ≤ 10000 × 1 × 31 = 310000 < 2^19
 *   rhsConf = totalSum × CONF_NUMER ≤ 310000 × 2 = 620000 < 2^20
 *   → GreaterThan(64) で十分
 *
 * 周波数マッピング（0.02Hz刻み、Python側で再ビン化済み）:
 *   bin  0 → 0.00Hz
 *   bin  5 → 0.10Hz  ← NORMAL_LOW_BIN
 *   bin 25 → 0.50Hz  ← NORMAL_HIGH_BIN
 *   bin 30 → 0.60Hz
 *
 * 信頼性パラメータ（component main で指定）:
 *   CONF_NUMER = 2, CONF_DENOM = 1  →  peak > 2 × 平均 を要求
 */

// ===== サブ回路 =====

template MusicSubcarrierDotNorms(N) {
    signal input ref[N];
    signal input cand[N];
    signal output dot;
    signal output normRef2;
    signal output normCand2;

    signal r_sq[N];
    signal c_sq[N];
    signal rc[N];
    signal sum_r[N];
    signal sum_c[N];
    signal sum_rc[N];

    for (var i = 0; i < N; i++) {
        r_sq[i]  <== ref[i]  * ref[i];
        c_sq[i]  <== cand[i] * cand[i];
        rc[i]    <== ref[i]  * cand[i];

        if (i == 0) {
            sum_r[i]  <== r_sq[i];
            sum_c[i]  <== c_sq[i];
            sum_rc[i] <== rc[i];
        } else {
            sum_r[i]  <== sum_r[i-1]  + r_sq[i];
            sum_c[i]  <== sum_c[i-1]  + c_sq[i];
            sum_rc[i] <== sum_rc[i-1] + rc[i];
        }
    }

    dot       <== sum_rc[N-1];
    normRef2  <== sum_r[N-1];
    normCand2 <== sum_c[N-1];
}

// ===== メイン回路 =====

template MusicBreathingCheck(
    NUM_FREQ_POINTS,
    NUM_SUBCARRIERS,
    NORMAL_LOW_BIN,
    NORMAL_HIGH_BIN,
    CONF_NUMER,
    CONF_DENOM
) {
    signal input referenceMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal input candidateMatrix[NUM_FREQ_POINTS][NUM_SUBCARRIERS];
    signal output isNormal;

    // ===== ステップ1: コサイン類似度比較 + 最小類似度サブキャリア選択 =====
    component dn[NUM_SUBCARRIERS];
    signal dots[NUM_SUBCARRIERS];
    signal nrs[NUM_SUBCARRIERS];
    signal ncs[NUM_SUBCARRIERS];

    signal minDot[NUM_SUBCARRIERS];
    signal minNr[NUM_SUBCARRIERS];
    signal minNc[NUM_SUBCARRIERS];

    signal dot_sq[NUM_SUBCARRIERS];
    signal nr_nc[NUM_SUBCARRIERS];
    signal minDot_sq[NUM_SUBCARRIERS];
    signal minNr_minNc[NUM_SUBCARRIERS];
    signal lhs_cos[NUM_SUBCARRIERS];
    signal rhs_cos[NUM_SUBCARRIERS];

    signal dot_term_a[NUM_SUBCARRIERS];
    signal dot_term_b[NUM_SUBCARRIERS];
    signal nr_term_a[NUM_SUBCARRIERS];
    signal nr_term_b[NUM_SUBCARRIERS];
    signal nc_term_a[NUM_SUBCARRIERS];
    signal nc_term_b[NUM_SUBCARRIERS];

    signal selectedSpec[NUM_SUBCARRIERS][NUM_FREQ_POINTS];
    signal spec_term_a[NUM_SUBCARRIERS][NUM_FREQ_POINTS];
    signal spec_term_b[NUM_SUBCARRIERS][NUM_FREQ_POINTS];

    component lt_cos[NUM_SUBCARRIERS];

    for (var sc = 0; sc < NUM_SUBCARRIERS; sc++) {
        dn[sc] = MusicSubcarrierDotNorms(NUM_FREQ_POINTS);
        for (var f = 0; f < NUM_FREQ_POINTS; f++) {
            dn[sc].ref[f]  <== referenceMatrix[f][sc];
            dn[sc].cand[f] <== candidateMatrix[f][sc];
        }
        dots[sc] <== dn[sc].dot;
        nrs[sc]  <== dn[sc].normRef2;
        ncs[sc]  <== dn[sc].normCand2;

        dot_sq[sc] <== dots[sc] * dots[sc];
        nr_nc[sc]  <== nrs[sc]  * ncs[sc];

        if (sc == 0) {
            minDot[0]      <== dots[0];
            minNr[0]       <== nrs[0];
            minNc[0]       <== ncs[0];
            minDot_sq[0]   <== 0;
            minNr_minNc[0] <== 0;
            lhs_cos[0]     <== 0;
            rhs_cos[0]     <== 0;
            dot_term_a[0]  <== 0;
            dot_term_b[0]  <== 0;
            nr_term_a[0]   <== 0;
            nr_term_b[0]   <== 0;
            nc_term_a[0]   <== 0;
            nc_term_b[0]   <== 0;
            for (var f = 0; f < NUM_FREQ_POINTS; f++) {
                selectedSpec[0][f] <== candidateMatrix[f][0];
                spec_term_a[0][f]  <== 0;
                spec_term_b[0][f]  <== 0;
            }
        } else {
            minDot_sq[sc]   <== minDot[sc-1] * minDot[sc-1];
            minNr_minNc[sc] <== minNr[sc-1]  * minNc[sc-1];
            lhs_cos[sc]     <== dot_sq[sc]    * minNr_minNc[sc];
            rhs_cos[sc]     <== minDot_sq[sc] * nr_nc[sc];

            lt_cos[sc] = LessThan(128);
            lt_cos[sc].in[0] <== lhs_cos[sc];
            lt_cos[sc].in[1] <== rhs_cos[sc];

            dot_term_a[sc] <== lt_cos[sc].out * dots[sc];
            dot_term_b[sc] <== lt_cos[sc].out * minDot[sc-1];
            minDot[sc] <== dot_term_a[sc] - dot_term_b[sc] + minDot[sc-1];

            nr_term_a[sc] <== lt_cos[sc].out * nrs[sc];
            nr_term_b[sc] <== lt_cos[sc].out * minNr[sc-1];
            minNr[sc] <== nr_term_a[sc] - nr_term_b[sc] + minNr[sc-1];

            nc_term_a[sc] <== lt_cos[sc].out * ncs[sc];
            nc_term_b[sc] <== lt_cos[sc].out * minNc[sc-1];
            minNc[sc] <== nc_term_a[sc] - nc_term_b[sc] + minNc[sc-1];

            for (var f = 0; f < NUM_FREQ_POINTS; f++) {
                spec_term_a[sc][f] <== lt_cos[sc].out * candidateMatrix[f][sc];
                spec_term_b[sc][f] <== lt_cos[sc].out * selectedSpec[sc-1][f];
                selectedSpec[sc][f] <== spec_term_a[sc][f] - spec_term_b[sc][f] + selectedSpec[sc-1][f];
            }
        }
    }

    // ===== ステップ2: 選択スペクトラムの argmax =====
    signal maxVal[NUM_FREQ_POINTS];
    signal maxIdx[NUM_FREQ_POINTS];
    signal argmax_val_a[NUM_FREQ_POINTS];
    signal argmax_val_b[NUM_FREQ_POINTS];
    signal argmax_idx_a[NUM_FREQ_POINTS];
    signal argmax_idx_b[NUM_FREQ_POINTS];
    component argmax_gt[NUM_FREQ_POINTS];

    maxVal[0]       <== selectedSpec[NUM_SUBCARRIERS - 1][0];
    maxIdx[0]       <== 0;
    argmax_val_a[0] <== 0;
    argmax_val_b[0] <== 0;
    argmax_idx_a[0] <== 0;
    argmax_idx_b[0] <== 0;

    for (var f = 1; f < NUM_FREQ_POINTS; f++) {
        argmax_gt[f] = GreaterThan(64);
        argmax_gt[f].in[0] <== selectedSpec[NUM_SUBCARRIERS - 1][f];
        argmax_gt[f].in[1] <== maxVal[f - 1];

        argmax_val_a[f] <== argmax_gt[f].out * selectedSpec[NUM_SUBCARRIERS - 1][f];
        argmax_val_b[f] <== argmax_gt[f].out * maxVal[f - 1];
        maxVal[f] <== argmax_val_a[f] - argmax_val_b[f] + maxVal[f - 1];

        argmax_idx_a[f] <== argmax_gt[f].out * f;
        argmax_idx_b[f] <== argmax_gt[f].out * maxIdx[f - 1];
        maxIdx[f] <== argmax_idx_a[f] - argmax_idx_b[f] + maxIdx[f - 1];
    }

    // ===== ステップ3: ピーク信頼性チェック（MUSIC特有） =====
    // totalSum = 選択サブキャリアのスペクトル全ビン合計
    signal totalSum[NUM_FREQ_POINTS];
    totalSum[0] <== selectedSpec[NUM_SUBCARRIERS - 1][0];
    for (var f = 1; f < NUM_FREQ_POINTS; f++) {
        totalSum[f] <== totalSum[f-1] + selectedSpec[NUM_SUBCARRIERS - 1][f];
    }

    // peakVal × CONF_DENOM × NUM_FREQ_POINTS > totalSum × CONF_NUMER
    // CONF_DENOM * NUM_FREQ_POINTS はコンパイル時定数 → 線形制約
    signal lhsConf <== maxVal[NUM_FREQ_POINTS - 1] * (CONF_DENOM * NUM_FREQ_POINTS);
    signal rhsConf <== totalSum[NUM_FREQ_POINTS - 1] * CONF_NUMER;

    component gtConf = GreaterThan(64);
    gtConf.in[0] <== lhsConf;
    gtConf.in[1] <== rhsConf;

    // ===== ステップ4: ピーク周波数が正常範囲 [LOW, HIGH] 内かチェック =====
    component geLow = GreaterEqThan(8);
    geLow.in[0] <== maxIdx[NUM_FREQ_POINTS - 1];
    geLow.in[1] <== NORMAL_LOW_BIN;

    component leHigh = LessEqThan(8);
    leHigh.in[0] <== maxIdx[NUM_FREQ_POINTS - 1];
    leHigh.in[1] <== NORMAL_HIGH_BIN;

    // isNormal = inRange AND isPeakConfident
    signal inRange <== geLow.out * leHigh.out;
    isNormal <== inRange * gtConf.out;
}

/**
 * パラメータ:
 *   NUM_FREQ_POINTS = 31  (0.00～0.60Hz, 0.02Hz刻み、Python側で線形再ビン化)
 *   NUM_SUBCARRIERS = 245
 *   NORMAL_LOW_BIN  = 5   (0.10Hz)
 *   NORMAL_HIGH_BIN = 25  (0.50Hz)
 *   CONF_NUMER      = 2   (ピーク > 2 × 平均 を要求)
 *   CONF_DENOM      = 1
 */
component main = MusicBreathingCheck(31, 245, 5, 25, 2, 1);
