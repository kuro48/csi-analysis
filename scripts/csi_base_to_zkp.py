"""
csi_base_to_zkp.py

PicoScenes .csi ファイルを受け取り、ZKP回路（csi_full_similarity.circom）
への入力として使う基準行列（reference matrix）を生成してJSONで保存する。

使い方:
    python csi_base_to_zkp.py <csi_file> [--output base_matrix.json] [--no-plot]

出力 JSON:
    {
        "matrix": [[int, ...], ...],         // FFT 基準行列 [freq_points][subcarriers]
        "subcarrier_medians": {str: float},  // サブキャリア別メジアン振幅（背景差分除去用）
        "num_freq_points": int,
        "num_subcarriers": int,
        "sampling_rate_hz": float,           // 実測サンプリングレート [Hz]
        "source_file": str,
        "created_at": str                    // ISO8601
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
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
# パラメータ（csi_full_similarity.circom の main 宣言および          #
# PCAPAnalyzer クラス定数と同期）                                     #
# ------------------------------------------------------------------ #

DOWNSAMPLE_INTERVAL_S: float = 0.01   # フォールバック用サンプリング間隔（タイムスタンプ取得不可時）
FREQUENCY_BIN_STEP: float = 0.01      # 周波数ビン幅 Hz

ZKP_FREQ_START: float = 0.0           # 抽出開始周波数 Hz
ZKP_FREQ_END: float = 0.60            # 抽出終了周波数 Hz
ZKP_SCALE: int = 10000                # 整数化スケール

# 80MHz (VHT80 / HE80): subcarrier indices -128..+127
_CFG_80: dict = {
    "guard_bands": [(-128, -122), (122, 127)],
    "pilots": [-103, -75, -39, -11, 11, 39, 75, 103],
}

# 160MHz (VHT160 / HE160): subcarrier indices -256..+255
# IEEE 802.11ac/ax 準拠: 外側ガード左7本・右6本、パイロット16本
_CFG_160: dict = {
    "guard_bands": [(-256, -250), (250, 255)],
    "pilots": [
        -231, -203, -167, -139, -117, -89, -53, -25,
          25,   53,   89,  117,  139, 167, 203, 231,
    ],
}

CHANNEL_CONFIGS: dict[int, dict] = {80: _CFG_80, 160: _CFG_160}

# 後方互換エイリアス（グラフ表示ユーティリティで使用）
GUARD_BANDS: list[tuple[int, int]] = _CFG_80["guard_bands"]
PILOTS: list[int] = _CFG_80["pilots"]

# ------------------------------------------------------------------ #
# グラフ出力ユーティリティ                                              #
# ------------------------------------------------------------------ #

def _show_plot(fig: plt.Figure, title: str) -> None:
    fig.canvas.manager.set_window_title(title) if hasattr(fig.canvas, "manager") and fig.canvas.manager else None
    plt.show()


def _mag_cols(df: pd.DataFrame) -> list[str]:
    """振幅列（整数インデックス名の列）だけを返す。位相列を除外するために使う。"""
    return [c for c in df.columns if c.lstrip("-").isdigit()]


def _plot_step1(df: pd.DataFrame) -> None:
    """Step 1: 生CSI振幅・位相の時系列（全サブキャリア）"""
    mag_cols = _mag_cols(df)
    phase_cols = [c for c in df.columns if c.endswith("_phase")]
    has_phase = len(phase_cols) > 0

    n_rows = 2 if has_phase else 1
    fig, axes = plt.subplots(n_rows, 1, figsize=(12, 5 * n_rows))
    if n_rows == 1:
        axes = [axes]

    ax = axes[0]
    for col in mag_cols:
        ax.plot(df[col].values, alpha=0.4, linewidth=0.5)
    ax.set_xlabel("フレーム番号")
    ax.set_ylabel("振幅")
    ax.set_title(
        f"Step 1: 生CSI振幅（全サブキャリア）\n"
        f"{len(df)} フレーム, {len(mag_cols)} サブキャリア"
    )
    ax.grid(True, alpha=0.3)

    if has_phase:
        ax2 = axes[1]
        for col in phase_cols:
            ax2.plot(df[col].values, alpha=0.4, linewidth=0.5)
        ax2.set_xlabel("フレーム番号")
        ax2.set_ylabel("位相 (rad)")
        ax2.set_title(
            f"Step 1: 生CSI位相（全サブキャリア）\n"
            f"{len(df)} フレーム, {len(phase_cols)} サブキャリア"
        )
        ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, "Step 1: 生CSI振幅・位相")


def _plot_step2_3(
    before_frame_count: int,
    after_frame_count: int,
    before_sc_cols: list[str],
    df: pd.DataFrame,
    bandwidth_mhz: int = 80,
) -> None:
    """Step 2–3: 無効行削除 + 不要サブキャリア除去の結果を1画面で表示"""
    after_sc_cols = _mag_cols(df)
    dropped_frames = before_frame_count - after_frame_count
    frame_drop_rate = dropped_frames / before_frame_count * 100 if before_frame_count > 0 else 0.0

    cfg = CHANNEL_CONFIGS.get(bandwidth_mhz, _CFG_80)
    removed_sc = set(before_sc_cols) - set(after_sc_cols)
    removed_dc = 1 if "0" in removed_sc else 0
    removed_guard = sum(1 for s, e in cfg["guard_bands"] for i in range(s, e + 1) if str(i) in removed_sc)
    removed_pilot = sum(1 for p in cfg["pilots"] if str(p) in removed_sc)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # フレーム数の前後
    ax = axes[0]
    bars = ax.bar(["削除前", "削除後"], [before_frame_count, after_frame_count],
                  color=["#e74c3c", "#2ecc71"], width=0.5)
    ax.set_ylabel("フレーム数")
    ax.set_title(f"Step 2: 無効行削除\n{dropped_frames} 行削除 / 削除率 {frame_drop_rate:.1f}%")
    for bar, val in zip(bars, [before_frame_count, after_frame_count]):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.3, str(val), ha="center", fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)

    # サブキャリア数の前後
    ax2 = axes[1]
    bars2 = ax2.bar(["除去前", "除去後"], [len(before_sc_cols), len(after_sc_cols)],
                    color=["#e74c3c", "#2ecc71"], width=0.5)
    detail = f"DC:{removed_dc}  ガード:{removed_guard}  パイロット:{removed_pilot}"
    ax2.set_ylabel("サブキャリア数")
    ax2.set_title(f"Step 3: 不要サブキャリア除去\n{len(removed_sc)} 列除去 — {detail}")
    for bar, val in zip(bars2, [len(before_sc_cols), len(after_sc_cols)]):
        ax2.text(bar.get_x() + bar.get_width() / 2, val + 0.3, str(val), ha="center", fontweight="bold")
    ax2.grid(True, axis="y", alpha=0.3)

    # クリーニング後の振幅時系列
    ax3 = axes[2]
    for col in after_sc_cols:
        ax3.plot(df[col].values, alpha=0.4, linewidth=0.5)
    ax3.set_xlabel("フレーム番号")
    ax3.set_ylabel("振幅")
    ax3.set_title(f"Step 2–3 後: クリーニング済み振幅\n{after_frame_count} フレーム, {len(after_sc_cols)} サブキャリア")
    ax3.grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, "Step 2–3: クリーニング")


def _plot_step4_fft(fft_df: pd.DataFrame) -> None:
    """Step 4-1: FFTスペクトル（全サブキャリア）"""
    data_cols = [c for c in fft_df.columns if c != "frequency"]
    freqs = fft_df["frequency"].values

    fig, ax = plt.subplots(1, 1, figsize=(12, 5))

    for col in data_cols:
        ax.plot(freqs, fft_df[col].values, alpha=0.4, linewidth=0.5)
    ax.axvspan(
        ZKP_FREQ_START, ZKP_FREQ_END,
        alpha=0.15, color="red",
        label=f"ZKP帯域 ({ZKP_FREQ_START}–{ZKP_FREQ_END} Hz)",
    )
    ax.set_xlabel("周波数 (Hz)")
    ax.set_ylabel("振幅")
    ax.set_title(
        f"Step 4-1: FFTスペクトル（全サブキャリア）\n"
        f"{len(data_cols)} サブキャリア, {len(freqs)} 周波数点"
    )
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, "Step 4-1: FFT")


def _plot_step5(binned_df: pd.DataFrame, method_name: str = "") -> None:
    """Step 5: 周波数ビン平均化（全サブキャリア）"""
    data_cols = [
        c for c in binned_df.columns
        if c not in {"freq_interval"}
        and not c.startswith("_")
        and pd.api.types.is_numeric_dtype(binned_df[c])
    ]
    midpoints = binned_df["freq_interval"].apply(
        lambda v: float(v.mid) if hasattr(v, "mid") else 0.0
    ).values

    fig, ax = plt.subplots(1, 1, figsize=(12, 5))

    for col in data_cols:
        ax.plot(midpoints, binned_df[col].values, alpha=0.4, linewidth=0.5)
    ax.axvspan(
        ZKP_FREQ_START, ZKP_FREQ_END,
        alpha=0.15, color="red",
        label=f"ZKP帯域 ({ZKP_FREQ_START}–{ZKP_FREQ_END} Hz)",
    )
    ax.set_xlabel("周波数 (Hz)")
    ax.set_ylabel("振幅")
    label = f" [{method_name}]" if method_name else ""
    ax.set_title(
        f"Step 5{label}: 周波数ビン平均化スペクトル（全サブキャリア）\n"
        f"{len(data_cols)} サブキャリア, {len(midpoints)} ビン"
    )
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    _show_plot(fig, f"Step 5{label}")


def _plot_step6(matrix: list[list[int]], method_name: str = "") -> None:
    """Step 6: ZKP基準行列（全サブキャリア × 周波数ポイント + 値分布）"""
    data = np.array(matrix, dtype=np.float32)
    n_freq, n_sc = data.shape
    freq_indices = np.arange(n_freq)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    for sc_idx in range(n_sc):
        ax.plot(freq_indices, data[:, sc_idx], alpha=0.4, linewidth=0.5)
    ax.set_xlabel("周波数ポイントインデックス")
    ax.set_ylabel(f"スケール済み振幅 (0–{ZKP_SCALE})")
    label = f" [{method_name}]" if method_name else ""
    ax.set_title(
        f"Step 6{label}: ZKP基準行列（全サブキャリア）\n"
        f"{n_freq} 周波数ポイント × {n_sc} サブキャリア, スケール={ZKP_SCALE}"
    )
    ax.grid(True, alpha=0.3)

    ax2 = axes[1]
    ax2.hist(data.flatten(), bins=60, color="#9b59b6", alpha=0.8, edgecolor="white")
    ax2.set_xlabel(f"値 (0 – {ZKP_SCALE})")
    ax2.set_ylabel("頻度")
    ax2.set_title(f"Step 6{label}: ZKP行列の値分布")
    ax2.grid(True, alpha=0.3)
    stats_text = (
        f"min = {int(data.min())}\n"
        f"max = {int(data.max())}\n"
        f"mean = {data.mean():.1f}\n"
        f"non-zero = {int(np.count_nonzero(data))}"
    )
    ax2.text(
        0.97, 0.97, stats_text,
        transform=ax2.transAxes,
        ha="right", va="top",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.6),
    )

    fig.tight_layout()
    _show_plot(fig, f"Step 6{label}: ZKP基準行列")


# ------------------------------------------------------------------ #
# Step 1: PicoScenes .csi → DataFrame                                #
# ------------------------------------------------------------------ #

def load_csi_to_dataframe(file_path: str) -> pd.DataFrame:
    """PicoScenes Python Toolbox で .csi を DataFrame に変換する。

    Returns:
        columns: ["timestamp", "<subcarrier_index>", ...]
        timestamp は datetime64[ns]
        サブキャリア列は振幅（float32）
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
    sampling_rate_hz = (valid_count - 1) / duration_s if duration_s > 0 else 0.0

    # サブキャリアインデックスの最大絶対値から帯域幅を推定
    max_abs_sc = int(np.max(np.abs(subcarrier_indices))) if subcarrier_indices.size > 0 else 0
    detected_bw = 160 if max_abs_sc > 200 else 80
    df.attrs["bandwidth_mhz"] = detected_bw

    logger.info(
        f"DataFrame 作成完了: フレーム={valid_count}, サブキャリア={num_tones}, "
        f"位相={'あり' if has_phase else 'なし'}, "
        f"計測時間={duration_s:.2f}s, サンプリングレート={sampling_rate_hz:.2f} Hz, "
        f"帯域幅={detected_bw} MHz"
    )
    return df


