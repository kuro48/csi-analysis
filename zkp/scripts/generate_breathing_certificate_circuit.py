#!/usr/bin/env python3
"""csi_breathing_certificate.circom を生成するスクリプト。

docs/ZKP_PIPELINE_EXTENSION_IDEAS.md テーマ1・案A（証明書検証方式）の実装。

既存の csi_breathing_normality.circom は「与えられた単一 VMD モードのピークが
正常帯域内か」しか検証しないため、証明者が都合のよいモードを捏造できる余地が
残っていた。本回路は VMD のアルゴリズムそのものではなく「VMD 出力が満たすべき
性質（証明書）」を検証することで、その余地を狭める。

秘密入力:
    signal[T]     : VMD への入力信号（呼吸PC, 中心化・共通スケール整数）
    modes[K][T]   : VMD が出力した K 個のモード（signal と同一スケール整数）
    sel[K]        : 呼吸モードを指す one-hot ベクトル

公開出力:
    isNormal      : 呼吸あり（正常帯域内 かつ 狭帯域）= 1 / それ以外 = 0

回路内で検証する命題:
    1. 分解の妥当性（ハード制約）:
         - sel は one-hot（各要素 0/1, 総和 1）
         - 再構成性: Σ_k modes[k][t] ≈ signal[t]
           （誤差エネルギー Σ(recon-signal)² ≤ RECON_ERR_RATIO × Σ signal²）
    2. 選択モード（selectedMode = Σ_k sel[k]·modes[k]）の性質:
         - narrowband: DFT ピークパワー / 総パワー ≥ NARROW_RATIO
         - 正常帯域: DFT グローバルピークが [NORMAL_LOW_BIN, NORMAL_HIGH_BIN] 内
    3. isNormal = (正常帯域内) AND (narrowband)

使い方:
    python3 scripts/generate_breathing_certificate_circuit.py

パラメータ（backend/app/services/breathing_pipeline.py と一致させること）:
    T=150 サンプル, Fs=5.0Hz（100Hz→5Hzへ間引き後の30秒窓）
    K=5（VMD_K）, 周波数ビン: 0.05Hz + 0.01Hz×k (k=0..100)
    正常帯域: 0.10Hz(6bpm)=bin5 〜 0.37Hz(≈22bpm)=bin32
"""

import math
from pathlib import Path

T = 150
K = 5
FS = 5.0
FREQ_START = 0.05
FREQ_STEP = 0.01
NUM_FREQ = 101
NORMAL_LOW_BIN = 5    # 0.10 Hz = 6 bpm
NORMAL_HIGH_BIN = 32  # 0.37 Hz ≈ 22.2 bpm
COS_SCALE = 1000
SIGNAL_SCALE = 100    # signal の最大絶対値が SIGNAL_SCALE になるよう正規化

# モードの絶対値上限（ビット幅算出用）。共通スケール適用後、単一モードが signal を
# 超えることがあるため余裕を持たせる。breathing_pipeline 側でこの上限を検証する。
MODE_MAX_ABS = 1000

# 再構成誤差の許容比率: Σ(recon-signal)² ≤ (RECON_ERR_NUM/RECON_ERR_DEN) × Σ signal²
# 既定は保守的（50%）。実データの残差比率を見て締めてよい（pipeline がログ出力）。
RECON_ERR_NUM = 1
RECON_ERR_DEN = 2

# narrowband 判定: peakPower / totalPower ≥ (NARROW_NUM/NARROW_DEN)
# 既定 5%。白色的スペクトル（呼吸でない）を弾く緩い下限。
NARROW_NUM = 1
NARROW_DEN = 20

OUTPUT = Path(__file__).resolve().parent.parent / "circuits" / "csi_breathing_certificate.circom"


def build_table(func) -> str:
    rows = []
    for f in range(NUM_FREQ):
        freq = FREQ_START + f * FREQ_STEP
        row = [round(func(2 * math.pi * freq * t / FS) * COS_SCALE) for t in range(T)]
        rows.append("    [" + ", ".join(str(v) for v in row) + "]")
    return ",\n".join(rows)


