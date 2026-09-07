"""
PCAPAnalyzer の周波数解析関連処理。
"""

from typing import Optional

import numpy as np
import pandas as pd

from app.services.pcap_analyzer_common import _numeric_data_columns, _subcarrier_data_columns


def apply_bandpass_filter(
    self,
    df: pd.DataFrame,
    sampling_interval: float,
    time_col: str = "timestamp",
    low_freq: Optional[float] = None,
    high_freq: Optional[float] = None,
) -> pd.DataFrame:
    """呼吸帯域（デフォルト: BREATHING_MIN_FREQ〜BREATHING_MAX_FREQ）のバンドパスフィルタを各サブキャリアに適用する。

    FFT/Wavelet/MUSIC 変換前に呼吸帯域外の成分を除去することで、
    各変換の S/N 比を向上させる。ゼロ位相フィルタリング (filtfilt) を使用。
    """
    from scipy.signal import butter, filtfilt

    if df is None or df.empty:
        return df

    data_cols = _subcarrier_data_columns(df)
    if not data_cols:
        return df

    low = low_freq if low_freq is not None else self.BREATHING_MIN_FREQ
    high = high_freq if high_freq is not None else self.BREATHING_MAX_FREQ

    if time_col in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df[time_col])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_fs = (len(df) - 1) / duration_s if duration_s > 0 else 1.0 / sampling_interval
    else:
        actual_fs = 1.0 / sampling_interval

    nyquist = actual_fs / 2.0
    high = min(high, nyquist * 0.95)
    if low <= 0.0 or low >= high:
        self.logger.warning(
            "バンドパスフィルタの周波数設定が不正 (low=%.3f Hz, high=%.3f Hz)。スキップ",
            low, high,
        )
        return df

    order = self.BANDPASS_FILTER_ORDER
    b, a = butter(order, [low / nyquist, high / nyquist], btype="band")

    # filtfilt はパディング長 = 3 * (filter_order - 1) のサンプルを必要とする
    min_samples = 3 * max(len(a), len(b))
    if len(df) <= min_samples:
        self.logger.warning(
            "サンプル数不足 (%d <= %d) のためバンドパスフィルタをスキップ", len(df), min_samples,
        )
        return df

    df_filtered = df.copy()
    for col in data_cols:
        signal = np.nan_to_num(df[col].values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        try:
            df_filtered[col] = filtfilt(b, a, signal)
        except ValueError as exc:
            self.logger.debug("サブキャリア %s: filtfilt 失敗 (%s)。元の値を保持", col, exc)

    self.logger.info(
        "バンドパスフィルタ適用完了: %.3f–%.3f Hz, %d サブキャリア (order=%d, fs=%.2f Hz)",
        low, high, len(data_cols), order, actual_fs,
    )
    return df_filtered


def apply_fourier_transform(
    self,
    df: pd.DataFrame,
    sampling_interval: float,
    time_col: str = "timestamp",
) -> pd.DataFrame:
    """各サブキャリアに FFT を適用する。

    実際のタイムスタンプから実サンプリングレートを計算し、
    デトレンド・Hann窓を適用してから FFT する。
    リサンプリングは行わず、実測サンプリングレートをそのまま使用する。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    data_cols = _subcarrier_data_columns(df)
    if not data_cols:
        self.logger.warning("FFT適用可能な列が見つかりません")
        return pd.DataFrame()

    # 実サンプリングレートをタイムスタンプから計算
    if time_col in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df[time_col])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        if duration_s > 0:
            actual_fs = (len(df) - 1) / duration_s
        else:
            actual_fs = 1.0 / sampling_interval
    else:
        actual_fs = 1.0 / sampling_interval

    actual_interval = 1.0 / actual_fs
    self.logger.info(f"FFT 実サンプリングレート: {actual_fs:.4f} Hz (サンプル間隔: {actual_interval:.4f} s)")

    from scipy.signal import detrend

    all_fft_results = []
    for col in data_cols:
        signal = df[col].values.astype(np.float64)
        if len(signal) < 4:
            continue

        signal = detrend(signal, type="linear")
        signal = signal * np.hanning(len(signal))

        yf = np.fft.rfft(signal)
        xf = np.fft.rfftfreq(len(signal), d=actual_interval)

        positive_mask = xf > 0
        fft_df = pd.DataFrame({
            "frequency": xf[positive_mask],
            col: np.abs(yf[positive_mask]),
        })
        all_fft_results.append(fft_df.set_index("frequency"))

    if not all_fft_results:
        self.logger.warning("FFT結果が空です")
        return pd.DataFrame()

    merged_fft_df = pd.concat(all_fft_results, axis=1).reset_index()
    self.logger.info(
        f"FFT完了: {len(data_cols)}サブキャリア, "
        f"{len(merged_fft_df)}周波数ポイント"
    )
    return self.drop_invalid_rows(merged_fft_df)


def estimate_breathing_rate(
    self,
    freq_df: pd.DataFrame,
    freq_col: str = "frequency",
) -> Optional[float]:
    """周波数スペクトルから呼吸レートを推定する。"""
    if freq_df is None or freq_df.empty or freq_col not in freq_df.columns:
        return None

    breathing_df = freq_df[
        (freq_df[freq_col] >= self.BREATHING_MIN_FREQ)
        & (freq_df[freq_col] <= self.BREATHING_MAX_FREQ)
    ]
    if breathing_df.empty:
        return None

    data_cols = _numeric_data_columns(breathing_df, exclude=[freq_col])
    if not data_cols:
        return None

    # 全サブキャリアのスペクトルを平均（フロントエンド magnitude_avg と同じ定義）。
    # コヒーレント積算（時系列平均→変換）はサブキャリア間の位相オフセットで打ち消し
    # 合うため、位相パイプラインで偽ピークを生む。インコヒーレント積算（変換→平均）に
    # 統一することで、グラフのピーク位置と推定 BPM が一致する。
    mean_amplitude = breathing_df[data_cols].mean(axis=1)
    if mean_amplitude.empty or mean_amplitude.isna().all():
        return None

    # ガウシアン平滑化してからピーク検出（雑音耐性向上）
    values = mean_amplitude.values.astype(np.float64)
    if len(values) >= 9:
        from scipy.ndimage import gaussian_filter1d
        values = gaussian_filter1d(values, sigma=2)

    # バンドパスフィルタ端のロールオフを誤検出しないよう端を除外して探索
    freqs = breathing_df[freq_col].values.astype(np.float64)
    band_width = self.BREATHING_MAX_FREQ - self.BREATHING_MIN_FREQ
    edge_margin = band_width * self.BREATHING_EDGE_MARGIN_RATIO
    inner_mask = (freqs >= self.BREATHING_MIN_FREQ + edge_margin) & (
        freqs <= self.BREATHING_MAX_FREQ - edge_margin
    )
    search_values = values.copy()
    search_values[~inner_mask] = 0.0

    # find_peaks + prominence でロールオフの傾斜ではなく真の山を選ぶ
    from scipy.signal import find_peaks
    prominence_threshold = np.max(search_values) * self.BREATHING_PEAK_PROMINENCE_RATIO
    peaks, props = find_peaks(search_values, prominence=prominence_threshold)

    if peaks.size > 0:
        # 最大 prominence のピークを採用
        peak_idx_pos = int(peaks[np.argmax(props["prominences"])])
    else:
        # 真の山が見つからない場合は内側マージン内の argmax にフォールバック
        if inner_mask.any():
            inner_indices = np.where(inner_mask)[0]
            peak_idx_pos = int(inner_indices[np.argmax(values[inner_mask])])
        else:
            peak_idx_pos = int(np.argmax(values))

    peak_freq_hz = float(breathing_df[freq_col].iloc[peak_idx_pos])
    return peak_freq_hz * 60.0
