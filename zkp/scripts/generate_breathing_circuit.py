#!/usr/bin/env python3
"""csi_breathing_normality.circom を生成するスクリプト。

5-1.ipynb パイプラインの最終判定
「VMD呼吸成分のFFTグローバルピークが BPM_MIN〜BPM_MAX (6〜22 bpm) 内か」
を回路内 DFT で再現するための COS/SIN テーブルと判定ロジックを出力する。

使い方:
    python3 scripts/generate_breathing_circuit.py

パラメータ（backend/app/services/breathing_pipeline.py と一致させること）:
    T=150 サンプル, Fs=5.0Hz（100Hz→5Hzへ間引き後の30秒窓）
    周波数ビン: 0.05Hz + 0.01Hz×k (k=0..100) → 0.05〜1.05Hz
    正常帯域: 0.10Hz(6bpm)=bin5 〜 0.37Hz(≈22bpm)=bin32
"""

import math
from pathlib import Path

T = 150
FS = 5.0
FREQ_START = 0.05
FREQ_STEP = 0.01
NUM_FREQ = 101
NORMAL_LOW_BIN = 5    # 0.10 Hz = 6 bpm
NORMAL_HIGH_BIN = 32  # 0.37 Hz ≈ 22.2 bpm（22bpm=0.3667Hzに最も近いビン）
COS_SCALE = 1000
SIGNAL_SCALE = 100    # 入力は ±SIGNAL_SCALE の整数

OUTPUT = Path(__file__).resolve().parent.parent / "circuits" / "csi_breathing_normality.circom"


def build_table(func) -> str:
    rows = []
    for f in range(NUM_FREQ):
        freq = FREQ_START + f * FREQ_STEP
        row = [round(func(2 * math.pi * freq * t / FS) * COS_SCALE) for t in range(T)]
        rows.append("    [" + ", ".join(str(v) for v in row) + "]")
    return ",\n".join(rows)