def main() -> None:
    # ---- ビット幅算出 ----
    max_x = T * MODE_MAX_ABS * COS_SCALE          # |X_cos|, |X_sin| の上限
    max_power = 2 * max_x * max_x                  # power[f] の上限
    power_bits = max_power.bit_length() + 1        # argmax GreaterThan 用

    total_power_max = NUM_FREQ * max_power
    narrow_lhs_max = max_power * NARROW_DEN
    narrow_rhs_max = total_power_max * NARROW_NUM
    narrow_bits = max(narrow_lhs_max, narrow_rhs_max).bit_length() + 1

    recon_max = K * MODE_MAX_ABS                   # Σ modes の上限
    err_max = recon_max + SIGNAL_SCALE
    err_energy_max = T * err_max * err_max
    sig_energy_max = T * SIGNAL_SCALE * SIGNAL_SCALE
    recon_lhs_max = err_energy_max * RECON_ERR_DEN
    recon_rhs_max = sig_energy_max * RECON_ERR_NUM
    recon_bits = max(recon_lhs_max, recon_rhs_max).bit_length() + 1

    cos_table = build_table(math.cos)
    sin_table = build_table(math.sin)

    circuit = f"""pragma circom 2.0.0;

include "circomlib/circuits/comparators.circom";

/**
 * CSI呼吸モニタリング ZKP 回路（証明書検証方式 / 案A）
 *
 * ※ このファイルは scripts/generate_breathing_certificate_circuit.py により自動生成。
 *    直接編集せずジェネレータを修正して再生成すること。
 *
 * docs/ZKP_PIPELINE_EXTENSION_IDEAS.md テーマ1・案A の実装。
 *
 * 秘密入力:
 *   vmdInput[T]  : VMD 入力信号（呼吸PC, 中心化・共通スケール整数, ±{SIGNAL_SCALE}目安）
 *   modes[K][T]  : VMD 出力 K モード（vmdInput と同一スケール整数）
 *   sel[K]       : 呼吸モードを指す one-hot
 * 公開出力:
 *   isNormal     : 正常帯域内 かつ 狭帯域 = 1 / それ以外 = 0
 *
 * 検証する命題:
 *   1. sel が one-hot（各 0/1, 総和 1）                                （ハード制約）
 *   2. 再構成性: Σ_k modes[k][t] ≈ signal[t]
 *        Σ_t (Σ_k modes[k][t] - signal[t])² × {RECON_ERR_DEN}
 *          ≤ Σ_t signal[t]² × {RECON_ERR_NUM}                          （ハード制約）
 *   3. selectedMode = Σ_k sel[k]·modes[k] の DFT で
 *        - narrowband: peakPower × {NARROW_DEN} ≥ totalPower × {NARROW_NUM}
 *        - 正常帯域: argmax(power) ∈ [{NORMAL_LOW_BIN}, {NORMAL_HIGH_BIN}]
 *   4. isNormal = (正常帯域内) AND (narrowband)
 *
 * ビット幅 (MODE_MAX_ABS={MODE_MAX_ABS}, COS_SCALE={COS_SCALE}, T={T}, K={K}):
 *   max|X|      = {T} × {MODE_MAX_ABS} × {COS_SCALE} = {max_x:,} < 2^{max_x.bit_length()}
 *   power       < {max_power:,} < 2^{max_power.bit_length()}  → GreaterThan({power_bits})
 *   narrowband  → GreaterEqThan({narrow_bits})
 *   再構成      → LessEqThan({recon_bits})
 *
 * テーブル仕様 (Fs={FS}Hz):
 *   COS_TABLE[f][t] = round(cos(2π × ({FREQ_START} + f×{FREQ_STEP}) × t / {FS}) × {COS_SCALE})
 *   SIN_TABLE[f][t] = round(sin(2π × ({FREQ_START} + f×{FREQ_STEP}) × t / {FS}) × {COS_SCALE})
 */

template BreathingCertificateCheck(T, K, NUM_FREQ, NORMAL_LOW_BIN, NORMAL_HIGH_BIN) {{
    signal input vmdInput[T];   // VMD 入力信号（circom 予約語 signal を避けた命名）
    signal input modes[K][T];
    signal input sel[K];
    signal output isNormal;

    var COS_TABLE[{NUM_FREQ}][{T}] = [
{cos_table}
];

    var SIN_TABLE[{NUM_FREQ}][{T}] = [
{sin_table}
];

    // ===== 1. sel one-hot 検証 =====
    var selSum = 0;
    for (var k = 0; k < K; k++) {{
        sel[k] * sel[k] === sel[k];   // booleanity: sel[k] ∈ {{0,1}}
        selSum += sel[k];
    }}
    selSum === 1;

    // ===== 2. selectedMode = Σ_k sel[k]·modes[k] =====
    signal term[K][T];
    signal partial[K][T];
    signal selectedMode[T];
    for (var t = 0; t < T; t++) {{
        term[0][t]    <== sel[0] * modes[0][t];
        partial[0][t] <== term[0][t];
        for (var k = 1; k < K; k++) {{
            term[k][t]    <== sel[k] * modes[k][t];
            partial[k][t] <== partial[k-1][t] + term[k][t];
        }}
        selectedMode[t] <== partial[K-1][t];
    }}

    // ===== 3. 再構成性（ハード制約）: Σ_k modes[k][t] ≈ signal[t] =====
    signal recon[T];
    signal err[T];
    signal errSq[T];
    signal sigSq[T];
    var errEnergyAcc = 0;
    var sigEnergyAcc = 0;
    for (var t = 0; t < T; t++) {{
        var r = 0;
        for (var k = 0; k < K; k++) {{
            r += modes[k][t];
        }}
        recon[t] <== r;
        err[t]   <== recon[t] - vmdInput[t];
        errSq[t] <== err[t] * err[t];
        sigSq[t] <== vmdInput[t] * vmdInput[t];
        errEnergyAcc += errSq[t];
        sigEnergyAcc += sigSq[t];
    }}
    signal errEnergy;
    signal sigEnergy;
    errEnergy <== errEnergyAcc;
    sigEnergy <== sigEnergyAcc;

    component reconOk = LessEqThan({recon_bits});
    reconOk.in[0] <== errEnergy * {RECON_ERR_DEN};
    reconOk.in[1] <== sigEnergy * {RECON_ERR_NUM};
    reconOk.out === 1;

    // ===== 4. selectedMode の DFT パワースペクトル =====
    signal x_cos[NUM_FREQ];
    signal x_sin[NUM_FREQ];
    signal x_cos_sq[NUM_FREQ];
    signal x_sin_sq[NUM_FREQ];
    signal power[NUM_FREQ];
    var totalPowAcc = 0;

    for (var f = 0; f < NUM_FREQ; f++) {{
        var acc_cos = 0;
        var acc_sin = 0;
        for (var t = 0; t < T; t++) {{
            acc_cos += COS_TABLE[f][t] * selectedMode[t];
            acc_sin += SIN_TABLE[f][t] * selectedMode[t];
        }}
        x_cos[f]    <== acc_cos;
        x_sin[f]    <== acc_sin;
        x_cos_sq[f] <== x_cos[f] * x_cos[f];
        x_sin_sq[f] <== x_sin[f] * x_sin[f];
        power[f]    <== x_cos_sq[f] + x_sin_sq[f];
        totalPowAcc += power[f];
    }}
    signal totalPow;
    totalPow <== totalPowAcc;

    // ===== 5. argmax(power) → グローバルピーク =====
    signal maxPow[NUM_FREQ];
    signal maxIdx[NUM_FREQ];
    signal pow_term_a[NUM_FREQ];
    signal pow_term_b[NUM_FREQ];
    signal idx_term_b[NUM_FREQ];
    component gt[NUM_FREQ];

    maxPow[0]     <== power[0];
    maxIdx[0]     <== 0;
    pow_term_a[0] <== 0;
    pow_term_b[0] <== 0;
    idx_term_b[0] <== 0;

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

    // ===== 6. narrowband: peakPower / totalPower ≥ NARROW_NUM/NARROW_DEN =====
    component narrowOk = GreaterEqThan({narrow_bits});
    narrowOk.in[0] <== maxPow[NUM_FREQ-1] * {NARROW_DEN};
    narrowOk.in[1] <== totalPow * {NARROW_NUM};

    // ===== 7. 正常帯域チェック（5-1.ipynb: BPM_MIN <= bpm <= BPM_MAX） =====
    component geLow = GreaterEqThan(8);
    geLow.in[0] <== maxIdx[NUM_FREQ-1];
    geLow.in[1] <== NORMAL_LOW_BIN;

    component leHigh = LessEqThan(8);
    leHigh.in[0] <== maxIdx[NUM_FREQ-1];
    leHigh.in[1] <== NORMAL_HIGH_BIN;

    signal inRange;
    inRange <== geLow.out * leHigh.out;

    isNormal <== inRange * narrowOk.out;
}}

/**
 * パラメータ:
 *   T               = {T}   ({T / FS:.0f}秒 × {FS}Hz)
 *   K               = {K}   (VMD モード数)
 *   NUM_FREQ        = {NUM_FREQ} ({FREQ_START}〜{FREQ_START + (NUM_FREQ - 1) * FREQ_STEP:.2f}Hz, {FREQ_STEP}Hz刻み)
 *   NORMAL_LOW_BIN  = {NORMAL_LOW_BIN}   ({FREQ_START + NORMAL_LOW_BIN * FREQ_STEP:.2f}Hz = 6 bpm)
 *   NORMAL_HIGH_BIN = {NORMAL_HIGH_BIN}  ({FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP:.2f}Hz ≈ 22 bpm)
 */
component main = BreathingCertificateCheck({T}, {K}, {NUM_FREQ}, {NORMAL_LOW_BIN}, {NORMAL_HIGH_BIN});
"""

    OUTPUT.write_text(circuit)
    print(f"Generated: {OUTPUT}")
    print(f"  T={T}, K={K}, NUM_FREQ={NUM_FREQ}")
    print(f"  GreaterThan({power_bits}), GreaterEqThan({narrow_bits}), LessEqThan({recon_bits})")
    print(f"  recon err ratio = {RECON_ERR_NUM}/{RECON_ERR_DEN}, narrow ratio = {NARROW_NUM}/{NARROW_DEN}")
    print(f"  normal band: bin {NORMAL_LOW_BIN} ({(FREQ_START + NORMAL_LOW_BIN * FREQ_STEP) * 60:.1f} bpm)"
          f" .. bin {NORMAL_HIGH_BIN} ({(FREQ_START + NORMAL_HIGH_BIN * FREQ_STEP) * 60:.1f} bpm)")


if __name__ == "__main__":
    main()
