pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

/**
 * CSI呼吸数検証回路（超シンプル版・学習用）
 *
 * この回路は3つのシンプルな検証のみを行います：
 * 1. 呼吸数が正常範囲内（10-30 bpm）
 * 2. 信頼度スコアが十分に高い（70%以上）
 * 3. すべての検証が成功した場合のみ isValid = 1
 */
template BreathingVerifier() {
    // 公開入力（誰でも見られる情報）
    signal input breathingRate;          // 呼吸数（回/分）
    signal input confidenceScore;        // 信頼度スコア（0-100）

    // 出力（検証結果）
    signal output isValid;

    // === 検証1: 呼吸数が10以上であることを確認 ===
    component minCheck = GreaterEqThan(8);  // 8ビット比較器
    minCheck.in[0] <== breathingRate;
    minCheck.in[1] <== 10;  // 最小値: 10 bpm

    // === 検証2: 呼吸数が30以下であることを確認 ===
    component maxCheck = LessEqThan(8);  // 8ビット比較器
    maxCheck.in[0] <== breathingRate;
    maxCheck.in[1] <== 30;  // 最大値: 30 bpm

    // === 検証3: 信頼度スコアが70以上であることを確認 ===
    component confidenceCheck = GreaterEqThan(8);  // 8ビット比較器
    confidenceCheck.in[0] <== confidenceScore;
    confidenceCheck.in[1] <== 70;  // 閾値: 70%

    // === すべての検証結果を組み合わせる ===
    // すべてが1（真）の場合のみ、最終結果が1になる
    signal check1and2;
    check1and2 <== minCheck.out * maxCheck.out;

    signal finalCheck;
    finalCheck <== check1and2 * confidenceCheck.out;

    // 最終的な検証結果を出力
    isValid <== finalCheck;
}

// メインコンポーネントの宣言
// breathingRateとconfidenceScoreを公開入力として指定
component main {public [breathingRate, confidenceScore]} = BreathingVerifier();