def main() -> None:
    # ビット幅: |X| <= T×SIGNAL_SCALE×COS_SCALE = 15,000,000 < 2^24
    #           power <= 2×(1.5e7)^2 = 4.5e14 < 2^49 → GreaterThan(50)
    max_x = T * SIGNAL_SCALE * COS_SCALE
    max_power = 2 * max_x * max_x
    power_bits = max_power.bit_length() + 1  # 余裕1bit

    cos_table = build_table(math.cos)
    sin_table = build_table(math.sin)

    circuit = f"""pragma circom 2.0.0;

include "circomlib/circuits/comparators.circom";

/**
 * CSI呼吸モニタリング ZKP 回路（5-1.ipynb パイプライン正常判定版）
 *
 * ※ このファイルは scripts/generate_breathing_circuit.py により自動生成。
 *    直接編集せずジェネレータを修正して再生成すること。
 *
 * 設計方針:
 *   秘密入力: 5-1.ipynb パイプライン（SNRサブキャリア選択→バンドパス→PCA→VMD）
 *            で抽出した呼吸成分 vmd[T]
 *            （T={T} サンプル, Fs={FS}Hz, ゼロ中心化・±{SIGNAL_SCALE}正規化済み整数）
 *   公開出力: isNormal（呼吸あり=1 / なし=0）
 *
 * 回路内で行うこと（5-1.ipynb の「呼吸あり/なし判定」を回路内で再現）:
 *   1. DFT近似でパワースペクトル計算:
 *        X_cos[f] = Σ_t vmd[t] × COS_TABLE[f][t]
 *        X_sin[f] = Σ_t vmd[t] × SIN_TABLE[f][t]
 *        power[f] = X_cos[f]² + X_sin[f]²
 *   2. argmax(power) → グローバルピーク周波数ビン
 *   3. ピークが [NORMAL_LOW_BIN, NORMAL_HIGH_BIN] 内 → isNormal = 1
 *
 * ビット幅 (SIGNAL_SCALE={SIGNAL_SCALE}, COS_SCALE={COS_SCALE}, T={T}):
 *   max|X| = {T} × {SIGNAL_SCALE} × {COS_SCALE} = {max_x:,} < 2^24
 *   power < 2 × ({max_x:,})² < 2^{power_bits - 1}  → GreaterThan({power_bits}) を使用
 *
 * テーブル仕様 (Fs={FS}Hz):
 *   COS_TABLE[f][t] = round(cos(2π × ({FREQ_START} + f×{FREQ_STEP}) × t / {FS}) × {COS_SCALE})
 *   SIN_TABLE[f][t] = round(sin(2π × ({FREQ_START} + f×{FREQ_STEP}) × t / {FS}) × {COS_SCALE})
 *
 * 周波数マッピング ({FREQ_STEP}Hz刻みビン, {FREQ_START}Hz開始):
 *   bin {NORMAL_LOW_BIN:3d} → {FREQ_START + NORMAL_LOW_BIN * FREQ_STEP:.2f}Hz =  {(FREQ_START + NORMAL_LOW_BIN * FREQ_STEP) * 60:.1f} bpm ← NORMAL_LOW_BIN  (BPM_MIN=6)
 *   bin {NORMAL_HIGH_BIN:3d} → {FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP:.2f}Hz ≈ {(FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP) * 60:.1f} bpm ← NORMAL_HIGH_BIN (BPM_MAX=22)
 *   bin {NUM_FREQ - 1:3d} → {FREQ_START + (NUM_FREQ - 1) * FREQ_STEP:.2f}Hz（バンドパス上限 1.0Hz をカバー）
 */

template BreathingNormalityCheck(T, NUM_FREQ, NORMAL_LOW_BIN, NORMAL_HIGH_BIN) {{
    signal input vmd[T];
    signal output isNormal;

    var COS_TABLE[{NUM_FREQ}][{T}] = [
{cos_table}
];

    var SIN_TABLE[{NUM_FREQ}][{T}] = [
{sin_table}
];

    signal x_cos[NUM_FREQ];
    signal x_sin[NUM_FREQ];
    signal x_cos_sq[NUM_FREQ];
    signal x_sin_sq[NUM_FREQ];
    signal power[NUM_FREQ];

    for (var f = 0; f < NUM_FREQ; f++) {{
        var acc_cos = 0;
        var acc_sin = 0;
        for (var t = 0; t < T; t++) {{
            acc_cos += COS_TABLE[f][t] * vmd[t];
            acc_sin += SIN_TABLE[f][t] * vmd[t];
        }}
        x_cos[f] <== acc_cos;
        x_sin[f] <== acc_sin;
        x_cos_sq[f] <== x_cos[f] * x_cos[f];
        x_sin_sq[f] <== x_sin[f] * x_sin[f];
        power[f]    <== x_cos_sq[f] + x_sin_sq[f];
    }}

    // ===== argmax(power) =====
    signal maxPow[NUM_FREQ];
    signal maxIdx[NUM_FREQ];
    signal pow_term_a[NUM_FREQ];
    signal pow_term_b[NUM_FREQ];
    signal idx_term_b[NUM_FREQ];
    component gt[NUM_FREQ];

    maxPow[0]      <== power[0];
    maxIdx[0]      <== 0;
    pow_term_a[0]  <== 0;
    pow_term_b[0]  <== 0;
    idx_term_b[0]  <== 0;

    for (var f = 1; f < NUM_FREQ; f++) {{
        gt[f] = GreaterThan({power_bits});
        gt[f].in[0] <== power[f];
        gt[f].in[1] <== maxPow[f-1];

        pow_term_a[f] <== gt[f].out * power[f];
        pow_term_b[f] <== gt[f].out * maxPow[f-1];
        maxPow[f] <== pow_term_a[f] - pow_term_b[f] + maxPow[f-1];

        idx_term_b[f] <== gt[f].out * maxIdx[f-1];
        maxIdx[f] <== f * gt[f].out - idx_term_b[f] + maxIdx[f-1];
    }}

    // ===== 正常範囲チェック（5-1.ipynb: BPM_MIN <= bpm <= BPM_MAX） =====
    component geLow = GreaterEqThan(8);
    geLow.in[0] <== maxIdx[NUM_FREQ-1];
    geLow.in[1] <== NORMAL_LOW_BIN;

    component leHigh = LessEqThan(8);
    leHigh.in[0] <== maxIdx[NUM_FREQ-1];
    leHigh.in[1] <== NORMAL_HIGH_BIN;

    isNormal <== geLow.out * leHigh.out;
}}

/**
 * パラメータ:
 *   T               = {T}   ({T / FS:.0f}秒 × {FS}Hz)
 *   NUM_FREQ        = {NUM_FREQ} ({FREQ_START}〜{FREQ_START + (NUM_FREQ - 1) * FREQ_STEP:.2f}Hz, {FREQ_STEP}Hz刻み)
 *   NORMAL_LOW_BIN  = {NORMAL_LOW_BIN}   ({FREQ_START + NORMAL_LOW_BIN * FREQ_STEP:.2f}Hz = 6 bpm)
 *   NORMAL_HIGH_BIN = {NORMAL_HIGH_BIN}  ({FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP:.2f}Hz ≈ 22 bpm)
 */
component main = BreathingNormalityCheck({T}, {NUM_FREQ}, {NORMAL_LOW_BIN}, {NORMAL_HIGH_BIN});
"""

    OUTPUT.write_text(circuit)
    print(f"Generated: {OUTPUT}")
    print(f"  NUM_FREQ={NUM_FREQ}, T={T}, GreaterThan({power_bits})")
    print(f"  normal band: bin {NORMAL_LOW_BIN} ({(FREQ_START + NORMAL_LOW_BIN * FREQ_STEP) * 60:.1f} bpm)"
          f" .. bin {NORMAL_HIGH_BIN} ({(FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP) * 60:.1f} bpm)")


if __name__ == "__main__":
    main()
