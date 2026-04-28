"""
PCAPAnalyzer の周波数解析関連処理。
"""

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.services.pcap_analyzer_common import _numeric_data_columns

try:
    import pywt

    PYWAVELETS_AVAILABLE = True
except ImportError:
    pywt = None
    PYWAVELETS_AVAILABLE = False


def apply_fourier_transform(
    self,
    df: pd.DataFrame,
    sampling_interval: float,
    time_col: str = "timestamp",
) -> pd.DataFrame:
    """各サブキャリアに FFT を適用する。

    実際のタイムスタンプから実サンプリングレートを計算し、
    等間隔リサンプリング・デトレンド・Hann窓を適用してから FFT する。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    data_cols = _numeric_data_columns(df, time_col=time_col)
    if not data_cols:
        self.logger.warning("FFT適用可能な列が見つかりません")
        return pd.DataFrame()

    # --- 実サンプリングレートをタイムスタンプから計算 ---
    if time_col in df.columns and len(df) >= 2:
        ts = pd.to_datetime(df[time_col])
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        if duration_s > 0:
            actual_fs = (len(df) - 1) / duration_s        # 実際の Hz
            target_fs = 1.0 / sampling_interval            # 目標 Hz (100 Hz)
            resample_factor = actual_fs / target_fs
        else:
            actual_fs = 1.0 / sampling_interval
            resample_factor = 1.0
    else:
        actual_fs = 1.0 / sampling_interval
        resample_factor = 1.0

    self.logger.info(f"実サンプリングレート: {actual_fs:.2f} Hz (目標: {1/sampling_interval:.0f} Hz)")

    all_fft_results = []
    for col in data_cols:
        signal = df[col].values.astype(np.float64)
        if len(signal) < 4:
            continue

        # 等間隔リサンプリング（実レート → 目標レート）
        if abs(resample_factor - 1.0) > 0.05:
            from scipy.signal import resample
            n_target = max(4, int(round(len(signal) / resample_factor)))
            signal = resample(signal, n_target)

        # デトレンド（線形トレンドと DC を除去）
        from scipy.signal import detrend
        signal = detrend(signal, type="linear")

        # Hann 窓（スペクトル漏れ抑制）
        window = np.hanning(len(signal))
        signal = signal * window

        sample_count = len(signal)
        yf = np.fft.rfft(signal)
        xf = np.fft.rfftfreq(sample_count, d=sampling_interval)

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

    data_cols = _numeric_data_columns(df, time_col=time_col)
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
    frequency_axis = None
    amplitude_rows = []
    valid_cols = []

    for col in data_cols:
        signal = df[col].to_numpy(dtype=np.float64, copy=False)
        if len(signal) < 2:
            self.logger.debug(f"サブキャリア {col}: データ不足 (長さ={len(signal)})")
            continue

        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)

        # デトレンド（DCオフセット・線形ドリフト除去）
        from scipy.signal import detrend
        signal = detrend(signal, type="linear")

        method = "fft" if len(signal) >= self.WAVELET_FFT_METHOD_MIN_SIGNAL_LEN else "conv"

        coefficients, freqs = pywt.cwt(
            signal,
            scales,
            self.WAVELET_NAME,
            sampling_period=actual_interval,
            method=method,
        )

        amplitude_rows.append(np.mean(np.abs(coefficients), axis=1).astype(np.float32, copy=False))
        valid_cols.append(col)
        if frequency_axis is None:
            frequency_axis = freqs

    if not amplitude_rows:
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
) -> np.ndarray:
    """1次元信号に対する MUSIC 擬似スペクトルを計算する。"""
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

    hankel = np.column_stack([
        cleaned[start:start + embedding_dim]
        for start in range(snapshot_count)
    ])
    covariance = (hankel @ hankel.conj().T) / snapshot_count

    eigvals, eigvecs = np.linalg.eigh(covariance)
    sort_idx = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, sort_idx]

    model_order = model_order or self.MUSIC_MODEL_ORDER
    model_order = max(1, min(model_order, embedding_dim - 1))
    noise_subspace = eigvecs[:, model_order:]

    if noise_subspace.size == 0:
        return np.array([], dtype=np.float32)

    sample_indices = np.arange(embedding_dim, dtype=np.float64)
    angular = 2.0 * np.pi * frequencies * sampling_interval
    steering = np.exp(-1j * np.outer(sample_indices, angular))
    projection = noise_subspace.conj().T @ steering
    denominator = np.sum(np.abs(projection) ** 2, axis=0)
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

    data_cols = _numeric_data_columns(df, time_col=time_col)
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

    actual_fs = 1.0 / actual_interval
    n_freqs = n_freqs or self.MUSIC_N_FREQS
    target_freqs = np.linspace(
        self.MUSIC_FREQ_MIN,
        min(self.MUSIC_FREQ_MAX, actual_fs / 2.0),
        n_freqs,
        dtype=np.float64,
    )

    from scipy.signal import detrend

    # --- 全サブキャリアの平均信号を計算（コヒーレント積算）---
    # 呼吸信号は全サブキャリアで同位相に乗るため加算で強調され、
    # 無相関なノイズは sqrt(N) 倍ではなく 1/N で平均化されて抑制される。
    # この平均信号に MUSIC を適用することで BPM 推定精度が向上する。
    signal_matrix = np.stack(
        [df[col].to_numpy(dtype=np.float64, copy=False) for col in data_cols],
        axis=1,
    )  # shape: [time, n_subcarriers]
    signal_matrix = np.nan_to_num(signal_matrix, nan=0.0, posinf=0.0, neginf=0.0)
    signal_matrix = detrend(signal_matrix, axis=0, type="linear")
    mean_signal = signal_matrix.mean(axis=1)  # shape: [time]

    mean_spectrum = self._compute_music_pseudospectrum(mean_signal, actual_interval, target_freqs)
    if mean_spectrum.size == 0:
        self.logger.warning("MUSIC平均信号スペクトル生成不可")
        return pd.DataFrame()

    # --- サブキャリアごとの MUSIC（ZKP 入力用に残す）---
    spectra = []
    valid_cols = []
    for col_idx, col in enumerate(data_cols):
        signal = signal_matrix[:, col_idx]
        spectrum = self._compute_music_pseudospectrum(signal, actual_interval, target_freqs)
        if spectrum.size == 0:
            self.logger.debug(f"サブキャリア {col}: MUSICスペクトル生成不可")
            continue
        spectra.append(spectrum)
        valid_cols.append(col)

    if not spectra:
        self.logger.warning("MUSIC変換結果が空です")
        return pd.DataFrame()

    music_matrix = np.stack(spectra, axis=1)
    merged_music_df = pd.DataFrame(music_matrix, columns=valid_cols)
    # _mean 列を先頭に挿入（BPM 推定に使用、ZKP では除外）
    merged_music_df.insert(0, "_mean", mean_spectrum.astype(np.float32, copy=False))
    merged_music_df.insert(0, "frequency", target_freqs.astype(np.float32, copy=False))

    self.logger.info(
        f"MUSIC変換完了: {len(valid_cols)}サブキャリア, "
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

    # MUSIC の場合は平均信号スペクトル列（_mean）を優先する。
    # 各サブキャリアのMUSICピークが異なる周波数に出るのを避けるため、
    # コヒーレント積算済みの _mean 列を直接使う。
    if "_mean" in data_cols:
        mean_amplitude = breathing_df["_mean"]
    else:
        # FFT / Wavelet: ピーク振幅が大きい上位10%サブキャリアの平均
        subcarrier_peaks = breathing_df[data_cols].max(axis=0)
        n_top = max(1, len(data_cols) // 10)
        top_cols = subcarrier_peaks.nlargest(n_top).index.tolist()
        mean_amplitude = breathing_df[top_cols].mean(axis=1)
    if mean_amplitude.empty or mean_amplitude.isna().all():
        return None

    # ガウシアン平滑化してからピーク検出（雑音耐性向上）
    values = mean_amplitude.values.astype(np.float64)
    if len(values) >= 5:
        from scipy.ndimage import gaussian_filter1d
        values = gaussian_filter1d(values, sigma=2)

    peak_idx_pos = int(np.argmax(values))
    peak_freq_hz = float(breathing_df[freq_col].iloc[peak_idx_pos])
    return peak_freq_hz * 60.0


def compare_breathing_rate_methods(
    self,
    method_rates: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    """複数手法の呼吸レート推定結果を比較する。"""
    normalized_rates = {
        method: (float(rate) if rate is not None else None)
        for method, rate in method_rates.items()
    }
    available = {method: rate for method, rate in normalized_rates.items() if rate is not None}

    comparison: Dict[str, Any] = {
        "methods": {f"{method}_bpm": rate for method, rate in normalized_rates.items()},
        "available_methods": list(available.keys()),
        "agreement_threshold_bpm": self.BREATHING_RATE_AGREEMENT_THRESHOLD_BPM,
        "min_bpm": min(available.values()) if available else None,
        "max_bpm": max(available.values()) if available else None,
        "spread_bpm": None,
        "spread_ratio": None,
        "is_consistent": None,
        "preferred_method": None,
    }
    comparison.update({f"{method}_bpm": rate for method, rate in normalized_rates.items()})

    if not available:
        return comparison

    preferred_order = ["fft", "wavelet", "music"]
    if len(available) == 1:
        comparison["preferred_method"] = next(iter(available))
        return comparison

    min_bpm = comparison["min_bpm"]
    max_bpm = comparison["max_bpm"]
    spread_bpm = max_bpm - min_bpm
    spread_ratio = (spread_bpm / max_bpm) if max_bpm and max_bpm > 0 else 0.0

    comparison["spread_bpm"] = spread_bpm
    comparison["spread_ratio"] = spread_ratio
    comparison["is_consistent"] = spread_bpm <= self.BREATHING_RATE_AGREEMENT_THRESHOLD_BPM

    if comparison["is_consistent"]:
        for method in preferred_order:
            if method in available:
                comparison["preferred_method"] = method
                break
    else:
        median_rate = float(np.median(list(available.values())))
        comparison["preferred_method"] = min(
            available,
            key=lambda method: (
                abs(available[method] - median_rate),
                preferred_order.index(method) if method in preferred_order else len(preferred_order),
            ),
        )

    return comparison


def compare_breathing_rate_estimates(
    self,
    fft_bpm: Optional[float],
    wavelet_bpm: Optional[float],
) -> Dict[str, Any]:
    """既存互換のための 2 手法比較ラッパー。"""
    comparison = self.compare_breathing_rate_methods({
        "fft": fft_bpm,
        "wavelet": wavelet_bpm,
    })
    return {
        "fft_bpm": comparison["methods"].get("fft_bpm"),
        "wavelet_bpm": comparison["methods"].get("wavelet_bpm"),
        "difference_bpm": comparison["spread_bpm"],
        "difference_ratio": comparison["spread_ratio"],
        "agreement_threshold_bpm": comparison["agreement_threshold_bpm"],
        "is_consistent": comparison["is_consistent"],
        "preferred_method": comparison["preferred_method"],
    }
