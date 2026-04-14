"""
PCAPAnalyzer の共通ユーティリティ。
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _numeric_data_columns(
    df: pd.DataFrame,
    time_col: Optional[str] = None,
    exclude: Optional[List[str]] = None,
) -> List[str]:
    excluded = set(exclude or [])
    if time_col is not None:
        excluded.add(time_col)

    return [
        col for col in df.columns
        if col not in excluded and pd.api.types.is_numeric_dtype(df[col])
    ]


def _empty_extracted_vectors() -> Dict[str, Any]:
    return {
        "csi_matrix": [[0]],
        "frequencies": [0],
        "num_freq_points": 0,
        "num_subcarriers": 0,
    }


def _build_empty_analysis_result(self) -> Dict[str, Any]:
    return {
        "fft": pd.DataFrame(),
        "wavelet": pd.DataFrame(),
        "music": pd.DataFrame(),
        "breathing_rate_fft_bpm": None,
        "breathing_rate_wavelet_bpm": None,
        "breathing_rate_music_bpm": None,
        "breathing_rate_comparison": self.compare_breathing_rate_methods(
            {"fft": None, "wavelet": None, "music": None}
        ),
    }


def _interval_midpoint(value: Any) -> float:
    if pd.isna(value):
        return 0.0

    if hasattr(value, "mid"):
        return float(value.mid)

    if isinstance(value, str):
        try:
            left_str, right_str = value.strip("[]()").split(",")
            return (float(left_str.strip()) + float(right_str.strip())) / 2.0
        except (TypeError, ValueError):
            return 0.0

    return 0.0


def contains_nan_or_inf(self, array: np.ndarray) -> bool:
    """配列にNaNまたはInfが含まれているかチェックする。"""
    arr = np.asarray(array)
    return np.isnan(arr).any() or np.isinf(arr).any()


def normalize_signal(self, signal: np.ndarray) -> np.ndarray:
    """信号を平均0・標準偏差1に正規化する。"""
    if len(signal) == 0:
        return signal

    signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)

    mean = np.mean(signal)
    std = np.std(signal)

    if std == 0:
        return signal - mean

    return (signal - mean) / std


def drop_invalid_rows(self, df: pd.DataFrame) -> pd.DataFrame:
    """NaN または Inf を含む数値行を削除する。"""
    if df is None or df.empty:
        return pd.DataFrame()

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) == 0:
        return df

    cleaned = df.dropna(subset=numeric_cols, how="any")
    return cleaned[~cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]


def make_bins(self, max_val: float, step: float) -> List[float]:
    """周波数ビン境界を作成する。"""
    if step <= 0:
        raise ValueError("ステップは正の値である必要があります")

    num_steps = int(max_val / step)
    return [i * step for i in range(num_steps + 1)]


def remove_unnecessary_subcarriers(
    self,
    df: pd.DataFrame,
    channel_width: str = "80MHz",
) -> pd.DataFrame:
    """ガードバンド・パイロット・DC サブキャリアを削除する。"""
    if df is None or df.empty:
        return df

    if channel_width not in self.CHANNEL_CONFIGS:
        self.logger.warning(f"未サポートのチャネル幅: {channel_width}")
        return df

    subcarrier_cols = [col for col in df.columns if col.lstrip("-").isdigit()]
    if not subcarrier_cols:
        self.logger.warning("サブキャリア列が見つかりません")
        return df

    original_count = len(subcarrier_cols)

    if "0" in df.columns:
        df = df.drop(columns=["0"])
        self.logger.debug("DC成分（サブキャリア0）を削除")

    config = self.CHANNEL_CONFIGS[channel_width]

    for start, end in config["guard_bands"]:
        guard_cols = [str(i) for i in range(start, end + 1) if str(i) in df.columns]
        if guard_cols:
            df = df.drop(columns=guard_cols)
            self.logger.debug(f"ガードバンド削除: {start}～{end} ({len(guard_cols)}列)")

    pilot_cols = [str(i) for i in config["pilots"] if str(i) in df.columns]
    if pilot_cols:
        df = df.drop(columns=pilot_cols)
        self.logger.debug(f"パイロット削除: {len(pilot_cols)}列")

    remaining_count = len([col for col in df.columns if col.lstrip("-").isdigit()])
    self.logger.info(
        f"不要サブキャリア削除: {original_count}列 → {remaining_count}列 "
        f"({original_count - remaining_count}列削除)"
    )

    return df


def average_magnitude_by_frequency_bins(
    self,
    df: pd.DataFrame,
    bins: List[float],
    freq_col: str = "frequency",
) -> pd.DataFrame:
    """周波数ビンごとに振幅を平均化する。"""
    if df is None or df.empty or freq_col not in df.columns:
        return pd.DataFrame()

    grouped_source = df.copy()
    grouped_source["freq_interval"] = pd.cut(
        grouped_source[freq_col],
        bins=bins,
        right=False,
        include_lowest=True,
    )

    data_cols = _numeric_data_columns(grouped_source, exclude=[freq_col, "freq_interval"])
    if not data_cols:
        self.logger.warning("平均化可能な列が見つかりません")
        return pd.DataFrame()

    try:
        grouped_df = grouped_source.groupby("freq_interval", observed=False).mean(numeric_only=True).reset_index()
    except TypeError:
        grouped_df = grouped_source.groupby("freq_interval", observed=False)[data_cols].mean().reset_index()

    if "frequency" in grouped_df.columns:
        grouped_df = grouped_df.drop(columns=["frequency"], errors="ignore")

    self.logger.info(f"周波数ビン平均化完了: {len(grouped_df)}ビン")
    return grouped_df
