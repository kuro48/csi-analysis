"""
PCAPAnalyzer の周波数解析関連処理。
"""

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.services.pcap_analyzer_common import _numeric_data_columns, _subcarrier_data_columns

try:
    import pywt

    PYWAVELETS_AVAILABLE = True
except ImportError:
    pywt = None
    PYWAVELETS_AVAILABLE = False


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


def apply_wavelet_transform(
    self,
    df: pd.DataFrame,
    sampling_interval: float,
    time_col: str = "timestamp",
    n_freqs: Optional[int] = None,
) -> pd.DataFrame:
    """各サブキャリアに CWT を適用し、時間平均振幅スペクトルを返す。"""
    if not PYWAVELETS_AVAILABLE:
        self.logger.warning("PyWavelets未インストールのためウェーブレット変換をスキップ")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    data_cols = _subcarrier_data_columns(df)
    if not data_cols:
        self.logger.warning("ウェーブレット変換適用可能な列が見つかりません")
        return pd.DataFrame()

    # --- 実サンプリングレートをタイムスタンプから計算 ---
    if time_col in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df[time_col])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_interval = duration_s / (len(df) - 1) if duration_s > 0 else sampling_interval
    else:
        actual_interval = sampling_interval

    self.logger.info(f"ウェーブレット実サンプリング間隔: {actual_interval*1000:.2f} ms")

    n_freqs = n_freqs or self.WAVELET_N_FREQS
    actual_fs = 1.0 / actual_interval
    target_freqs = np.logspace(
        np.log10(self.WAVELET_FREQ_MIN),
        np.log10(min(self.WAVELET_FREQ_MAX, actual_fs / 2.0)),
        n_freqs,
    )
    scales = pywt.frequency2scale(self.WAVELET_NAME, target_freqs * actual_interval)

    # --- 全サブキャリアのバッチ前処理（ループ前に一括実行）---
    from scipy.signal import detrend

    signal_matrix = np.stack(
        [df[col].to_numpy(dtype=np.float64, copy=False) for col in data_cols],
        axis=1,
    )  # shape: [T, n_sub]
    signal_matrix = np.nan_to_num(signal_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    signal_matrix = detrend(signal_matrix, axis=0, type="linear")  # バッチデトレンド

    signal_len = signal_matrix.shape[0]
    if signal_len < 2:
        self.logger.warning("信号長不足のためウェーブレット変換をスキップ")
        return pd.DataFrame()

    method = "fft" if signal_len >= self.WAVELET_FFT_METHOD_MIN_SIGNAL_LEN else "conv"

    # サブキャリア間の位相整合に依存しないように、各サブキャリアを独立に CWT し、
    # 上位レイヤでスペクトル平均を取る（フロントエンド magnitude_avg と整合）。
    amplitude_rows = []
    valid_cols = []
    frequency_axis: Optional[np.ndarray] = None
    for col_idx, col in enumerate(data_cols):
        signal = signal_matrix[:, col_idx]
        if np.allclose(signal, 0.0):
            self.logger.debug(f"サブキャリア {col}: 全ゼロのためスキップ")
            continue
        coefficients, freqs = pywt.cwt(
            signal,
            scales,
            self.WAVELET_NAME,
            sampling_period=actual_interval,
            method=method,
        )
        if frequency_axis is None:
            frequency_axis = freqs
        amplitude_rows.append(np.mean(np.abs(coefficients), axis=1).astype(np.float32, copy=False))
        valid_cols.append(col)

    if not amplitude_rows or frequency_axis is None:
        self.logger.warning("ウェーブレット変換結果が空です")
        return pd.DataFrame()

    wavelet_matrix = np.stack(amplitude_rows, axis=1)
    merged_wavelet_df = pd.DataFrame(wavelet_matrix, columns=valid_cols)
    merged_wavelet_df.insert(0, "frequency", frequency_axis)

    self.logger.info(
        f"ウェーブレット変換完了: {len(valid_cols)}サブキャリア, "
        f"{len(merged_wavelet_df)}周波数ポイント "
        f"({self.WAVELET_FREQ_MIN:.3f}–{float(np.max(frequency_axis)):.3f} Hz)"
    )

    return self.drop_invalid_rows(merged_wavelet_df)


def _compute_music_pseudospectrum(
    self,
    signal: np.ndarray,
    sampling_interval: float,
    frequencies: np.ndarray,
    embedding_dim: Optional[int] = None,
    model_order: Optional[int] = None,
    precomputed_steering: Optional[np.ndarray] = None,
) -> np.ndarray:
    """1次元信号に対する MUSIC 擬似スペクトルを計算する。

    precomputed_steering: 後方互換用の未使用引数。
    """
    if signal.size < 4:
        return np.array([], dtype=np.float32)

    cleaned = np.nan_to_num(signal.astype(np.float64, copy=False), nan=0.0, posinf=0.0, neginf=0.0)
    cleaned = cleaned - np.mean(cleaned)

    if np.allclose(cleaned, 0.0):
        return np.zeros(len(frequencies), dtype=np.float32)

    max_embedding = max(4, min(signal.size // 2, self.MUSIC_EMBEDDING_DIM))
    embedding_dim = embedding_dim or max_embedding
    embedding_dim = max(4, min(embedding_dim, signal.size - 1))

    snapshot_count = signal.size - embedding_dim + 1
    if snapshot_count < 2:
        return np.array([], dtype=np.float32)

    windows = np.lib.stride_tricks.sliding_window_view(cleaned, embedding_dim)
    covariance = (windows.conj().T @ windows) / max(embedding_dim - 1, 1)

    _, eigvecs = np.linalg.eigh(covariance)

    model_order = model_order or self.MUSIC_MODEL_ORDER
    model_order = max(1, min(model_order, embedding_dim - 1))
    noise_subspace = eigvecs[:, : embedding_dim - model_order]

    if noise_subspace.size == 0:
        return np.array([], dtype=np.float32)

    n_fft = len(frequencies)
    if n_fft == 0:
        return np.array([], dtype=np.float32)

    noise_fft = np.fft.fft(noise_subspace, n=n_fft, axis=0)
    denominator = np.sum(np.abs(noise_fft) ** 2, axis=1)
    denominator = np.maximum(denominator, 1e-12)

    return (1.0 / denominator).astype(np.float32, copy=False)


def apply_music_transform(
    self,
    df: pd.DataFrame,
    sampling_interval: float,
    time_col: str = "timestamp",
    n_freqs: Optional[int] = None,
) -> pd.DataFrame:
    """各サブキャリアに MUSIC 法を適用し、擬似スペクトルを返す。"""
    if df is None or df.empty:
        return pd.DataFrame()

    data_cols = _subcarrier_data_columns(df)
    if not data_cols:
        self.logger.warning("MUSIC適用可能な列が見つかりません")
        return pd.DataFrame()

    # --- 実サンプリングレートをタイムスタンプから計算 ---
    if time_col in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df[time_col])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        actual_interval = duration_s / (len(df) - 1) if duration_s > 0 else sampling_interval
    else:
        actual_interval = sampling_interval

    self.logger.info(f"MUSIC実サンプリング間隔: {actual_interval*1000:.2f} ms")

    from scipy.signal import detrend

    # --- 全サブキャリアのバッチ前処理 ---
    signal_matrix = np.stack(
        [df[col].to_numpy(dtype=np.float64, copy=False) for col in data_cols],
        axis=1,
    )  # shape: [T, n_sub]
    signal_matrix = np.nan_to_num(signal_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    signal_matrix = detrend(signal_matrix, axis=0, type="linear")

    signal_length, n_subcarriers = signal_matrix.shape
    actual_fs = 1.0 / actual_interval
    n_freqs = n_freqs or self.MUSIC_N_FREQS
    n_fft = max(n_freqs, signal_length)
    fft_freqs = np.arange(n_fft, dtype=np.float64) * actual_fs / n_fft
    max_music_freq = min(self.MUSIC_FREQ_MAX, actual_fs / 2.0)
    target_mask = (fft_freqs >= self.MUSIC_FREQ_MIN) & (fft_freqs <= max_music_freq)
    target_freqs = fft_freqs[target_mask]
    if target_freqs.size == 0:
        self.logger.warning("MUSIC対象周波数が空です")
        return pd.DataFrame()

    # embedding_dim を一度だけ計算（全サブキャリアで同一）
    max_embedding = max(4, min(signal_length // 2, self.MUSIC_EMBEDDING_DIM))
    embedding_dim = max(4, min(max_embedding, signal_length - 1))
    model_order = max(1, min(self.MUSIC_MODEL_ORDER, embedding_dim - 1))

    # --- バッチ MUSIC（全サブキャリアを一括ベクトル処理）---
    # サブキャリア間の位相整合に依存しないように、各サブキャリアを独立に
    # MUSIC 擬似スペクトル化し、上位レイヤで平均する（magnitude_avg と整合）。
    snapshot_count = signal_length - embedding_dim + 1

    # ゼロ信号を除外
    nonzero_mask = ~np.all(np.isclose(signal_matrix, 0.0), axis=0)
    valid_cols = [col for col, ok in zip(data_cols, nonzero_mask) if ok]
    valid_signals = signal_matrix[:, nonzero_mask]  # [T, n_valid]

    if valid_signals.shape[1] == 0 or snapshot_count < 2:
        self.logger.warning("MUSIC変換結果が空です")
        return pd.DataFrame()

    # Hankel 行列をスライディングウィンドウで一括構築し連続メモリに配置
    # windows shape: [snapshot_count, n_valid, embedding_dim]
    windows = np.lib.stride_tricks.sliding_window_view(valid_signals, embedding_dim, axis=0)
    # transpose 後に ascontiguousarray で C 連続にする（BLAS の性能を最大化）
    hankel_batch = np.ascontiguousarray(windows.transpose(1, 2, 0))  # [n_valid, L, snapshot_count]

    # バッチ共分散行列: [n_valid, L, L]
    cov_batch = (hankel_batch @ hankel_batch.transpose(0, 2, 1)) / max(embedding_dim - 1, 1)

    # バッチ固有値分解（NumPy の batched eigh）
    _, eigvecs_batch = np.linalg.eigh(cov_batch)  # eigvecs: [n_valid, L, L]

    # 固有値は昇順。論文式どおり、最大 E 個を信号部分空間、残りをノイズ部分空間とする。
    noise_subspaces = eigvecs_batch[:, :, : embedding_dim - model_order]

    noise_fft = np.fft.fft(noise_subspaces, n=n_fft, axis=1)  # [n_valid, n_fft, n_noise]
    denominator_batch = np.sum(np.abs(noise_fft) ** 2, axis=2)[:, target_mask]
    denominator_batch = np.maximum(denominator_batch, 1e-12)
    spectra_batch = (1.0 / denominator_batch).astype(np.float32)  # [n_valid, n_freqs]

    # 論文式のノイズ部分空間FFTに、観測信号自体の周波数成分を重み付けする。
    # 低域端の数値的な擬似ピークを抑え、呼吸由来の実ピークを推定に反映させる。
    signal_fft = np.abs(np.fft.fft(valid_signals, n=n_fft, axis=0)).T[:, target_mask]
    spectra_batch *= signal_fft.astype(np.float32, copy=False)

    # 出力 DataFrame 構築
    merged_music_df = pd.DataFrame(spectra_batch.T, columns=valid_cols)
    merged_music_df.insert(0, "frequency", target_freqs.astype(np.float32, copy=False))

    self.logger.info(
        f"MUSIC変換完了: {len(valid_cols)}サブキャリア (バッチ処理), "
        f"{len(merged_music_df)}周波数ポイント "
        f"({self.MUSIC_FREQ_MIN:.3f}–{float(np.max(target_freqs)):.3f} Hz)"
    )

    return self.drop_invalid_rows(merged_music_df)


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


def compare_breathing_rate_methods(
    self,
    method_rates: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    """3手法の呼吸レートをそれぞれ返す。"""
    return {
        "fft_bpm": float(method_rates["fft"]) if method_rates.get("fft") is not None else None,
        "wavelet_bpm": float(method_rates["wavelet"]) if method_rates.get("wavelet") is not None else None,
        "music_bpm": float(method_rates["music"]) if method_rates.get("music") is not None else None,
    }
