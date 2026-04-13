"""
PCAP解析サービス
Wi-Fi CSIデータをPCAPファイルから抽出・解析する
"""

from CSIKit.reader import get_reader
from CSIKit.util import csitools
from CSIKit.tools.batch_graph import BatchGraph
from CSIKit.filters.passband import lowpass
from CSIKit.filters.statistical import running_mean
from CSIKit.util.filters import hampel

import logging
import struct
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime
import json
import asyncio

try:
    from scapy.all import rdpcap
    from scapy.layers.dot11 import Dot11Beacon, Dot11ProbeReq, Dot11ProbeResp
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    logging.warning("Scapy not available. PCAP analysis will be limited.")

try:
    import pywt
    PYWAVELETS_AVAILABLE = True
except ImportError:
    PYWAVELETS_AVAILABLE = False
    logging.warning("PyWavelets not available. Wavelet analysis will be disabled.")

logger = logging.getLogger(__name__)

class PCAPAnalyzer:
    """PCAP解析クラス"""

    # チャネル設定（80MHz Wi-Fi 5/6）
    CHANNEL_CONFIGS = {
        '80MHz': {
            'guard_bands': [
                (-128, -122),  # 下側ガードバンド
                (122, 127)     # 上側ガードバンド
            ],
            'pilots': [-103, -75, -39, -11, 11, 39, 75, 103]  # パイロットサブキャリア
        }
    }

    # サンプリング設定
    DOWNSAMPLE_INTERVAL_S = 0.01  # 10ms = 100Hz サンプリング

    # 周波数ビン設定
    FREQUENCY_BIN_STEP = 0.01  # 0.01Hz刻み（表示用）

    # 呼吸周波数帯域（Hz）
    BREATHING_MIN_FREQ = 0.15  # 9 bpm
    BREATHING_MAX_FREQ = 0.4   # 24 bpm

    # ZKP回路用周波数設定（正常範囲外もカバーしてピーク判定を可能にする）
    ZKP_FREQ_START = 0.0   # Hz
    ZKP_FREQ_END   = 0.60  # Hz
    ZKP_FREQ_STEP  = 0.02  # Hz刻み → 31ビン (bin5=0.10Hz, bin25=0.50Hz)

    # ZKP設定
    ZKP_VECTOR_DIM = 4  # ZKP回路で要求される次元数
    ZKP_SCALE = 10000   # 固定小数点スケール

    # 全DataFrame ZKP回路用の設定
    MAX_FREQ_POINTS = 5000  # 最大周波数ポイント数
    MAX_SUBCARRIERS = 256   # 最大サブキャリア数

    # ウェーブレット変換設定
    WAVELET_FREQ_MIN = 0.01  # Hz（解析下限 = 0.6 bpm）
    WAVELET_FREQ_MAX = 2.0   # Hz（解析上限 = 120 bpm、呼吸帯域の5倍）
    WAVELET_N_FREQS = 200    # 対数スケール周波数点数
    WAVELET_NAME = "cmor1.5-1.0"
    BREATHING_RATE_AGREEMENT_THRESHOLD_BPM = 3.0
    WAVELET_FFT_METHOD_MIN_SIGNAL_LEN = 256
    MUSIC_FREQ_MIN = 0.01
    MUSIC_FREQ_MAX = 2.0
    MUSIC_N_FREQS = 256
    MUSIC_EMBEDDING_DIM = 32
    MUSIC_MODEL_ORDER = 2

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def contains_nan_or_inf(self, array: np.ndarray) -> bool:
        """
        配列にNaNまたはInfが含まれているかチェック

        Args:
            array: チェック対象の配列

        Returns:
            NaNまたはInfが含まれている場合True
        """
        arr = np.asarray(array)
        return np.isnan(arr).any() or np.isinf(arr).any()

    def normalize_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        信号を正規化（平均0、標準偏差1）

        Args:
            signal: 正規化対象の信号

        Returns:
            正規化された信号
        """
        if len(signal) == 0:
            return signal

        # NaNとInfを0に置き換え
        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)

        mean = np.mean(signal)
        std = np.std(signal)

        if std == 0:
            return signal - mean

        return (signal - mean) / std

    def drop_invalid_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        NaN、Infを含む行を削除

        Args:
            df: クリーニング対象のDataFrame

        Returns:
            クリーニング済みのDataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # 数値列を取得
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        if len(numeric_cols) == 0:
            return df

        # NaNを含む行を削除
        df_cleaned = df.dropna(subset=numeric_cols, how='any')

        # Infまたは-Infを含む行を削除
        df_cleaned = df_cleaned[~df_cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]

        return df_cleaned

    def make_bins(self, max_val: float, step: float) -> List[float]:
        """
        周波数ビンを作成

        Args:
            max_val: 最大値
            step: ステップ幅

        Returns:
            ビンのリスト
        """
        if step <= 0:
            raise ValueError("ステップは正の値である必要があります")

        num_steps = int(max_val / step)
        return [i * step for i in range(num_steps + 1)]

    def remove_unnecessary_subcarriers(
        self,
        df: pd.DataFrame,
        channel_width: str = '80MHz'
    ) -> pd.DataFrame:
        """
        ガードバンドとパイロットサブキャリアを削除

        Args:
            df: 処理対象のDataFrame
            channel_width: チャネル幅（デフォルト: '80MHz'）

        Returns:
            不要なサブキャリアを削除したDataFrame
        """
        if df is None or df.empty:
            return df

        if channel_width not in self.CHANNEL_CONFIGS:
            self.logger.warning(f"未サポートのチャネル幅: {channel_width}")
            return df

        # サブキャリア列を取得（数字の列名）
        subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]

        if not subcarrier_cols:
            self.logger.warning("サブキャリア列が見つかりません")
            return df

        original_count = len(subcarrier_cols)

        # DC成分（0番）を削除
        if '0' in df.columns:
            df = df.drop(columns=['0'])
            self.logger.debug("DC成分（サブキャリア0）を削除")

        # 設定を取得
        config = self.CHANNEL_CONFIGS[channel_width]

        # ガードバンドを削除
        for start, end in config['guard_bands']:
            guard_cols = [
                str(i) for i in range(start, end + 1)
                if str(i) in df.columns
            ]
            if guard_cols:
                df = df.drop(columns=guard_cols)
                self.logger.debug(f"ガードバンド削除: {start}～{end} ({len(guard_cols)}列)")

        # パイロットサブキャリアを削除
        pilot_cols = [str(i) for i in config['pilots'] if str(i) in df.columns]
        if pilot_cols:
            df = df.drop(columns=pilot_cols)
            self.logger.debug(f"パイロット削除: {len(pilot_cols)}列")

        remaining_count = len([col for col in df.columns if col.lstrip('-').isdigit()])
        self.logger.info(
            f"不要サブキャリア削除: {original_count}列 → {remaining_count}列 "
            f"({original_count - remaining_count}列削除)"
        )

        return df

    def apply_fourier_transform(
        self,
        df: pd.DataFrame,
        sampling_interval: float,
        time_col: str = 'timestamp'
    ) -> pd.DataFrame:
        """
        各サブキャリアにフーリエ変換を適用

        Args:
            df: 入力DataFrame
            sampling_interval: サンプリング間隔（秒）
            time_col: タイムスタンプ列名

        Returns:
            FFT結果のDataFrame（列: frequency, サブキャリア番号...）
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # 数値列（サブキャリア）を取得
        data_cols = [
            col for col in df.columns
            if col != time_col and pd.api.types.is_numeric_dtype(df[col])
        ]

        if not data_cols:
            self.logger.warning("FFT適用可能な列が見つかりません")
            return pd.DataFrame()

        all_fft_results = []

        for col in data_cols:
            signal = df[col].values

            if len(signal) < 2:
                self.logger.debug(f"サブキャリア {col}: データ不足 (長さ={len(signal)})")
                continue

            # FFT実行
            N = len(signal)
            yf = np.fft.fft(signal)
            xf = np.fft.fftfreq(N, d=sampling_interval)

            # 正の周波数のみ抽出
            positive_mask = xf > 0
            xf_positive = xf[positive_mask]
            yf_positive_abs = np.abs(yf[positive_mask])

            # DataFrame作成
            fft_df = pd.DataFrame({
                'frequency': xf_positive,
                col: yf_positive_abs
            })
            all_fft_results.append(fft_df.set_index('frequency'))

        if not all_fft_results:
            self.logger.warning("FFT結果が空です")
            return pd.DataFrame()

        # 全サブキャリアのFFT結果を結合
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
        time_col: str = 'timestamp',
        n_freqs: int = None
    ) -> pd.DataFrame:
        """
        各サブキャリアにCWT（連続ウェーブレット変換）を適用

        Morletウェーブレットを使用し、時間平均振幅スペクトルを算出する。
        FFT出力と同じDataFrame形式で返すため、downstream処理（ビン化・呼吸推定）を
        そのまま再利用できる。

        スケールと周波数の関係（Morletウェーブレット）:
            scale = w0 * fs / (2π × freq)
        ここで w0 はウェーブレットの角周波数パラメータ、fs はサンプリング周波数。

        Args:
            df: 入力DataFrame（タイムスタンプ列 + サブキャリア列）
            sampling_interval: サンプリング間隔（秒）
            time_col: タイムスタンプ列名
            n_freqs: 解析周波数点数（Noneの場合はWAVELET_N_FREQSを使用）

        Returns:
            ウェーブレット時間平均振幅のDataFrame（列: frequency, サブキャリア番号...）
        """
        if not PYWAVELETS_AVAILABLE:
            self.logger.warning("PyWavelets未インストールのためウェーブレット変換をスキップ")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        data_cols = [
            col for col in df.columns
            if col != time_col and pd.api.types.is_numeric_dtype(df[col])
        ]

        if not data_cols:
            self.logger.warning("ウェーブレット変換適用可能な列が見つかりません")
            return pd.DataFrame()

        n_freqs = n_freqs or self.WAVELET_N_FREQS
        fs = 1.0 / sampling_interval

        # 対数スケールで解析周波数を設定（低周波域の分解能を高める）
        target_freqs = np.logspace(
            np.log10(self.WAVELET_FREQ_MIN),
            np.log10(min(self.WAVELET_FREQ_MAX, fs / 2.0)),
            n_freqs
        )

        scales = pywt.frequency2scale(self.WAVELET_NAME, target_freqs * sampling_interval)
        frequency_axis = None
        amplitude_rows = []
        valid_cols = []

        for col in data_cols:
            sig = df[col].to_numpy(dtype=np.float32, copy=False)

            if len(sig) < 2:
                self.logger.debug(f"サブキャリア {col}: データ不足 (長さ={len(sig)})")
                continue

            sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0)
            method = 'fft' if len(sig) >= self.WAVELET_FFT_METHOD_MIN_SIGNAL_LEN else 'conv'

            coefficients, freqs = pywt.cwt(
                sig,
                scales,
                self.WAVELET_NAME,
                sampling_period=sampling_interval,
                method=method
            )

            # 時間平均振幅 (axis=1 は時間軸)
            time_avg_amplitude = np.mean(np.abs(coefficients), axis=1).astype(np.float32, copy=False)
            amplitude_rows.append(time_avg_amplitude)
            valid_cols.append(col)
            if frequency_axis is None:
                frequency_axis = freqs

        if not amplitude_rows:
            self.logger.warning("ウェーブレット変換結果が空です")
            return pd.DataFrame()

        wavelet_matrix = np.stack(amplitude_rows, axis=1)
        merged_wavelet_df = pd.DataFrame(
            wavelet_matrix,
            columns=valid_cols,
        )
        merged_wavelet_df.insert(0, 'frequency', frequency_axis)

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
        """
        1次元信号に対して MUSIC 擬似スペクトルを計算する。

        時系列を Hankel 行列に埋め込み、共分散行列の雑音部分空間から
        周波数ごとの擬似スペクトルを算出する。
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
        time_col: str = 'timestamp',
        n_freqs: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        各サブキャリアに MUSIC 法を適用し、擬似スペクトルを返す。

        返却形式は FFT / Wavelet と揃え、列を `frequency + subcarriers` にする。
        """
        if df is None or df.empty:
            return pd.DataFrame()

        data_cols = [
            col for col in df.columns
            if col != time_col and pd.api.types.is_numeric_dtype(df[col])
        ]

        if not data_cols:
            self.logger.warning("MUSIC適用可能な列が見つかりません")
            return pd.DataFrame()

        fs = 1.0 / sampling_interval
        n_freqs = n_freqs or self.MUSIC_N_FREQS
        target_freqs = np.linspace(
            self.MUSIC_FREQ_MIN,
            min(self.MUSIC_FREQ_MAX, fs / 2.0),
            n_freqs,
            dtype=np.float64,
        )

        spectra = []
        valid_cols = []

        for col in data_cols:
            sig = df[col].to_numpy(dtype=np.float32, copy=False)
            spectrum = self._compute_music_pseudospectrum(sig, sampling_interval, target_freqs)
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
        merged_music_df.insert(0, 'frequency', target_freqs.astype(np.float32, copy=False))

        self.logger.info(
            f"MUSIC変換完了: {len(valid_cols)}サブキャリア, "
            f"{len(merged_music_df)}周波数ポイント "
            f"({self.MUSIC_FREQ_MIN:.3f}–{float(np.max(target_freqs)):.3f} Hz)"
        )

        return self.drop_invalid_rows(merged_music_df)

    def estimate_breathing_rate(
        self,
        freq_df: pd.DataFrame,
        freq_col: str = 'frequency'
    ) -> Optional[float]:
        """
        周波数スペクトルから呼吸レートを推定

        全サブキャリアの平均振幅スペクトルを計算し、
        呼吸周波数帯域（BREATHING_MIN_FREQ–BREATHING_MAX_FREQ）の
        ピーク周波数から呼吸レート（BPM）を推定する。

        Args:
            freq_df: 周波数スペクトルのDataFrame（FFTまたはウェーブレット出力）
            freq_col: 周波数列名

        Returns:
            推定呼吸レート（BPM）。推定不能な場合はNone。
        """
        if freq_df is None or freq_df.empty or freq_col not in freq_df.columns:
            return None

        mask = (
            (freq_df[freq_col] >= self.BREATHING_MIN_FREQ) &
            (freq_df[freq_col] <= self.BREATHING_MAX_FREQ)
        )
        breathing_df = freq_df[mask]

        if breathing_df.empty:
            return None

        data_cols = [
            col for col in breathing_df.columns
            if col != freq_col
            and pd.api.types.is_numeric_dtype(breathing_df[col])
        ]

        if not data_cols:
            return None

        mean_amplitude = breathing_df[data_cols].mean(axis=1)

        if mean_amplitude.empty or mean_amplitude.isna().all():
            return None

        peak_idx = mean_amplitude.idxmax()
        peak_freq_hz = float(breathing_df.loc[peak_idx, freq_col])

        return peak_freq_hz * 60.0  # Hz → BPM

    def compare_breathing_rate_methods(self, method_rates: Dict[str, Optional[float]]) -> Dict[str, Any]:
        """
        複数手法の呼吸レート推定結果を比較する。
        """
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
        wavelet_bpm: Optional[float]
    ) -> Dict[str, Any]:
        """
        既存互換のための2手法比較ラッパー。
        """
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

    def average_magnitude_by_frequency_bins(
        self,
        df: pd.DataFrame,
        bins: List[float],
        freq_col: str = 'frequency'
    ) -> pd.DataFrame:
        """
        周波数ビンごとに振幅を平均化

        Args:
            df: FFT結果のDataFrame
            bins: 周波数ビンのリスト
            freq_col: 周波数列名

        Returns:
            ビンごとに平均化されたDataFrame
        """
        if df is None or df.empty or freq_col not in df.columns:
            return pd.DataFrame()

        df = df.copy()

        # 周波数をビンに分割
        df['freq_interval'] = pd.cut(
            df[freq_col],
            bins=bins,
            right=False,
            include_lowest=True
        )

        # 数値列を取得
        data_cols = [
            col for col in df.columns
            if col not in [freq_col, 'freq_interval']
            and pd.api.types.is_numeric_dtype(df[col])
        ]

        if not data_cols:
            self.logger.warning("平均化可能な列が見つかりません")
            return pd.DataFrame()

        # ビンごとに平均
        try:
            grouped_df = df.groupby('freq_interval', observed=False).mean(numeric_only=True).reset_index()
        except TypeError:
            grouped_df = df.groupby('freq_interval', observed=False)[data_cols].mean().reset_index()

        # frequency列を削除（ビン平均後は不要）
        if 'frequency' in grouped_df.columns:
            grouped_df = grouped_df.drop(columns=['frequency'], errors='ignore')

        self.logger.info(f"周波数ビン平均化完了: {len(grouped_df)}ビン")

        return grouped_df

    def extract_full_subcarrier_vectors(
        self,
        fft_df: pd.DataFrame,
        freq_col: str = 'frequency',
        use_binned: bool = False,
        freq_min: Optional[float] = None,
        freq_max: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        全サブキャリアの呼吸周波数帯域データを抽出（生データのまま）

        Args:
            fft_df: FFT結果のDataFrame
            freq_col: 周波数列名（'frequency' または 'freq_interval'）
            use_binned: ビン平均化後のDataFrameを使用する場合True
            freq_min: 抽出する周波数下限 Hz（省略時は BREATHING_MIN_FREQ）
            freq_max: 抽出する周波数上限 Hz（省略時は BREATHING_MAX_FREQ）

        Returns:
            {
                "csi_matrix": List[List[int]],  # [周波数ポイント][サブキャリア]
                "frequencies": List[int],        # 各周波数ポイント（Hz × ZKP_SCALE）
                "num_freq_points": int,
                "num_subcarriers": int
            }
        """
        if fft_df is None or fft_df.empty:
            self.logger.warning("FFT DataFrameが空です")
            return {
                "csi_matrix": [[0]],
                "frequencies": [0],
                "num_freq_points": 0,
                "num_subcarriers": 0
            }

        # DataFrameをコピー
        df = fft_df.copy()

        # 周波数でフィルタリング（呼吸周波数帯域のみ）
        if use_binned and 'freq_interval' in df.columns:
            # freq_interval列の中点を計算
            def get_interval_mid(x):
                if pd.isna(x):
                    return 0
                # Interval型の場合
                if hasattr(x, 'mid'):
                    return x.mid
                # 文字列の場合（例: "[0.0, 0.01)"）
                if isinstance(x, str):
                    try:
                        # "[0.0, 0.01)" -> "0.0, 0.01" -> ["0.0", "0.01"]
                        parts = x.strip('[]()').split(',')
                        left = float(parts[0].strip())
                        right = float(parts[1].strip())
                        return (left + right) / 2
                    except:
                        return 0
                return 0

            df['freq_mid'] = df['freq_interval'].apply(get_interval_mid)
            # 明示的にfloat型に変換（category型を回避）
            df['freq_mid'] = df['freq_mid'].astype(float)
            lo = freq_min if freq_min is not None else self.BREATHING_MIN_FREQ
            hi = freq_max if freq_max is not None else self.BREATHING_MAX_FREQ
            freq_mask = (
                (df['freq_mid'] >= lo) &
                (df['freq_mid'] <= hi)
            )
            freq_values = df.loc[freq_mask, 'freq_mid'].values
        else:
            lo = freq_min if freq_min is not None else self.BREATHING_MIN_FREQ
            hi = freq_max if freq_max is not None else self.BREATHING_MAX_FREQ
            # frequency列を使用
            freq_mask = (
                (df[freq_col] >= lo) &
                (df[freq_col] <= hi)
            )
            freq_values = df.loc[freq_mask, freq_col].values

        breathing_df = df[freq_mask]

        if breathing_df.empty:
            # デバッグ情報を出力
            if 'freq_mid' in df.columns:
                freq_range = f"{df['freq_mid'].min():.4f} - {df['freq_mid'].max():.4f} Hz"
            elif freq_col in df.columns:
                freq_range = f"{df[freq_col].min():.4f} - {df[freq_col].max():.4f} Hz"
            else:
                freq_range = "不明"

            self.logger.warning(
                f"呼吸周波数帯域({self.BREATHING_MIN_FREQ}-{self.BREATHING_MAX_FREQ}Hz)にデータがありません。"
                f"データの周波数範囲: {freq_range}"
            )
            return {
                "csi_matrix": [[0]],
                "frequencies": [0],
                "num_freq_points": 0,
                "num_subcarriers": 0
            }

        # サブキャリア列を取得
        subcarrier_cols = [
            col for col in breathing_df.columns
            if col not in [freq_col, 'freq_interval', 'freq_mid']
            and pd.api.types.is_numeric_dtype(breathing_df[col])
        ]

        if not subcarrier_cols:
            self.logger.warning("サブキャリア列が見つかりません")
            return {
                "csi_matrix": [[0]],
                "frequencies": [0],
                "num_freq_points": 0,
                "num_subcarriers": 0
            }

        # 2次元配列を構築: [周波数ポイント][サブキャリア]
        csi_matrix = []
        frequencies = []

        for idx, row in breathing_df.iterrows():
            freq_point_data = []
            for col in subcarrier_cols:
                amplitude = row[col]
                
                # NaNチェック
                if np.isnan(amplitude):
                    amplitude = 0.0
                
                # 整数化してスケーリング
                int_amplitude = int(amplitude * self.ZKP_SCALE)
                freq_point_data.append(int_amplitude)
            
            csi_matrix.append(freq_point_data)

        # 周波数値を整数化
        for freq in freq_values:
            freq_int = int(freq * self.ZKP_SCALE)
            frequencies.append(freq_int)

        num_freq_points = len(csi_matrix)
        num_subcarriers = len(subcarrier_cols) if csi_matrix else 0

        self.logger.info(
            f"全データ抽出完了: "
            f"{num_freq_points}周波数ポイント × {num_subcarriers}サブキャリア = "
            f"{num_freq_points * num_subcarriers}次元, "
            f"呼吸周波数帯域: {self.BREATHING_MIN_FREQ}～{self.BREATHING_MAX_FREQ}Hz"
        )

        return {
            "csi_matrix": csi_matrix,
            "frequencies": frequencies,
            "num_freq_points": num_freq_points,
            "num_subcarriers": num_subcarriers
        }

    async def analyze_and_generate_zkp(
        self,
        file_path: str,
        zkp_service: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        PCAPファイルを解析してZKP証明を生成

        Args:
            file_path: PCAPファイルのパス
            zkp_service: ZKPServiceインスタンス（Noneの場合は新規作成）

        Returns:
            {
                "fft_dataframe": FFT DataFrame,
                "zkp_proof": ZKP証明データ,
                "selected_subcarriers": 選択されたサブキャリア,
                "best_similarity": 最適類似度
            }
        """
        # FFT・ウェーブレット解析を実行
        analysis_result = self.analyze_pcap_file(file_path)
        fft_df = analysis_result["fft"]

        if fft_df.empty:
            self.logger.error("FFT解析に失敗しました")
            return {
                "fft_dataframe": pd.DataFrame(),
                "wavelet_dataframe": pd.DataFrame(),
                "music_dataframe": pd.DataFrame(),
                "breathing_rate_comparison": self.compare_breathing_rate_methods(
                    {"fft": None, "wavelet": None, "music": None}
                ),
                "zkp_proof": None,
                "error": "FFT analysis failed"
            }

        # ZKP用ベクトルを準備
        reference_vec, candidate_vecs = self.prepare_zkp_vectors_from_fft(fft_df)

        # ZKPServiceがない場合はインポートして作成
        if zkp_service is None:
            from app.services.zkp_service import ZKPService
            zkp_service = ZKPService()

        # ZKP証明を生成
        try:
            zkp_result = await zkp_service.generate_cosine_similarity_proof(
                reference_vector=reference_vec,
                candidate_vectors=candidate_vecs,
                scale=self.ZKP_SCALE
            )

            self.logger.info(
                f"ZKP証明生成完了: "
                f"bestIndex={zkp_result['bestIndex']}, "
                f"similarity={zkp_result['normalizedSimilarity']:.4f}"
            )

            return {
                "fft_dataframe": fft_df,
                "wavelet_dataframe": analysis_result["wavelet"],
                "music_dataframe": analysis_result["music"],
                "breathing_rate_fft_bpm": analysis_result["breathing_rate_fft_bpm"],
                "breathing_rate_wavelet_bpm": analysis_result["breathing_rate_wavelet_bpm"],
                "breathing_rate_music_bpm": analysis_result["breathing_rate_music_bpm"],
                "breathing_rate_comparison": analysis_result["breathing_rate_comparison"],
                "zkp_proof": zkp_result["proof"],
                "public_signals": zkp_result["publicSignals"],
                "best_index": zkp_result["bestIndex"],
                "best_similarity": zkp_result["normalizedSimilarity"],
                "reference_vector": reference_vec,
                "candidate_vectors": candidate_vecs
            }

        except Exception as e:
            self.logger.error(f"ZKP証明生成に失敗: {e}", exc_info=True)
            return {
                "fft_dataframe": fft_df,
                "wavelet_dataframe": analysis_result["wavelet"],
                "music_dataframe": analysis_result["music"],
                "breathing_rate_fft_bpm": analysis_result["breathing_rate_fft_bpm"],
                "breathing_rate_wavelet_bpm": analysis_result["breathing_rate_wavelet_bpm"],
                "breathing_rate_music_bpm": analysis_result["breathing_rate_music_bpm"],
                "breathing_rate_comparison": analysis_result["breathing_rate_comparison"],
                "zkp_proof": None,
                "error": str(e)
            }

    def _convert_csi_to_dataframe(
        self,
        csi_matrix: np.ndarray,
        timestamps: np.ndarray,
        no_subcarriers: int
    ) -> pd.DataFrame:
        """
        CSIKitのマトリックスをDataFrame形式に変換

        Args:
            csi_matrix: CSIマトリックス (frames, subcarriers, rx, tx)
            timestamps: タイムスタンプ配列
            no_subcarriers: サブキャリア数

        Returns:
            変換されたDataFrame（列: timestamp, 0, 1, 2, ...）
        """
        # 最初のRX/TXペア（0,0）のデータを抽出
        csi_matrix_first = csi_matrix[:, :, 0, 0]
        csi_matrix_squeezed = np.squeeze(csi_matrix_first)

        # DataFrameに変換
        # 各行がフレーム、各列がサブキャリア
        df_data = {}

        # タイムスタンプ列を追加
        df_data['timestamp'] = pd.to_datetime(timestamps, unit='s')

        # サブキャリア列を追加（列名は "0", "1", "2", ...）
        for subcarrier_idx in range(no_subcarriers):
            col_name = str(subcarrier_idx)
            df_data[col_name] = csi_matrix_squeezed[:, subcarrier_idx]

        df = pd.DataFrame(df_data)

        self.logger.info(f"DataFrame作成完了: shape={df.shape}")

        return df

    def analyze_pcap_file(
        self,
        file_path: str,
        include_wavelet: bool = True,
        include_music: bool = True,
    ) -> Dict[str, Any]:
        """
        PCAPファイルを解析してCSIデータを抽出（FFT・ウェーブレット変換の両方を実行）

        Args:
            file_path: PCAPファイルのパス
            include_wavelet: True の場合はウェーブレット変換も実行
            include_music: True の場合は MUSIC 法も実行

        Returns:
            {
                "fft": pd.DataFrame,               # FFT結果（周波数ビン平均化済み）
                                                   # 列: ['freq_interval', サブキャリア...]
                "wavelet": pd.DataFrame,           # ウェーブレット変換結果（周波数ビン平均化済み）
                                                   # 列: ['freq_interval', サブキャリア...]
                "music": pd.DataFrame,             # MUSIC 結果（周波数ビン平均化済み）
                                                   # 列: ['freq_interval', サブキャリア...]
                "breathing_rate_fft_bpm": float,   # FFTによる呼吸レート推定値 (BPM)
                "breathing_rate_wavelet_bpm": float, # ウェーブレットによる呼吸レート推定値 (BPM)
                "breathing_rate_music_bpm": float, # MUSICによる呼吸レート推定値 (BPM)
                "breathing_rate_comparison": dict  # 各手法の比較結果
            }
            解析失敗時は "fft" が空のDataFrameとなる。
        """
        _empty = {
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

        # CSIKitでPCAPファイルを読み込み
        my_reader = get_reader(file_path)
        csi_data = my_reader.read_file(file_path, scaled=True)
        csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)

        self.logger.info(f"CSIデータ読み込み完了: {no_frames}フレーム, {no_subcarriers}サブキャリア")

        # CSIマトリックスをDataFrame形式に変換
        df = self._convert_csi_to_dataframe(csi_matrix, csi_data.timestamps, no_subcarriers)

        # 無効データを除去
        df = self.drop_invalid_rows(df)

        if df.empty:
            self.logger.warning("有効なデータが存在しません")
            return _empty

        self.logger.info(f"データクリーニング後: {len(df)}行")

        # 不要なサブキャリアを削除（ガードバンド、パイロット、DC）
        df = self.remove_unnecessary_subcarriers(df, channel_width='80MHz')

        # サブキャリア列数を取得
        subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
        remaining_subcarriers = len(subcarrier_cols)

        # === FFT解析 ===
        fft_df = self.apply_fourier_transform(df, self.DOWNSAMPLE_INTERVAL_S)

        if fft_df.empty:
            self.logger.warning("FFT結果が空です")
            return _empty

        max_freq = fft_df['frequency'].max()
        bins = self.make_bins(max_freq, self.FREQUENCY_BIN_STEP)
        binned_fft_df = self.average_magnitude_by_frequency_bins(fft_df, bins)

        # FFTから呼吸レート推定
        breathing_rate_fft = self.estimate_breathing_rate(fft_df, freq_col='frequency')

        binned_wavelet_df = pd.DataFrame()
        binned_music_df = pd.DataFrame()
        breathing_rate_wavelet = None
        breathing_rate_music = None
        wavelet_bin_count = 0
        music_bin_count = 0
        wavelet_df = pd.DataFrame()
        music_df = pd.DataFrame()

        if include_wavelet:
            wavelet_df = self.apply_wavelet_transform(df, self.DOWNSAMPLE_INTERVAL_S)
        if include_music:
            music_df = self.apply_music_transform(df, self.DOWNSAMPLE_INTERVAL_S)

        if not wavelet_df.empty:
            binned_wavelet_df = self.average_magnitude_by_frequency_bins(wavelet_df, bins)
            breathing_rate_wavelet = self.estimate_breathing_rate(wavelet_df, freq_col='frequency')
            wavelet_bin_count = len(binned_wavelet_df)

        if not music_df.empty:
            binned_music_df = self.average_magnitude_by_frequency_bins(music_df, bins)
            breathing_rate_music = self.estimate_breathing_rate(music_df, freq_col='frequency')
            music_bin_count = len(binned_music_df)

        breathing_rate_comparison = self.compare_breathing_rate_methods({
            "fft": breathing_rate_fft,
            "wavelet": breathing_rate_wavelet,
            "music": breathing_rate_music,
        })

        # 処理結果をログ出力
        br_info = (
            f"FFT={breathing_rate_fft:.1f}bpm" if breathing_rate_fft else "FFT=N/A",
            f"Wavelet={breathing_rate_wavelet:.1f}bpm" if breathing_rate_wavelet else "Wavelet=N/A",
            f"MUSIC={breathing_rate_music:.1f}bpm" if breathing_rate_music else "MUSIC=N/A",
        )
        self.logger.info(
            f"解析完了 - フレーム数: {no_frames}, "
            f"サブキャリア: {no_subcarriers} → {remaining_subcarriers}, "
            f"有効行: {len(df)}, "
            f"FFTビン: {len(binned_fft_df)}, "
            f"ウェーブレットビン: {wavelet_bin_count}, "
            f"MUSICビン: {music_bin_count}, "
            f"最大周波数: {max_freq:.2f}Hz, "
            f"呼吸推定 [{', '.join(br_info)}]"
        )

        return {
            "fft": binned_fft_df,
            "wavelet": binned_wavelet_df,
            "music": binned_music_df,
            "breathing_rate_fft_bpm": breathing_rate_fft,
            "breathing_rate_wavelet_bpm": breathing_rate_wavelet,
            "breathing_rate_music_bpm": breathing_rate_music,
            "breathing_rate_comparison": breathing_rate_comparison,
        }

# サービスインスタンス
pcap_analyzer = PCAPAnalyzer()