# ------------------------------------------------------------------ #
# ユーティリティ: サブキャリア別メジアン計算                              #
# ------------------------------------------------------------------ #

def compute_subcarrier_medians(df: pd.DataFrame) -> dict[str, float]:
    """サブキャリア別のメジアン振幅を返す（背景差分除去用）。

    スパイクや一時的外乱に対して平均より堅牢。
    """
    return {col: float(np.median(df[col].values)) for col in _mag_cols(df)}


# ------------------------------------------------------------------ #
# Step 2: 無効行削除                                                   #
# ------------------------------------------------------------------ #

def drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """NaN / Inf を含む行を削除する。"""
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
# Step 4: FFT適用                                                      #
# ------------------------------------------------------------------ #

def apply_fft(df: pd.DataFrame) -> pd.DataFrame:
    """各サブキャリアにFFTを適用する。

    手順:
        1. 実タイムスタンプから実サンプリングレートを計算
        2. 線形デトレンド（DC + 線形トレンド除去）
        3. Hann窓（スペクトル漏れ抑制）
        4. rfft → 正の周波数成分の絶対値
        ※ リサンプリングは行わず、実測サンプリングレートをそのまま使用する
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


# ------------------------------------------------------------------ #
# Step 5: 周波数ビン平均化                                              #
# ------------------------------------------------------------------ #

def average_by_frequency_bins(fft_df: pd.DataFrame) -> pd.DataFrame:
    """周波数ビンごとに振幅を平均化する。"""
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
    """pd.Interval または文字列から中点を返す。"""
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
    """ビン平均済みDataFrameからZKP入力行列を生成する。

    手順:
        1. ZKP_FREQ_START 〜 ZKP_FREQ_END の周波数帯域を抽出
        2. 各値を nan→0, 負値→0 でクリッピング
        3. サブキャリア単位で min-max 正規化 → [0, 1]
        4. ZKP_SCALE 倍して int に変換

    Returns:
        List[List[int]]: shape [freq_points][subcarriers]
    """
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
# メインパイプライン                                                     #
# ------------------------------------------------------------------ #

def _run_step5_6(
    freq_df: pd.DataFrame,
    method_name: str,
    show_plots: bool,
) -> list[list[int]]:
    """Step 5 + 6 を実行して ZKP 行列を返す。空の場合は [] を返す。"""
    if freq_df.empty:
        return []
    binned = average_by_frequency_bins(freq_df)
    if show_plots:
        _plot_step5(binned, method_name)
    try:
        matrix = extract_zkp_matrix(binned)
    except ValueError as e:
        logger.warning(f"[{method_name}] ZKP 行列抽出スキップ: {e}")
        return []
    if show_plots:
        _plot_step6(matrix, method_name)
    return matrix


def process_base_csi(
    csi_file: str,
    show_plots: bool = True,
    bandwidth_mhz: int | None = None,
) -> dict:
    """ベースCSIファイルを処理してZKP基準行列を返す。

    Args:
        bandwidth_mhz: チャンネル帯域幅 (80 または 160)。None の場合は自動検出。
    """
    df = load_csi_to_dataframe(csi_file)
    ts = pd.to_datetime(df["timestamp"])
    duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
    sampling_rate_hz = (len(df) - 1) / duration_s if duration_s > 0 else 0.0

    # 帯域幅: 引数優先、未指定なら自動検出値を使用
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

    subcarrier_medians = compute_subcarrier_medians(df)
    logger.info(f"サブキャリア別メジアン計算完了: {len(subcarrier_medians)} サブキャリア")

    # Step 4-1: FFT
    fft_df = apply_fft(df)
    if fft_df.empty:
        raise ValueError("FFT 結果が空です")
    if show_plots:
        _plot_step4_fft(fft_df)
    fft_matrix = _run_step5_6(fft_df, "FFT", show_plots)

    return {
        "matrix": fft_matrix,
        "subcarrier_medians": subcarrier_medians,
        "num_freq_points": len(fft_matrix),
        "num_subcarriers": len(fft_matrix[0]) if fft_matrix else 0,
        "sampling_rate_hz": round(sampling_rate_hz, 4),
        "bandwidth_mhz": bw,
        "source_file": str(Path(csi_file).resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PicoScenes .csi → ZKP基準行列 JSON 変換スクリプト"
    )
    parser.add_argument("csi_file", help=".csi ファイルパス")
    parser.add_argument(
        "--output", "-o",
        default="base_matrix.json",
        help="出力JSONファイルパス (デフォルト: base_matrix.json)",
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
        help="チャンネル帯域幅 MHz (デフォルト: auto = PicoScenesメタから自動検出)",
    )
    args = parser.parse_args()

    csi_path = Path(args.csi_file)
    if not csi_path.exists():
        logger.error(f"ファイルが見つかりません: {csi_path}")
        sys.exit(1)

    bandwidth_arg: int | None = None if args.bandwidth == "auto" else int(args.bandwidth)

    logger.info(f"=== ベースCSI処理開始: {csi_path} ===")

    try:
        result = process_base_csi(
            str(csi_path),
            show_plots=not args.no_plot,
            bandwidth_mhz=bandwidth_arg,
        )
    except Exception as exc:
        logger.error(f"処理失敗: {exc}", exc_info=True)
        sys.exit(1)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        f"=== 完了 ===\n"
        f"  行列サイズ: {result['num_freq_points']} × {result['num_subcarriers']}\n"
        f"  出力JSON: {output_path.resolve()}"
    )


if __name__ == "__main__":
    main()
