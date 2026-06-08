"""
csi_main_to_zkp.py

PicoScenes .csi ファイルを受け取り、ベース行列（base_matrix.json）と合わせて
ZKP証明（Groth16）を生成して結果をJSONで保存する。

使い方:
    python csi_main_to_zkp.py <csi_file> --base base_matrix.json \\
        [--zkp-dir ../zkp] [--output zkp_result.json]

前提:
    - base_matrix.json: csi_base_to_zkp.py が生成したベース行列JSON
    - node / snarkjs がPATH上に存在すること
    - zkp/build/csi_full_similarity_js/csi_full_similarity.wasm が存在すること
    - zkp/keys/csi_full_similarity_final.zkey が存在すること

出力 JSON:
    {
        "proof": { ... },              // Groth16証明オブジェクト
        "publicSignals": ["0" or "1"], // isNormal
        "isNormal": bool,
        "bpm_fft": float | null,       // FFTから推定した呼吸数 BPM
        "num_freq_points": int,
        "num_subcarriers": int,
        "bandwidth_mhz": int,
        "source_file": str,
        "base_file": str,
        "created_at": str              // ISO8601
    }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
plt.rcParams["font.family"] = ["Hiragino Sans", "AppleGothic", "IPAexGothic", "sans-serif"]
import numpy as np
import pandas as pd
from scipy.signal import detrend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# パラメータ（csi_full_similarity.circom および PCAPAnalyzer と同期）  #
# ------------------------------------------------------------------ #

DOWNSAMPLE_INTERVAL_S: float = 0.01
FREQUENCY_BIN_STEP: float = 0.01

ZKP_FREQ_START: float = 0.0
ZKP_FREQ_END: float = 0.60
ZKP_SCALE: int = 10000

EXPECTED_FREQ_POINTS: int = 31
EXPECTED_SUBCARRIERS: int = 245

# 80MHz (VHT80 / HE80): subcarrier indices -128..+127
_CFG_80: dict = {
    "guard_bands": [(-128, -122), (122, 127)],
    "pilots": [-103, -75, -39, -11, 11, 39, 75, 103],
}

# 160MHz (VHT160 / HE160): subcarrier indices -256..+255
_CFG_160: dict = {
    "guard_bands": [(-256, -250), (250, 255)],
    "pilots": [
        -231, -203, -167, -139, -117, -89, -53, -25,
          25,   53,   89,  117,  139, 167, 203, 231,
    ],
}

CHANNEL_CONFIGS: dict[int, dict] = {80: _CFG_80, 160: _CFG_160}

GUARD_BANDS: list[tuple[int, int]] = _CFG_80["guard_bands"]
PILOTS: list[int] = _CFG_80["pilots"]

# 呼吸数推定レンジ（一般的な安静時呼吸: 6〜30 BPM = 0.1〜0.5 Hz）
BREATHING_FREQ_MIN: float = 0.1
BREATHING_FREQ_MAX: float = 0.5


def _mag_cols(df: pd.DataFrame) -> list[str]:
    """振幅列（整数インデックス名の列）だけを返す。位相列を除外するために使う。"""
    return [c for c in df.columns if c.lstrip("-").isdigit()]


def estimate_bpm(freq_df: pd.DataFrame) -> float | None:
    """周波数スペクトルから呼吸数（BPM）を推定する。

    Wavelet/MUSIC の _mean 列がある場合はそちらを優先する。
    """
    if freq_df.empty or "frequency" not in freq_df.columns:
        return None

    mask = (freq_df["frequency"] >= BREATHING_FREQ_MIN) & (freq_df["frequency"] <= BREATHING_FREQ_MAX)
    sub_df = freq_df[mask]
    if sub_df.empty:
        return None

    if "_mean" in sub_df.columns:
        mean_spectrum = sub_df["_mean"].values.astype(np.float64)
    else:
        data_cols = [
            c for c in sub_df.columns
            if c not in {"frequency"} and not c.startswith("_")
            and pd.api.types.is_numeric_dtype(sub_df[c])
        ]
        if not data_cols:
            return None
        mean_spectrum = sub_df[data_cols].mean(axis=1).values.astype(np.float64)

    peak_idx = int(np.argmax(mean_spectrum))
    peak_freq = float(sub_df["frequency"].values[peak_idx])
    return round(peak_freq * 60, 1)


# ------------------------------------------------------------------ #
# グラフ出力ユーティリティ                                              #
# ------------------------------------------------------------------ #

def _show_plot(fig: plt.Figure, title: str) -> None:
    if hasattr(fig.canvas, "manager") and fig.canvas.manager:
        fig.canvas.manager.set_window_title(title)
    plt.show()


def _plot_step1(df: pd.DataFrame) -> None:
    mag_cols = _mag_cols(df)
    phase_cols = [c for c in df.columns if c.endswith("_phase")]
    has_phase = len(phase_cols) > 0

    n_rows = 2 if has_phase else 1
    fig, axes = plt.subplots(n_rows, 1, figsize=(12, 5 * n_rows))
    if n_rows == 1:
        axes = [axes]

    for col in mag_cols:
        axes[0].plot(df[col].values, alpha=0.4, linewidth=0.5)
    axes[0].set_xlabel("フレーム番号")
    axes[0].set_ylabel("振幅")
    axes[0].set_title(f"Step 1: 生CSI振幅\n{len(df)} フレーム, {len(mag_cols)} サブキャリア")
    axes[0].grid(True, alpha=0.3)

    if has_phase:
        for col in phase_cols:
            axes[1].plot(df[col].values, alpha=0.4, linewidth=0.5)
        axes[1].set_xlabel("フレーム番号")
        axes[1].set_ylabel("位相 (rad)")
        axes[1].set_title(f"Step 1: 生CSI位相\n{len(df)} フレーム, {len(phase_cols)} サブキャリア")
        axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, "Step 1: 生CSI振幅・位相")


def _plot_step2_3(
    before_frame_count: int,
    after_frame_count: int,
    before_sc_cols: list[str],
    df: pd.DataFrame,
    bandwidth_mhz: int = 80,
) -> None:
    cfg = CHANNEL_CONFIGS.get(bandwidth_mhz, _CFG_80)
    after_sc_cols = _mag_cols(df)
    dropped_frames = before_frame_count - after_frame_count
    frame_drop_rate = dropped_frames / before_frame_count * 100 if before_frame_count > 0 else 0.0
    removed_sc = set(before_sc_cols) - set(after_sc_cols)
    removed_dc = 1 if "0" in removed_sc else 0
    removed_guard = sum(1 for s, e in cfg["guard_bands"] for i in range(s, e + 1) if str(i) in removed_sc)
    removed_pilot = sum(1 for p in cfg["pilots"] if str(p) in removed_sc)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    bars = axes[0].bar(["削除前", "削除後"], [before_frame_count, after_frame_count],
                       color=["#e74c3c", "#2ecc71"], width=0.5)
    axes[0].set_ylabel("フレーム数")
    axes[0].set_title(f"Step 2: 無効行削除\n{dropped_frames} 行削除 / 削除率 {frame_drop_rate:.1f}%")
    for bar, val in zip(bars, [before_frame_count, after_frame_count]):
        axes[0].text(bar.get_x() + bar.get_width() / 2, val + 0.3, str(val), ha="center", fontweight="bold")
    axes[0].grid(True, axis="y", alpha=0.3)

    bars2 = axes[1].bar(["除去前", "除去後"], [len(before_sc_cols), len(after_sc_cols)],
                        color=["#e74c3c", "#2ecc71"], width=0.5)
    detail = f"DC:{removed_dc}  ガード:{removed_guard}  パイロット:{removed_pilot}"
    axes[1].set_ylabel("サブキャリア数")
    axes[1].set_title(f"Step 3: 不要サブキャリア除去\n{len(removed_sc)} 列除去 — {detail}")
    for bar, val in zip(bars2, [len(before_sc_cols), len(after_sc_cols)]):
        axes[1].text(bar.get_x() + bar.get_width() / 2, val + 0.3, str(val), ha="center", fontweight="bold")
    axes[1].grid(True, axis="y", alpha=0.3)

    for col in after_sc_cols:
        axes[2].plot(df[col].values, alpha=0.4, linewidth=0.5)
    axes[2].set_xlabel("フレーム番号")
    axes[2].set_ylabel("振幅")
    axes[2].set_title(f"Step 2–3 後: クリーニング済み振幅\n{len(df)} フレーム, {len(after_sc_cols)} サブキャリア")
    axes[2].grid(True, alpha=0.3)
    fig.tight_layout()
    _show_plot(fig, "Step 2–3: クリーニング")


def _plot_step3_5(df_before: pd.DataFrame, df_after: pd.DataFrame) -> None:
    mag_cols = _mag_cols(df_before)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    axes[0].plot(df_before[mag_cols].mean(axis=1).values, label="差分除去前", alpha=0.8, linewidth=1.0)
    axes[0].plot(df_after[mag_cols].mean(axis=1).values, label="差分除去後", alpha=0.8, linewidth=1.0)
    axes[0].set_xlabel("フレーム番号")
    axes[0].set_ylabel("平均振幅（全サブキャリア）")
    axes[0].set_title("Step 3.5: 背景差分除去（全サブキャリア平均）")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].hist(df_before[mag_cols].values.flatten(), bins=60, alpha=0.5,
                 label="差分除去前", color="#e74c3c", density=True)
    axes[1].hist(df_after[mag_cols].values.flatten(), bins=60, alpha=0.5,
                 label="差分除去後", color="#2ecc71", density=True)
    axes[1].set_xlabel("振幅")
    axes[1].set_ylabel("密度")
    axes[1].set_title("Step 3.5: 振幅分布の比較")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    for col in mag_cols:
        axes[2].plot(df_after[col].values, alpha=0.4, linewidth=0.5)
    axes[2].axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    axes[2].set_xlabel("フレーム番号")
    axes[2].set_ylabel("振幅（動的成分）")
    axes[2].set_title(f"Step 3.5: 全サブキャリアの動的成分\n{len(mag_cols)} サブキャリア")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, "Step 3.5: 背景差分除去")


def _plot_step4_fft(fft_df: pd.DataFrame) -> None:
    data_cols = [c for c in fft_df.columns if c != "frequency"]
    freqs = fft_df["frequency"].values
    bpm = estimate_bpm(fft_df)

    fig, ax = plt.subplots(figsize=(12, 5))
    for col in data_cols:
        ax.plot(freqs, fft_df[col].values, alpha=0.4, linewidth=0.5)
    ax.axvspan(ZKP_FREQ_START, ZKP_FREQ_END, alpha=0.15, color="red",
               label=f"ZKP帯域 ({ZKP_FREQ_START}–{ZKP_FREQ_END} Hz)")
    if bpm is not None:
        peak_freq = bpm / 60.0
        ax.axvline(peak_freq, color="orange", linewidth=1.5, linestyle="--",
                   label=f"推定ピーク {peak_freq:.3f} Hz ({bpm} BPM)")
    ax.set_xlabel("周波数 (Hz)")
    ax.set_ylabel("振幅")
    bpm_str = f" / 推定 {bpm} BPM" if bpm is not None else ""
    ax.set_title(f"Step 4: FFTスペクトル{bpm_str}\n{len(data_cols)} サブキャリア, {len(freqs)} 周波数点")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _show_plot(fig, "Step 4: FFT")


def _plot_step5(binned_df: pd.DataFrame, method_name: str = "") -> None:
    data_cols = [
        c for c in binned_df.columns
        if c not in {"freq_interval"} and not c.startswith("_")
        and pd.api.types.is_numeric_dtype(binned_df[c])
    ]
    midpoints = binned_df["freq_interval"].apply(
        lambda v: float(v.mid) if hasattr(v, "mid") else 0.0
    ).values
    label = f" [{method_name}]" if method_name else ""
    fig, ax = plt.subplots(figsize=(12, 5))
    for col in data_cols:
        ax.plot(midpoints, binned_df[col].values, alpha=0.4, linewidth=0.5)
    ax.axvspan(ZKP_FREQ_START, ZKP_FREQ_END, alpha=0.15, color="red",
               label=f"ZKP帯域 ({ZKP_FREQ_START}–{ZKP_FREQ_END} Hz)")
    ax.set_xlabel("周波数 (Hz)")
    ax.set_ylabel("振幅")
    ax.set_title(f"Step 5{label}: 周波数ビン平均化\n{len(data_cols)} サブキャリア, {len(midpoints)} ビン")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _show_plot(fig, f"Step 5{label}")


def _plot_step6_matrix(matrix: list[list[int]], method_name: str = "") -> None:
    data = np.array(matrix, dtype=np.float32)
    n_freq, n_sc = data.shape
    label = f" [{method_name}]" if method_name else ""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for sc_idx in range(n_sc):
        axes[0].plot(np.arange(n_freq), data[:, sc_idx], alpha=0.4, linewidth=0.5)
    axes[0].set_xlabel("周波数ポイントインデックス")
    axes[0].set_ylabel(f"スケール済み振幅 (0–{ZKP_SCALE})")
    axes[0].set_title(f"Step 6{label}: ZKP候補行列\n{n_freq} 周波数ポイント × {n_sc} サブキャリア")
    axes[0].grid(True, alpha=0.3)
    axes[1].hist(data.flatten(), bins=60, color="#9b59b6", alpha=0.8, edgecolor="white")
    axes[1].set_xlabel(f"値 (0 – {ZKP_SCALE})")
    axes[1].set_ylabel("頻度")
    axes[1].set_title(f"Step 6{label}: 値分布")
    axes[1].grid(True, alpha=0.3)
    stats_text = (
        f"min = {int(data.min())}\n"
        f"max = {int(data.max())}\n"
        f"mean = {data.mean():.1f}\n"
        f"non-zero = {int(np.count_nonzero(data))}"
    )
    axes[1].text(0.97, 0.97, stats_text, transform=axes[1].transAxes, ha="right", va="top",
                 fontsize=9, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.6))
    fig.tight_layout()
    _show_plot(fig, f"Step 6{label}: ZKP候補行列")


def _plot_comparison(
    reference_matrix: list[list[int]],
    candidate_matrix: list[list[int]],
    is_normal: bool,
) -> None:
    ref = np.array(reference_matrix, dtype=np.float32)
    cand = np.array(candidate_matrix, dtype=np.float32)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, data, title in zip(
        axes[:2], [ref, cand], ["ベース行列 (reference)", "候補行列 (candidate)"]
    ):
        im = ax.imshow(data, aspect="auto", origin="lower", cmap="viridis", vmin=0, vmax=ZKP_SCALE)
        plt.colorbar(im, ax=ax, label=f"値 (0–{ZKP_SCALE})")
        ax.set_xlabel("サブキャリアインデックス")
        ax.set_ylabel("周波数ポイントインデックス")
        ax.set_title(title)
    diff = cand - ref
    im3 = axes[2].imshow(diff, aspect="auto", origin="lower", cmap="RdBu_r",
                         vmin=-ZKP_SCALE, vmax=ZKP_SCALE)
    plt.colorbar(im3, ax=axes[2], label="差分（候補 − ベース）")
    axes[2].set_xlabel("サブキャリアインデックス")
    axes[2].set_ylabel("周波数ポイントインデックス")
    result_str = "正常 (isNormal=True)" if is_normal else "異常 (isNormal=False)"
    axes[2].set_title(f"差分行列\nZKP結果: {result_str}")
    fig.suptitle("ZKP入力比較: ベース vs 候補", fontsize=13, fontweight="bold")
    fig.tight_layout()
    _show_plot(fig, "ZKP入力比較")


# ------------------------------------------------------------------ #
# Step 1: PicoScenes .csi → DataFrame                                #
# ------------------------------------------------------------------ #

def load_csi_to_dataframe(file_path: str) -> pd.DataFrame:
    """PicoScenes Python Toolbox で .csi を DataFrame に変換する。

    Returns:
        columns: ["timestamp", "<subcarrier_index>", "<subcarrier_index>_phase", ...]
        timestamp は datetime64[ns]
        サブキャリア列は振幅（float32）、位相列は位相（float32, rad）
    """
    try:
        from picoscenes import Picoscenes
    except ImportError as exc:
        raise RuntimeError(
            "picoscenes パッケージがインストールされていません。\n"
            "pip install 'picoscenes @ git+https://github.com/wifisensing/PicoScenes-Python-Toolbox.git' "
            "でインストールしてください。"
        ) from exc

    logger.info(f"PicoScenes ファイル読み込み開始: {file_path}")
    frames_obj = Picoscenes(file_path)
    raw_frames = getattr(frames_obj, "raw", None)
    if not raw_frames:
        raise ValueError("PicoScenes ファイルにフレームがありません")

    first = raw_frames[0]
    csi_info = first.get("CSI") or {}
    rx_info = first.get("RxSBasic") or {}

    num_tones = int(csi_info.get("numTones", 0))
    num_sts = int(rx_info.get("numSTS", 1) or 1)
    num_rx = int(rx_info.get("numRx", csi_info.get("numRx", 1)) or 1)
    subcarrier_indices = np.asarray(csi_info.get("SubcarrierIndex", []), dtype=np.int32)

    if num_tones <= 0 or subcarrier_indices.size != num_tones:
        raise ValueError("PicoScenes メタデータ不正: numTones / SubcarrierIndex の不一致")

    mag_array = np.empty((len(raw_frames), num_tones), dtype=np.float32)
    phase_array = np.empty((len(raw_frames), num_tones), dtype=np.float32)
    timestamps: list = []
    valid_count = 0
    fallback_ns: int | None = None
    has_phase = False

    for frame_idx, frame in enumerate(raw_frames):
        frame_csi = frame.get("CSI") or {}
        frame_rx = frame.get("RxSBasic") or {}
        mag = np.asarray(frame_csi.get("Mag", []), dtype=np.float32)
        phase_raw = np.asarray(frame_csi.get("Phase", []), dtype=np.float32)

        if mag.size != num_tones * num_sts * num_rx:
            logger.debug(f"フレーム {frame_idx} をスキップ (Mag サイズ不正: {mag.size})")
            continue

        mag_matrix = mag.reshape((num_tones, num_sts, num_rx), order="F")
        tone_mag = mag_matrix[:, 0, 0]

        if phase_raw.size == num_tones * num_sts * num_rx:
            tone_phase = phase_raw.reshape((num_tones, num_sts, num_rx), order="F")[:, 0, 0]
            has_phase = True
        else:
            tone_phase = np.zeros(num_tones, dtype=np.float32)

        system_ns = frame_rx.get("systemns")
        if system_ns is None:
            if fallback_ns is None:
                fallback_ns = 0
            else:
                fallback_ns += int(DOWNSAMPLE_INTERVAL_S * 1_000_000_000)
            system_ns = fallback_ns

        mag_array[valid_count, :] = tone_mag
        phase_array[valid_count, :] = tone_phase
        timestamps.append(pd.to_datetime(int(system_ns), unit="ns", errors="coerce"))
        valid_count += 1

    if valid_count == 0:
        raise ValueError("有効なフレームを変換できませんでした")

    col_names = [str(int(i)) for i in subcarrier_indices]
    phase_col_names = [f"{str(int(i))}_phase" for i in subcarrier_indices]

    df = pd.DataFrame(mag_array[:valid_count], columns=col_names)
    if has_phase:
        phase_df = pd.DataFrame(phase_array[:valid_count], columns=phase_col_names)
        df = pd.concat([df, phase_df], axis=1)
    df.insert(0, "timestamp", timestamps)

    ts_series = pd.to_datetime(df["timestamp"])
    duration_s = (ts_series.iloc[-1] - ts_series.iloc[0]).total_seconds()

    max_abs_sc = int(np.max(np.abs(subcarrier_indices))) if subcarrier_indices.size > 0 else 0
    detected_bw = 160 if max_abs_sc > 200 else 80
    df.attrs["bandwidth_mhz"] = detected_bw

    logger.info(
        f"DataFrame 作成完了: フレーム={valid_count}, サブキャリア={num_tones}, "
        f"位相={'あり' if has_phase else 'なし'}, "
        f"計測時間={duration_s:.2f}s, 帯域幅={detected_bw} MHz"
    )
    return df


# ------------------------------------------------------------------ #
# Step 2: 無効行削除                                                   #
# ------------------------------------------------------------------ #

def drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    cleaned = df.dropna(subset=numeric_cols, how="any")
    return cleaned[~cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]


# ------------------------------------------------------------------ #
# Step 3: 不要サブキャリア削除                                          #
# ------------------------------------------------------------------ #

def remove_unnecessary_subcarriers(
    df: pd.DataFrame,
    bandwidth_mhz: int = 80,
) -> pd.DataFrame:
    """DC / ガードバンド / パイロットサブキャリアを削除する。対応する位相列も同時に削除する。"""
    if df.empty:
        return df

    cfg = CHANNEL_CONFIGS.get(bandwidth_mhz, _CFG_80)
    guard_bands: list[tuple[int, int]] = cfg["guard_bands"]
    pilots: list[int] = cfg["pilots"]

    def _drop_with_phase(frame: pd.DataFrame, mag_cols: list[str]) -> pd.DataFrame:
        phase_cols = [f"{c}_phase" for c in mag_cols if f"{c}_phase" in frame.columns]
        return frame.drop(columns=mag_cols + phase_cols)

    if "0" in df.columns:
        df = _drop_with_phase(df, ["0"])

    for start, end in guard_bands:
        cols = [str(i) for i in range(start, end + 1) if str(i) in df.columns]
        if cols:
            df = _drop_with_phase(df, cols)

    pilot_cols = [str(i) for i in pilots if str(i) in df.columns]
    if pilot_cols:
        df = _drop_with_phase(df, pilot_cols)

    remaining = len(_mag_cols(df))
    logger.info(f"サブキャリアフィルタ後 ({bandwidth_mhz} MHz): {remaining} 列")
    return df


# ------------------------------------------------------------------ #
# Step 3.5: 背景差分除去                                                #
# ------------------------------------------------------------------ #

def subtract_background(
    df: pd.DataFrame,
    subcarrier_medians: dict[str, float],
) -> pd.DataFrame:
    """ベースCSIのサブキャリア別メジアンを引き、負値を 0 にクリップする。"""
    result = df.copy()
    for col in _mag_cols(df):
        base_offset = subcarrier_medians.get(col, 0.0)
        result[col] = np.maximum(df[col].values - base_offset, 0.0)
    return result


# ------------------------------------------------------------------ #
# Step 4: 周波数解析（FFT / Wavelet / MUSIC）                          #
# ------------------------------------------------------------------ #

# --- Wavelet / MUSIC 定数 ---
WAVELET_NAME = "cmor1.5-1.0"
WAVELET_FREQ_MIN = 0.01
WAVELET_FREQ_MAX = 2.0
WAVELET_N_FREQS = 100
WAVELET_FFT_METHOD_MIN_LEN = 256

MUSIC_FREQ_MIN = 0.01
MUSIC_FREQ_MAX = 2.0
MUSIC_N_FREQS = 128
MUSIC_EMBEDDING_DIM = 32
MUSIC_MODEL_ORDER = 1


def apply_fft(df: pd.DataFrame) -> pd.DataFrame:
    """各サブキャリアにFFTを適用する。

    リサンプリングは行わず、実測サンプリングレートをそのまま使用する。
    """
    if df.empty:
        return pd.DataFrame()

    data_cols = _mag_cols(df)
    if not data_cols:
        return pd.DataFrame()

    if "timestamp" in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df["timestamp"])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_fs = (len(df) - 1) / duration_s if duration_s > 0 else 1.0 / DOWNSAMPLE_INTERVAL_S
    else:
        actual_fs = 1.0 / DOWNSAMPLE_INTERVAL_S

    actual_interval = 1.0 / actual_fs
    logger.info(f"FFT 実サンプリングレート: {actual_fs:.4f} Hz (サンプル間隔: {actual_interval:.4f} s)")

    all_results: list[pd.DataFrame] = []
    for col in data_cols:
        signal = df[col].values.astype(np.float64)
        if len(signal) < 4:
            continue

        signal = detrend(signal, type="linear")
        signal = signal * np.hanning(len(signal))

        yf = np.fft.rfft(signal)
        xf = np.fft.rfftfreq(len(signal), d=actual_interval)

        positive = xf > 0
        col_df = pd.DataFrame({"frequency": xf[positive], col: np.abs(yf[positive])})
        all_results.append(col_df.set_index("frequency"))

    if not all_results:
        return pd.DataFrame()

    merged = pd.concat(all_results, axis=1).reset_index()
    logger.info(f"FFT 完了: {len(data_cols)} サブキャリア, {len(merged)} 周波数ポイント")
    return drop_invalid_rows(merged)


def apply_wavelet(df: pd.DataFrame) -> pd.DataFrame:
    """各サブキャリアに CWT を適用し、時間平均振幅スペクトルを返す。

    frequency 列と _mean 列（全サブキャリアのコヒーレント平均）を含む DataFrame を返す。
    """
    try:
        import pywt
    except ImportError:
        logger.warning("PyWavelets 未インストールのためウェーブレット変換をスキップ")
        return pd.DataFrame()

    data_cols = _mag_cols(df)
    if not data_cols:
        return pd.DataFrame()

    if "timestamp" in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df["timestamp"])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_fs = (len(df) - 1) / duration_s if duration_s > 0 else 1.0 / DOWNSAMPLE_INTERVAL_S
    else:
        actual_fs = 1.0 / DOWNSAMPLE_INTERVAL_S
    actual_interval = 1.0 / actual_fs

    target_freqs = np.logspace(
        np.log10(WAVELET_FREQ_MIN),
        np.log10(min(WAVELET_FREQ_MAX, actual_fs / 2.0)),
        WAVELET_N_FREQS,
    )
    scales = pywt.frequency2scale(WAVELET_NAME, target_freqs * actual_interval)

    signal_matrix = np.stack(
        [df[col].to_numpy(dtype=np.float64, copy=False) for col in data_cols], axis=1
    )
    signal_matrix = np.nan_to_num(signal_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    signal_matrix = detrend(signal_matrix, axis=0, type="linear")

    signal_len = signal_matrix.shape[0]
    if signal_len < 2:
        return pd.DataFrame()

    method = "fft" if signal_len >= WAVELET_FFT_METHOD_MIN_LEN else "conv"

    mean_signal = signal_matrix.mean(axis=1)
    mean_coeff, frequency_axis = pywt.cwt(
        mean_signal, scales, WAVELET_NAME,
        sampling_period=actual_interval, method=method,
    )
    mean_amplitude = np.mean(np.abs(mean_coeff), axis=1).astype(np.float32)

    amplitude_rows = []
    valid_cols = []
    for col_idx, col in enumerate(data_cols):
        signal = signal_matrix[:, col_idx]
        if np.allclose(signal, 0.0):
            continue
        coeff, _ = pywt.cwt(
            signal, scales, WAVELET_NAME,
            sampling_period=actual_interval, method=method,
        )
        amplitude_rows.append(np.mean(np.abs(coeff), axis=1).astype(np.float32))
        valid_cols.append(col)

    if not amplitude_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(np.stack(amplitude_rows, axis=1), columns=valid_cols)
    result_df.insert(0, "_mean", mean_amplitude)
    result_df.insert(0, "frequency", frequency_axis.astype(np.float32))
    logger.info(f"Wavelet 完了: {len(valid_cols)} サブキャリア, {len(result_df)} 周波数ポイント")
    return drop_invalid_rows(result_df)


def apply_music(df: pd.DataFrame) -> pd.DataFrame:
    """各サブキャリアに MUSIC 法を適用し、擬似スペクトルを返す。

    frequency 列と _mean 列（平均信号のコヒーレント MUSIC）を含む DataFrame を返す。
    """
    data_cols = _mag_cols(df)
    if not data_cols:
        return pd.DataFrame()

    if "timestamp" in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df["timestamp"])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_fs = (len(df) - 1) / duration_s if duration_s > 0 else 1.0 / DOWNSAMPLE_INTERVAL_S
    else:
        actual_fs = 1.0 / DOWNSAMPLE_INTERVAL_S
    actual_interval = 1.0 / actual_fs

    target_freqs = np.linspace(
        MUSIC_FREQ_MIN, min(MUSIC_FREQ_MAX, actual_fs / 2.0),
        MUSIC_N_FREQS, dtype=np.float64,
    )

    signal_matrix = np.stack(
        [df[col].to_numpy(dtype=np.float64, copy=False) for col in data_cols], axis=1
    )
    signal_matrix = np.nan_to_num(signal_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    signal_matrix = detrend(signal_matrix, axis=0, type="linear")

    signal_length = signal_matrix.shape[0]
    embedding_dim = max(4, min(min(signal_length // 2, MUSIC_EMBEDDING_DIM), signal_length - 1))
    model_order = max(1, min(MUSIC_MODEL_ORDER, embedding_dim - 1))
    snapshot_count = signal_length - embedding_dim + 1
    if snapshot_count < 2:
        return pd.DataFrame()

    sample_indices = np.arange(embedding_dim, dtype=np.float64)
    angular = 2.0 * np.pi * target_freqs * actual_interval
    steering = np.exp(-1j * np.outer(sample_indices, angular))

    # 平均信号 MUSIC（BPM 推定用）
    mean_signal = signal_matrix.mean(axis=1)
    mean_signal = mean_signal - mean_signal.mean()
    if not np.allclose(mean_signal, 0.0):
        windows_m = np.lib.stride_tricks.sliding_window_view(mean_signal, embedding_dim)
        hankel_m = windows_m.T
        cov_m = (hankel_m @ hankel_m.T) / snapshot_count
        _, evecs_m = np.linalg.eigh(cov_m)
        noise_m = evecs_m[:, ::-1][:, model_order:]
        proj_m = noise_m.conj().T @ steering
        denom_m = np.maximum(np.sum(np.abs(proj_m) ** 2, axis=0), 1e-12)
        mean_spectrum = (1.0 / denom_m).astype(np.float32)
    else:
        mean_spectrum = np.zeros(len(target_freqs), dtype=np.float32)

    # バッチ MUSIC（全サブキャリア）
    nonzero_mask = ~np.all(np.isclose(signal_matrix, 0.0), axis=0)
    valid_cols = [c for c, ok in zip(data_cols, nonzero_mask) if ok]
    valid_signals = signal_matrix[:, nonzero_mask]

    if valid_signals.shape[1] == 0:
        result_df = pd.DataFrame({
            "frequency": target_freqs.astype(np.float32),
            "_mean": mean_spectrum,
        })
        return drop_invalid_rows(result_df)

    windows = np.lib.stride_tricks.sliding_window_view(valid_signals, embedding_dim, axis=0)
    hankel_batch = np.ascontiguousarray(windows.transpose(1, 2, 0))
    cov_batch = (hankel_batch @ hankel_batch.transpose(0, 2, 1)) / snapshot_count
    _, evecs_batch = np.linalg.eigh(cov_batch)
    noise_batch = evecs_batch[..., ::-1][:, :, model_order:]
    noise_T = np.ascontiguousarray(noise_batch.conj().transpose(0, 2, 1))
    proj_batch = noise_T @ steering
    denom_batch = np.maximum(np.sum(np.abs(proj_batch) ** 2, axis=1), 1e-12)
    spectra_batch = (1.0 / denom_batch).astype(np.float32)

    result_df = pd.DataFrame(spectra_batch.T, columns=valid_cols)
    result_df.insert(0, "_mean", mean_spectrum)
    result_df.insert(0, "frequency", target_freqs.astype(np.float32))
    logger.info(f"MUSIC 完了: {len(valid_cols)} サブキャリア, {len(result_df)} 周波数ポイント")
    return drop_invalid_rows(result_df)


# ------------------------------------------------------------------ #
# Step 5: 周波数ビン平均化                                              #
# ------------------------------------------------------------------ #

def average_by_frequency_bins(fft_df: pd.DataFrame) -> pd.DataFrame:
    if fft_df.empty or "frequency" not in fft_df.columns:
        return pd.DataFrame()

    max_freq = fft_df["frequency"].max()
    num_steps = int(max_freq / FREQUENCY_BIN_STEP)
    bins = [i * FREQUENCY_BIN_STEP for i in range(num_steps + 1)]

    df = fft_df.copy()
    df["freq_interval"] = pd.cut(df["frequency"], bins=bins, right=False, include_lowest=True)

    data_cols = [
        c for c in df.columns
        if c not in {"frequency", "freq_interval"}
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    binned = df.groupby("freq_interval", observed=False)[data_cols].mean().reset_index()
    logger.info(f"周波数ビン平均化完了: {len(binned)} ビン")
    return binned


# ------------------------------------------------------------------ #
# Step 6: ZKP行列抽出                                                  #
# ------------------------------------------------------------------ #

def _interval_midpoint(value) -> float:
    if pd.isna(value):
        return 0.0
    if hasattr(value, "mid"):
        return float(value.mid)
    if isinstance(value, str):
        try:
            left, right = value.strip("[]()").split(",")
            return (float(left.strip()) + float(right.strip())) / 2.0
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def extract_zkp_matrix(binned_df: pd.DataFrame) -> list[list[int]]:
    """ビン平均済みDataFrameからZKP入力行列を生成する。"""
    if binned_df.empty:
        raise ValueError("ビン平均DataFrameが空です")

    df = binned_df.copy()
    df["_freq_mid"] = df["freq_interval"].apply(_interval_midpoint).astype(float)
    mask = (df["_freq_mid"] >= ZKP_FREQ_START) & (df["_freq_mid"] <= ZKP_FREQ_END)
    sub_df = df[mask]

    if sub_df.empty:
        raise ValueError(
            f"周波数帯域 {ZKP_FREQ_START}〜{ZKP_FREQ_END} Hz にデータがありません。"
            f"データ範囲: {df['_freq_mid'].min():.3f}〜{df['_freq_mid'].max():.3f} Hz"
        )

    subcarrier_cols = [
        c for c in sub_df.columns
        if c not in {"freq_interval", "_freq_mid"}
        and not c.startswith("_")
        and pd.api.types.is_numeric_dtype(sub_df[c])
    ]
    if not subcarrier_cols:
        raise ValueError("サブキャリア列が見つかりません")

    raw = sub_df[subcarrier_cols].to_numpy(dtype=np.float64)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    raw = np.maximum(raw, 0.0)

    col_min = raw.min(axis=0)
    col_max = raw.max(axis=0)
    col_range = np.where(col_max - col_min == 0.0, 1.0, col_max - col_min)
    normalized = (raw - col_min) / col_range

    matrix = [[int(v * ZKP_SCALE) for v in row] for row in normalized]

    logger.info(
        f"ZKP 行列抽出完了: {len(matrix)} 周波数ポイント × {len(subcarrier_cols)} サブキャリア"
    )
    return matrix


# ------------------------------------------------------------------ #
# Step 7: ZKP入力リサイズ                                              #
# ------------------------------------------------------------------ #

def resize_matrix(
    matrix: list[list[int]],
    target_rows: int,
    target_cols: int,
) -> list[list[int]]:
    """ZKP回路の期待サイズ（EXPECTED_FREQ_POINTS × EXPECTED_SUBCARRIERS）に合わせる。"""
    resized = []
    for i in range(target_rows):
        if i < len(matrix):
            row = [max(0, int(v)) for v in matrix[i][:target_cols]]
            row.extend([0] * (target_cols - len(row)))
        else:
            row = [0] * target_cols
        resized.append(row)
    return resized


# ------------------------------------------------------------------ #
# Step 8: Witness生成                                                  #
# ------------------------------------------------------------------ #

async def generate_witness(
    input_data: dict,
    zkp_dir: Path,
    temp_dir: Path,
) -> str:
    """snarkjs generate_witness.js でWitnessファイルを生成する。

    Returns:
        生成されたWitnessファイルパス（文字列）
    """
    wasm_file = zkp_dir / "build" / "csi_full_similarity_js" / "csi_full_similarity.wasm"
    generate_witness_js = zkp_dir / "build" / "csi_full_similarity_js" / "generate_witness.js"

    if not wasm_file.exists():
        raise FileNotFoundError(f"WASM ファイルが見つかりません: {wasm_file}")
    if not generate_witness_js.exists():
        raise FileNotFoundError(f"generate_witness.js が見つかりません: {generate_witness_js}")

    run_id = uuid.uuid4()
    input_file = temp_dir / f"csi_input_{run_id}.json"
    witness_file = temp_dir / f"csi_witness_{run_id}.wtns"

    with open(input_file, "w") as f:
        json.dump(input_data, f)

    cmd = ["node", str(generate_witness_js), str(wasm_file), str(input_file), str(witness_file)]

    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--max-old-space-size=4096"

    logger.info("Witness 生成開始...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    input_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        stdout_msg = stdout.decode(errors="replace") if stdout else ""
        stderr_msg = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(
            f"Witness 生成失敗 (returncode={proc.returncode})\n"
            f"stdout: {stdout_msg}\nstderr: {stderr_msg}"
        )

    logger.info(f"Witness 生成完了: {witness_file}")
    return str(witness_file)


# ------------------------------------------------------------------ #
# Step 9: Groth16証明生成                                              #
# ------------------------------------------------------------------ #

async def generate_groth16_proof(
    witness_file: str,
    zkp_dir: Path,
    temp_dir: Path,
) -> tuple[dict, list[str]]:
    """snarkjs groth16 prove でGroth16証明を生成する。

    Returns:
        (proof, publicSignals)
    """
    zkey_file = zkp_dir / "keys" / "csi_full_similarity_final.zkey"
    if not zkey_file.exists():
        raise FileNotFoundError(
            f"zkey ファイルが見つかりません: {zkey_file}\n"
            "cd zkp && npm run setup:full_similarity を実行してください。"
        )

    run_id = uuid.uuid4()
    proof_file = temp_dir / f"csi_proof_{run_id}.json"
    public_file = temp_dir / f"csi_public_{run_id}.json"

    cmd = [
        "snarkjs", "groth16", "prove",
        str(zkey_file),
        witness_file,
        str(proof_file),
        str(public_file),
    ]

    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--max-old-space-size=4096"

    logger.info("Groth16 証明生成開始...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stdout_msg = stdout.decode(errors="replace") if stdout else ""
        stderr_msg = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(
            f"証明生成失敗 (returncode={proc.returncode})\n"
            f"stdout: {stdout_msg}\nstderr: {stderr_msg}"
        )

    with open(proof_file, "r") as f:
        proof = json.load(f)
    with open(public_file, "r") as f:
        public_signals = json.load(f)

    proof_file.unlink(missing_ok=True)
    public_file.unlink(missing_ok=True)

    logger.info("Groth16 証明生成完了")
    return proof, public_signals


# ------------------------------------------------------------------ #
# メインパイプライン                                                     #
# ------------------------------------------------------------------ #

def process_main_csi(
    csi_file: str,
    subcarrier_medians: dict[str, float] | None = None,
    show_plots: bool = True,
    bandwidth_mhz: int | None = None,
) -> dict:
    """メインCSIファイルを処理してZKP候補行列を返す（FFTのみ）。"""
    df = load_csi_to_dataframe(csi_file)

    bw = bandwidth_mhz if bandwidth_mhz is not None else int(df.attrs.get("bandwidth_mhz", 80))
    if bw not in CHANNEL_CONFIGS:
        logger.warning(f"未対応の帯域幅 {bw} MHz → 80 MHz にフォールバック")
        bw = 80
    logger.info(f"使用帯域幅: {bw} MHz")

    if show_plots:
        _plot_step1(df)

    before_frame_count = len(df)
    df = drop_invalid_rows(df)
    if df.empty:
        raise ValueError("有効なデータ行がありません")
    before_sc_cols = _mag_cols(df)
    df = remove_unnecessary_subcarriers(df, bandwidth_mhz=bw)
    if show_plots:
        _plot_step2_3(before_frame_count, len(df), before_sc_cols, df, bandwidth_mhz=bw)

    if subcarrier_medians:
        df_before_bg = df
        df = subtract_background(df, subcarrier_medians)
        logger.info("背景差分除去完了")
        if show_plots:
            _plot_step3_5(df_before_bg, df)

    # Step 4-1: FFT
    fft_df = apply_fft(df)
    if fft_df.empty:
        raise ValueError("FFT結果が空です")
    if show_plots:
        _plot_step4_fft(fft_df)

    fft_binned = average_by_frequency_bins(fft_df)
    if show_plots:
        _plot_step5(fft_binned, "FFT")

    fft_matrix = extract_zkp_matrix(fft_binned)
    if show_plots:
        _plot_step6_matrix(fft_matrix, "FFT")

    bpm_fft = estimate_bpm(fft_df)

    # Step 4-2: Wavelet
    wavelet_df = apply_wavelet(df)
    bpm_wavelet = estimate_bpm(wavelet_df) if not wavelet_df.empty else None
    if show_plots and not wavelet_df.empty:
        wavelet_binned = average_by_frequency_bins(wavelet_df)
        _plot_step5(wavelet_binned, "Wavelet")

    # Step 4-3: MUSIC
    music_df = apply_music(df)
    bpm_music = estimate_bpm(music_df) if not music_df.empty else None
    if show_plots and not music_df.empty:
        music_binned = average_by_frequency_bins(music_df)
        _plot_step5(music_binned, "MUSIC")

    logger.info(
        f"推定呼吸数: FFT={bpm_fft} BPM, "
        f"Wavelet={bpm_wavelet} BPM, "
        f"MUSIC={bpm_music} BPM"
    )

    return {
        "matrix": fft_matrix,
        "bpm_fft": bpm_fft,
        "bpm_wavelet": bpm_wavelet,
        "bpm_music": bpm_music,
        "bandwidth_mhz": bw,
    }


async def run(
    csi_file: str,
    base_file: str,
    zkp_dir: Path,
    output_file: str,
    show_plots: bool = True,
    bandwidth_mhz: int | None = None,
) -> None:
    logger.info(f"=== メインCSI処理開始: {csi_file} ===")

    base_path = Path(base_file)
    if not base_path.exists():
        raise FileNotFoundError(f"ベース行列JSONが見つかりません: {base_path}")

    with open(base_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    reference_matrix: list[list[int]] = base_data["matrix"]
    subcarrier_medians: dict[str, float] = base_data.get("subcarrier_medians", {})

    base_bw: int = int(base_data.get("bandwidth_mhz", 80))
    effective_bw = bandwidth_mhz if bandwidth_mhz is not None else base_bw

    logger.info(
        f"ベース行列読み込み: {base_data['num_freq_points']} × {base_data['num_subcarriers']}, "
        f"メジアン: {len(subcarrier_medians)} サブキャリア, 帯域幅: {effective_bw} MHz"
    )

    result_matrices = process_main_csi(
        csi_file,
        subcarrier_medians or None,
        show_plots=show_plots,
        bandwidth_mhz=effective_bw,
    )
    candidate_matrix = result_matrices["matrix"]
    logger.info(
        f"候補行列: {len(candidate_matrix)} × {len(candidate_matrix[0]) if candidate_matrix else 0}"
    )

    reference_matrix = resize_matrix(reference_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)
    candidate_matrix = resize_matrix(candidate_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)
    logger.info(f"リサイズ後: {EXPECTED_FREQ_POINTS} × {EXPECTED_SUBCARRIERS}")

    input_data = {
        "referenceMatrix": reference_matrix,
        "candidateMatrix": candidate_matrix,
    }

    temp_dir = Path(tempfile.gettempdir())
    witness_file = await generate_witness(input_data, zkp_dir, temp_dir)
    proof, public_signals = await generate_groth16_proof(witness_file, zkp_dir, temp_dir)
    Path(witness_file).unlink(missing_ok=True)

    is_normal = bool(int(public_signals[0])) if public_signals else False

    if show_plots:
        _plot_comparison(reference_matrix, candidate_matrix, is_normal)

    result = {
        "proof": proof,
        "publicSignals": public_signals,
        "isNormal": is_normal,
        "bpm_fft": result_matrices["bpm_fft"],
        "bpm_wavelet": result_matrices["bpm_wavelet"],
        "bpm_music": result_matrices["bpm_music"],
        "num_freq_points": EXPECTED_FREQ_POINTS,
        "num_subcarriers": EXPECTED_SUBCARRIERS,
        "bandwidth_mhz": result_matrices["bandwidth_mhz"],
        "source_file": str(Path(csi_file).resolve()),
        "base_file": str(base_path.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path = Path(output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        f"=== 完了 ===\n"
        f"  isNormal: {is_normal}\n"
        f"  publicSignals: {public_signals}\n"
        f"  BPM (FFT): {result_matrices['bpm_fft']}\n"
        f"  BPM (Wavelet): {result_matrices['bpm_wavelet']}\n"
        f"  BPM (MUSIC): {result_matrices['bpm_music']}\n"
        f"  出力: {output_path.resolve()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PicoScenes .csi → ZKP証明生成スクリプト"
    )
    parser.add_argument("csi_file", help=".csi ファイルパス")
    parser.add_argument(
        "--base", "-b",
        required=True,
        help="ベース行列JSONファイルパス（csi_base_to_zkp.py の出力）",
    )
    parser.add_argument(
        "--zkp-dir",
        default=None,
        help="zkp ディレクトリパス (デフォルト: スクリプトの ../zkp)",
    )
    parser.add_argument(
        "--output", "-o",
        default="zkp_result.json",
        help="出力JSONファイルパス (デフォルト: zkp_result.json)",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="グラフ表示を無効にする",
    )
    parser.add_argument(
        "--bandwidth",
        type=str,
        default="auto",
        choices=["auto", "80", "160"],
        help="チャンネル帯域幅 MHz (デフォルト: auto = ベースJSONの記録値または自動検出)",
    )
    args = parser.parse_args()

    csi_path = Path(args.csi_file)
    if not csi_path.exists():
        logger.error(f"ファイルが見つかりません: {csi_path}")
        sys.exit(1)

    if args.zkp_dir:
        zkp_dir = Path(args.zkp_dir)
    else:
        script_dir = Path(__file__).resolve().parent
        zkp_dir = script_dir.parent / "zkp"

    if not zkp_dir.exists():
        logger.error(f"zkp ディレクトリが見つかりません: {zkp_dir}")
        sys.exit(1)

    bandwidth_arg: int | None = None if args.bandwidth == "auto" else int(args.bandwidth)

    try:
        asyncio.run(run(
            str(csi_path),
            args.base,
            zkp_dir,
            args.output,
            show_plots=not args.no_plot,
            bandwidth_mhz=bandwidth_arg,
        ))
    except Exception as exc:
        logger.error(f"処理失敗: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
