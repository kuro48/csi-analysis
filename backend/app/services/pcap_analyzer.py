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
    FREQUENCY_BIN_STEP = 0.01  # 0.01Hz刻み

    # 呼吸周波数帯域（Hz）
    BREATHING_MIN_FREQ = 0.15  # 9 bpm
    BREATHING_MAX_FREQ = 0.4   # 24 bpm

    # ZKP設定
    ZKP_VECTOR_DIM = 4  # ZKP回路で要求される次元数
    ZKP_SCALE = 10000   # 固定小数点スケール

    # 全DataFrame ZKP回路用の設定
    MAX_FREQ_POINTS = 5000  # 最大周波数ポイント数
    MAX_SUBCARRIERS = 256   # 最大サブキャリア数

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

    def prepare_zkp_vectors_from_fft(
        self,
        fft_df: pd.DataFrame,
        num_subcarriers: int = ZKP_VECTOR_DIM,
        freq_col: str = 'frequency'
    ) -> Tuple[List[int], List[List[int]]]:
        """
        FFT DataFrameから ZKP用の4次元ベクトルを準備

        Args:
            fft_df: FFT結果のDataFrame
            num_subcarriers: 選択するサブキャリア数（デフォルト: 4）
            freq_col: 周波数列名

        Returns:
            (reference_vector, candidate_vectors)
            - reference_vector: 参照ベクトル（4次元、整数）
            - candidate_vectors: 候補ベクトルリスト（各4次元、整数）
        """
        if fft_df is None or fft_df.empty:
            self.logger.warning("FFT DataFrameが空です")
            return [0, 0, 0, 0], [[0, 0, 0, 0]]

        # 呼吸周波数帯域のデータを抽出
        breathing_mask = (
            (fft_df[freq_col] >= self.BREATHING_MIN_FREQ) &
            (fft_df[freq_col] <= self.BREATHING_MAX_FREQ)
        )
        breathing_df = fft_df[breathing_mask]

        if breathing_df.empty:
            self.logger.warning("呼吸周波数帯域にデータがありません")
            return [0, 0, 0, 0], [[0, 0, 0, 0]]

        # サブキャリア列を取得
        subcarrier_cols = [
            col for col in breathing_df.columns
            if col != freq_col and col != 'freq_interval'
            and pd.api.types.is_numeric_dtype(breathing_df[col])
        ]

        if len(subcarrier_cols) < num_subcarriers:
            self.logger.warning(
                f"サブキャリア数が不足: {len(subcarrier_cols)} < {num_subcarriers}"
            )
            # 不足分をゼロパディング
            pass

        # 各サブキャリアの呼吸帯域での平均振幅を計算
        subcarrier_power = {}
        for col in subcarrier_cols:
            avg_amplitude = breathing_df[col].mean()
            if not np.isnan(avg_amplitude):
                subcarrier_power[col] = avg_amplitude

        # SNRが高い上位N個のサブキャリアを選択
        sorted_subcarriers = sorted(
            subcarrier_power.items(),
            key=lambda x: x[1],
            reverse=True
        )[:num_subcarriers]

        # 選択されたサブキャリアのリスト
        selected_cols = [col for col, _ in sorted_subcarriers]

        # 不足分をゼロパディング
        while len(selected_cols) < num_subcarriers:
            selected_cols.append(None)

        self.logger.info(f"選択されたサブキャリア: {[c for c in selected_cols if c is not None]}")

        # 参照ベクトルを作成（呼吸帯域の平均振幅）
        reference_vector = []
        for col in selected_cols:
            if col is not None:
                value = breathing_df[col].mean()
                # 整数化（ZKP_SCALEでスケーリング）
                int_value = int(value * self.ZKP_SCALE)
                reference_vector.append(int_value)
            else:
                reference_vector.append(0)

        # 候補ベクトルを作成（各周波数ポイントでのベクトル）
        # トップ2つの周波数ポイントを候補とする
        candidate_vectors = []

        # 各サブキャリアの合計パワーで周波数ポイントをランク付け
        breathing_df_copy = breathing_df.copy()
        breathing_df_copy['total_power'] = breathing_df_copy[selected_cols[:len([c for c in selected_cols if c is not None])]].sum(axis=1)
        top_freq_points = breathing_df_copy.nlargest(2, 'total_power')

        for idx, row in top_freq_points.iterrows():
            candidate_vec = []
            for col in selected_cols:
                if col is not None:
                    value = row[col]
                    int_value = int(value * self.ZKP_SCALE) if not np.isnan(value) else 0
                    candidate_vec.append(int_value)
                else:
                    candidate_vec.append(0)
            candidate_vectors.append(candidate_vec)

        # 候補ベクトルが1つの場合は2つ目をダミーで追加
        while len(candidate_vectors) < 2:
            candidate_vectors.append([0, 0, 0, 0])

        self.logger.info(
            f"ZKPベクトル準備完了: "
            f"reference={reference_vector}, "
            f"candidates={len(candidate_vectors)}"
        )

        return reference_vector, candidate_vectors

    def prepare_full_dataframe_for_zkp(
        self,
        fft_df: pd.DataFrame,
        freq_col: str = 'frequency'
    ) -> Dict[str, Any]:
        """
        FFT DataFrameを全DataFrame ZKP回路用の入力形式に変換

        Args:
            fft_df: FFT結果のDataFrame（周波数ビン平均化前のもの）
            freq_col: 周波数列名

        Returns:
            {
                "csi_amplitude": List[List[int]],  # [5000][256]
                "frequency_bins": List[int],       # [5000]
                "num_freq_points": int,
                "num_subcarriers": int
            }
        """
        if fft_df is None or fft_df.empty:
            self.logger.warning("FFT DataFrameが空です")
            return {
                "csi_amplitude": [[0] * self.MAX_SUBCARRIERS] * self.MAX_FREQ_POINTS,
                "frequency_bins": [0] * self.MAX_FREQ_POINTS,
                "num_freq_points": 0,
                "num_subcarriers": 0
            }

        # サブキャリア列を取得
        subcarrier_cols = [
            col for col in fft_df.columns
            if col != freq_col and col != 'freq_interval'
            and pd.api.types.is_numeric_dtype(fft_df[col])
        ]

        actual_freq_points = min(len(fft_df), self.MAX_FREQ_POINTS)
        actual_subcarriers = min(len(subcarrier_cols), self.MAX_SUBCARRIERS)

        self.logger.info(
            f"DataFrame変換: {actual_freq_points}周波数ポイント × "
            f"{actual_subcarriers}サブキャリア"
        )

        # 周波数ビンを整数化（Hz × 10000）
        frequency_bins = []
        for i in range(actual_freq_points):
            freq_value = fft_df[freq_col].iloc[i]
            freq_int = int(freq_value * self.ZKP_SCALE)
            frequency_bins.append(freq_int)

        # 不足分をゼロパディング
        while len(frequency_bins) < self.MAX_FREQ_POINTS:
            frequency_bins.append(0)

        # CSI振幅を整数化
        csi_amplitude = []
        for i in range(actual_freq_points):
            row = []
            for col in subcarrier_cols[:actual_subcarriers]:
                value = fft_df[col].iloc[i]
                int_value = int(value) if not np.isnan(value) else 0
                row.append(int_value)

            # サブキャリア数をMAX_SUBCARRIERSまでパディング
            while len(row) < self.MAX_SUBCARRIERS:
                row.append(0)

            csi_amplitude.append(row)

        # 周波数ポイント数をMAX_FREQ_POINTSまでパディング
        while len(csi_amplitude) < self.MAX_FREQ_POINTS:
            csi_amplitude.append([0] * self.MAX_SUBCARRIERS)

        self.logger.info(
            f"ZKP入力データ準備完了: "
            f"shape=({len(csi_amplitude)}, {len(csi_amplitude[0])})"
        )

        return {
            "csi_amplitude": csi_amplitude,
            "frequency_bins": frequency_bins,
            "num_freq_points": actual_freq_points,
            "num_subcarriers": actual_subcarriers
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
        # FFT解析を実行
        fft_df = self.analyze_pcap_file(file_path)

        if fft_df.empty:
            self.logger.error("FFT解析に失敗しました")
            return {
                "fft_dataframe": pd.DataFrame(),
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
                "zkp_proof": None,
                "error": str(e)
            }

    async def analyze_and_generate_full_zkp(
        self,
        file_path: str,
        zkp_service: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        PCAPファイルを解析して全DataFrame ZKP証明を生成

        警告: この処理は非常に時間がかかります（30分～数時間）

        Args:
            file_path: PCAPファイルのパス
            zkp_service: ZKPServiceインスタンス（Noneの場合は新規作成）

        Returns:
            {
                "binned_fft_dataframe": ビン平均化後のDataFrame,
                "fft_dataframe": ビン平均化前のFFT DataFrame,
                "zkp_proof": ZKP証明データ,
                "best_subcarrier_indices": 最適サブキャリアインデックス,
                "breathing_frequency": 呼吸周波数,
                "confidence_score": 信頼度スコア
            }
        """
        self.logger.warning("全DataFrame ZKP証明生成を開始します（非常に時間がかかる可能性があります）")

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
            return {
                "error": "No valid data"
            }

        # 不要なサブキャリアを削除
        df = self.remove_unnecessary_subcarriers(df, channel_width='80MHz')

        # フーリエ変換を適用（ビン平均化前）
        fft_df = self.apply_fourier_transform(df, self.DOWNSAMPLE_INTERVAL_S)

        if fft_df.empty:
            self.logger.warning("FFT結果が空です")
            return {
                "error": "FFT failed"
            }

        # ビン平均化も実行（互換性のため）
        max_freq = fft_df['frequency'].max()
        bins = self.make_bins(max_freq, self.FREQUENCY_BIN_STEP)
        binned_fft_df = self.average_magnitude_by_frequency_bins(fft_df, bins)

        # 全DataFrame ZKP用の入力データを準備
        zkp_input = self.prepare_full_dataframe_for_zkp(fft_df)

        # ZKPServiceがない場合はインポートして作成
        if zkp_service is None:
            from app.services.zkp_service import ZKPService
            zkp_service = ZKPService()

        # ZKP証明を生成
        try:
            self.logger.info("全DataFrame ZKP証明生成を開始...")
            zkp_result = await zkp_service.generate_full_dataframe_proof(
                csi_amplitude=zkp_input["csi_amplitude"],
                frequency_bins=zkp_input["frequency_bins"],
                num_freq_points=zkp_input["num_freq_points"],
                num_subcarriers=zkp_input["num_subcarriers"]
            )

            self.logger.info(
                f"全DataFrame ZKP証明生成完了: "
                f"breathing_frequency={zkp_result.get('breathing_frequency', 0) / 10000:.4f}Hz"
            )

            return {
                "binned_fft_dataframe": binned_fft_df,
                "fft_dataframe": fft_df,
                "zkp_proof": zkp_result.get("proof"),
                "public_signals": zkp_result.get("publicSignals"),
                "best_subcarrier_indices": zkp_result.get("best_subcarrier_indices"),
                "breathing_frequency": zkp_result.get("breathing_frequency"),
                "confidence_score": zkp_result.get("confidence_score"),
                "zkp_input": zkp_input
            }

        except Exception as e:
            self.logger.error(f"全DataFrame ZKP証明生成に失敗: {e}", exc_info=True)
            return {
                "binned_fft_dataframe": binned_fft_df,
                "fft_dataframe": fft_df,
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

    def analyze_pcap_file(self, file_path: str) -> pd.DataFrame:
        """
        PCAPファイルを解析してCSIデータを抽出

        Args:
            file_path: PCAPファイルのパス

        Returns:
            周波数ビン平均化後のFFT結果DataFrame
            列: ['freq_interval', サブキャリア番号...]
        """
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
            return pd.DataFrame()

        self.logger.info(f"データクリーニング後: {len(df)}行")

        # 不要なサブキャリアを削除（ガードバンド、パイロット、DC）
        df = self.remove_unnecessary_subcarriers(df, channel_width='80MHz')

        # サブキャリア列数を取得
        subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
        remaining_subcarriers = len(subcarrier_cols)

        # フーリエ変換を適用
        fft_df = self.apply_fourier_transform(df, self.DOWNSAMPLE_INTERVAL_S)

        if fft_df.empty:
            self.logger.warning("FFT結果が空です")
            return pd.DataFrame()

        # 周波数ビンを作成
        max_freq = fft_df['frequency'].max()
        bins = self.make_bins(max_freq, self.FREQUENCY_BIN_STEP)

        # 周波数ビンごとに平均化
        binned_fft_df = self.average_magnitude_by_frequency_bins(fft_df, bins)

        # 処理結果をログ出力
        self.logger.info(
            f"解析完了 - フレーム数: {no_frames}, "
            f"サブキャリア: {no_subcarriers} → {remaining_subcarriers}, "
            f"有効行: {len(df)}, "
            f"FFT周波数ポイント: {len(fft_df)}, "
            f"周波数ビン: {len(binned_fft_df)}, "
            f"最大周波数: {max_freq:.2f}Hz"
        )


        # 周波数ビン平均化後のDataFrameを返す
        return binned_fft_df

        # try:
        #     packets = rdpcap(file_path)
        #     timestamps = [pkt.time for pkt in packets if pkt.haslayer('UDP')]
        # except FileNotFoundError:
        #     print(f"Error: PCAP file not found at {file_path}")
        #     return []
        # except Exception as e:
        #     print(f"Error reading or processing PCAP file {file_path}: {e}")
        #     return []
        


    # def save_initial_data(df, output_dir, input_base):
    #     base_name_for_file = os.path.basename(input_base)
    #     initial_file = os.path.join(output_dir, f"{base_name_for_file}_initial_processed.csv")
    #     df.to_csv(initial_file, index=False)
    #     print(f"Initial processed data saved to {initial_file}")
        
    #     plot_file = os.path.join(output_dir, f"{base_name_for_file}_initial_plot.png")
    #     plot_time_series_from_dataframe(df, plot_file, "Initial Processed")

    # def make_bins(max_val, step):
    #     if step <= 0:
    #         raise ValueError("Step must be positive")
    #     num_steps = int(max_val / step)
    #     return [i * step for i in range(num_steps + 1)]

    # def drop_invalid_rows(df):
    #     if df is None or df.empty:
    #         return pd.DataFrame()
    #     numeric_cols = df.select_dtypes(include=[np.number]).columns
    #     if not numeric_cols.any():
    #         return df 
    #     df_cleaned = df.dropna(subset=numeric_cols, how='any')
    #     df_cleaned = df_cleaned[~df_cleaned[numeric_cols].isin([np.inf, -np.inf]).any(axis=1)]
    #     return df_cleaned

    # def normalize_signal(signal):
    #     if len(signal) == 0:
    #         return signal
    #     signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
    #     mean = np.mean(signal)
    #     std = np.std(signal)
    #     if std == 0:
    #         return signal - mean
    #     return (signal - mean) / std

    # def contains_nan_or_inf(array):
    #     arr = np.asarray(array)
    #     return np.isnan(arr).any() or np.isinf(arr).any()

    # def _bandpass_filter(data, lowcut, highcut, fs, order=Config.FILTER_ORDER):
    #     nyquist = 0.5 * fs
    #     low = lowcut / nyquist
    #     high = highcut / nyquist
    #     low = max(1e-9, low) 
    #     high = min(1.0 - 1e-9, high)
    #     if low >= high:
    #         return data
    #     try:
    #         b, a = butter(order, [low, high], btype='band')
    #         y = filtfilt(b, a, data)
    #         return y
    #     except ValueError as e:
    #         return data

    # def remove_unnecessary_subcarriers(df, channel_width='80MHz'):
    #     if df is None or df.empty:
    #         return df

    #     if channel_width not in Config.CHANNEL_CONFIGS:
    #         raise ValueError(f"Unsupported channel width: {channel_width}")

    #     subcarrier_cols = [col for col in df.columns if col.isdigit()]
    #     if not subcarrier_cols:
    #         return df

    #     if '0' in df.columns:
    #         df = df.drop(columns=['0'])
        
    #     config = Config.CHANNEL_CONFIGS[channel_width]
        
    #     for start, end in config['guard_bands']:
    #         guard_cols = [str(i) for i in range(start, end + 1) if str(i) in df.columns] # end inclusive
    #         if guard_cols:
    #             df = df.drop(columns=guard_cols)
        
    #     pilot_cols = [str(i) for i in config['pilots'] if str(i) in df.columns]
    #     if pilot_cols:
    #         df = df.drop(columns=pilot_cols)
        
    #     print(f"Removed unnecessary subcarriers for {channel_width}. Remaining: {len([col for col in df.columns if col.isdigit()])}")
    #     return df

    # def preprocess_csi_data(csi_kit_csv_path, pcap_timestamps, channel_width='80MHz'):
    #     try:
    #         print(f"Reading CSV file: {csi_kit_csv_path}")
    #         print(f"CSV file exists: {os.path.exists(csi_kit_csv_path)}")
    #         if os.path.exists(csi_kit_csv_path):
    #             print(f"CSV file size: {os.path.getsize(csi_kit_csv_path)} bytes")
            
    #         df = pd.read_csv(csi_kit_csv_path)
    #         if df.empty:
    #             print("Error: CSV file is empty")
    #             return pd.DataFrame()
    #         print(f"CSV file loaded successfully. Shape: {df.shape}")
    #         print(f"Columns: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error reading CSV: {e}")
    #         return None

    #     try:
    #         print("Renaming columns...")
    #         original_columns = df.columns.tolist()
    #         df.rename(columns=lambda col: re.sub(r'^Sub\s+(-?\d+)\s+RXTX\s+0/0$', r'\1', col), inplace=True)
    #         print(f"Original columns: {original_columns}")
    #         print(f"Columns after renaming: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error renaming columns: {e}")
    #         return None

    #     try:
    #         print("Removing unnecessary subcarriers...")
    #         df = remove_unnecessary_subcarriers(df, channel_width)
    #         print(f"Shape after removing subcarriers: {df.shape}")
    #         print(f"Remaining columns: {df.columns.tolist()}")
    #     except Exception as e:
    #         print(f"Error removing subcarriers: {e}")
    #         return None

    #     try:
    #         print("Converting subcarrier columns to numeric...")
    #         subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
    #         print(f"Found {len(subcarrier_cols)} subcarrier columns")
    #         for col in subcarrier_cols:
    #             df[col] = pd.to_numeric(df[col], errors='coerce')
    #         print(f"Number of subcarrier columns after conversion: {len(subcarrier_cols)}")
    #     except Exception as e:
    #         print(f"Error converting subcarrier columns: {e}")
    #         return None

    #     if not pcap_timestamps:
    #         print("Error: No PCAP timestamps provided")
    #         return None

    #     try:
    #         print("Processing timestamps...")
    #         print(f"Number of timestamps: {len(pcap_timestamps)}")
    #         print(f"DataFrame length: {len(df)}")
    #         min_len = min(len(pcap_timestamps), len(df))
    #         if min_len == 0:
    #             print("Error: No data points available")
    #             return pd.DataFrame()

    #         df = df.iloc[:min_len]
    #         df.insert(0, 'timestamp', pcap_timestamps[:min_len])
    #         print(f"Data shape after timestamp processing: {df.shape}")

    #         print("Converting timestamps to datetime...")
    #         df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp'], errors='coerce'), unit='s')
    #         print("Timestamp conversion successful")
    #     except Exception as e:
    #         print(f"Error processing timestamps: {e}")
    #         return None

    #     try:
    #         print("Dropping invalid rows...")
    #         print(f"DataFrame shape before dropping invalid rows: {df.shape}")
    #         df = drop_invalid_rows(df)
    #         print(f"Final data shape: {df.shape}")
    #         return df
    #     except Exception as e:
    #         print(f"Error dropping invalid rows: {e}")
    #         return None

    # def resample_data_by_interval(df_input, interval_sec, time_col='timestamp'):
    #     if df_input is None or df_input.empty or time_col not in df_input.columns:
    #         return pd.DataFrame()
        
    #     df = df_input.set_index(time_col)
    #     if not isinstance(df.index, pd.DatetimeIndex):
    #         return pd.DataFrame()

    #     try:
    #         resampled_df = df.resample(f'{int(interval_sec*1000)}ms').mean().reset_index()
    #     except Exception as e:
    #         return pd.DataFrame()
    #     return drop_invalid_rows(resampled_df)

    # def bandpass_filter_csv(df_input, lowcut, highcut, fs, time_col='timestamp', order=Config.FILTER_ORDER):
    #     if df_input is None or df_input.empty: return pd.DataFrame()
    #     df = df_input.copy()
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return df

    #     for col in data_cols:
    #         if contains_nan_or_inf(df[col]):
    #             continue
            
    #         if np.std(df[col]) == 0:
    #             continue
                
    #         try:
    #             df[col] = np.nan_to_num(df[col], nan=0.0, posinf=0.0, neginf=0.0)
    #             df[col] = normalize_signal(df[col])
    #             df[col] = df[col] + 1e-10
                
    #             try:
    #                 if np.all(np.isfinite(df[col])):
    #                     df[col] = detrend(df[col])
    #                 else:
    #                     print(f"Warning: Non-finite values in column {col} after normalization")
    #                     continue
    #             except Exception as e:
    #                 print(f"Warning: Detrend failed for column {col}: {e}")
    #                 continue
                    
    #             df[col] = _bandpass_filter(df[col], lowcut, highcut, fs, order)
                
    #             if contains_nan_or_inf(df[col]):
    #                 print(f"Warning: Invalid values detected in column {col} after filtering")
    #                 continue
                
    #         except Exception as e:
    #             print(f"Warning: Error processing column {col}: {e}")
    #             continue
                
    #     return drop_invalid_rows(df)

    # def apply_fourier_transform(df_input, sampling_interval, time_col='timestamp'):
    #     if df_input is None or df_input.empty: return pd.DataFrame()
    #     df = df_input.copy()
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return pd.DataFrame()

    #     all_fft_results = []
    #     for col in data_cols:
    #         signal = df[col].values
    #         if len(signal) < 2 : continue

    #         N = len(signal)
    #         yf = np.fft.fft(signal)
    #         xf = np.fft.fftfreq(N, d=sampling_interval)
            
    #         positive_mask = xf > 0
    #         xf_positive = xf[positive_mask]
    #         yf_positive_abs = np.abs(yf[positive_mask])

    #         fft_df = pd.DataFrame({'frequency': xf_positive, col: yf_positive_abs})
    #         all_fft_results.append(fft_df.set_index('frequency'))

    #     if not all_fft_results: return pd.DataFrame()
        
    #     merged_fft_df = pd.concat(all_fft_results, axis=1).reset_index()
    #     return drop_invalid_rows(merged_fft_df)

    # def average_magnitude_by_frequency_bins(df_input, bins, freq_col='frequency'):
    #     if df_input is None or df_input.empty or freq_col not in df_input.columns:
    #         return pd.DataFrame()
    #     df = df_input.copy()
    #     df['freq_interval'] = pd.cut(df[freq_col], bins=bins, right=False, include_lowest=True)
        
    #     data_cols = [col for col in df.columns if col not in [freq_col, 'freq_interval'] and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return pd.DataFrame()

    #     try:
    #         grouped_df = df.groupby('freq_interval', observed=False).mean(numeric_only=True).reset_index()
    #     except TypeError:
    #         grouped_df = df.groupby('freq_interval', observed=False)[data_cols].mean().reset_index()

    #     if 'frequency' in grouped_df.columns:
    #         grouped_df = grouped_df.drop(columns=['frequency'], errors='ignore')
    #     return grouped_df

    # def compute_cosine_similarity(file1_path, file2_path, output_path, identifier_col='freq_interval'):
    #     try:
    #         df1 = pd.read_csv(file1_path)
    #         df2 = pd.read_csv(file2_path)
    #     except Exception as e:
    #         print(f"Error reading CSV for cosine similarity: {e}")
    #         return

    #     if df1.empty or df2.empty or identifier_col not in df1.columns or identifier_col not in df2.columns:
    #         return

    #     merged_df = pd.merge(df1, df2, on=identifier_col, suffixes=('_1', '_2'), how='inner')
    #     if merged_df.empty:
    #         return
        
    #     data_cols_1 = [col for col in merged_df.columns if col.endswith('_1') and col[:-2] != identifier_col and pd.api.types.is_numeric_dtype(merged_df[col])]
    #     data_cols_2 = [col for col in merged_df.columns if col.endswith('_2') and col[:-2] != identifier_col and pd.api.types.is_numeric_dtype(merged_df[col])]

    #     if not data_cols_1 or not data_cols_2 or len(data_cols_1) != len(data_cols_2):
    #         return

    #     vec1 = merged_df[data_cols_1].values.T
    #     vec2 = merged_df[data_cols_2].values.T

    #     if vec1.shape[1] == 0 or vec2.shape[1] == 0 :
    #         return

    #     avg_vec1 = np.mean(vec1, axis=0) if vec1.ndim > 1 else vec1.flatten()
    #     avg_vec2 = np.mean(vec2, axis=0) if vec2.ndim > 1 else vec2.flatten()

    #     if avg_vec1.ndim == 0 : avg_vec1 = avg_vec1.reshape(1, -1)
    #     if avg_vec2.ndim == 0 : avg_vec2 = avg_vec2.reshape(1, -1)
    #     if avg_vec1.shape[0] == 1 and avg_vec1.shape[1] > 1:
    #         pass
    #     elif avg_vec1.shape[1] == 1 and avg_vec1.shape[0] > 1:
    #         avg_vec1 = avg_vec1.T
    #         avg_vec2 = avg_vec2.T
    #     elif avg_vec1.size == 0 or avg_vec2.size == 0:
    #         print("Empty vectors after averaging, cannot compute similarity.")
    #         return

    #     try:
    #         similarity = cosine_similarity(avg_vec1.reshape(1, -1), avg_vec2.reshape(1, -1))[0, 0]
    #         pd.DataFrame([{'similarity': similarity}]).to_csv(output_path, index=False)
    #         print(f"Cosine similarity: {similarity:.4f} -> saved to {output_path}")
    #     except ValueError as e:
    #         print(f"Error computing cosine similarity (possibly due to zero vectors): {e}")

    # def plot_time_series_from_dataframe(df, output_path, title_suffix='', time_col='timestamp'):
    #     if df is None or df.empty or time_col not in df.columns: return
    #     data_cols = [col for col in df.columns if col != time_col and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols: return

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     for i, col in enumerate(data_cols):
    #         color = Config.PLOT_COLORS[i % len(Config.PLOT_COLORS)]
    #         plt.plot(df[time_col], df[col], color=color, linewidth=Config.PLOT_LINE_WIDTH)
        
    #     plt.xlabel("Time")
    #     plt.ylabel("Amplitude")
    #     plt.title(f"Time Series {title_suffix}")
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.xticks(rotation=45)
        
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()
    #     print(f"Time series plot saved to {output_path}")

    # def plot_fft_from_dataframe(df, output_path, title_suffix='', freq_col='frequency'):
    #     if df is None or df.empty or freq_col not in df.columns:
    #         return

    #     data_cols = [col for col in df.columns if col != freq_col and col != 'freq_interval' and pd.api.types.is_numeric_dtype(df[col])]
    #     if not data_cols:
    #         return

    #     avg_spectrum = df[data_cols].mean(axis=1)
        
    #     threshold = np.max(avg_spectrum) * 0.01
    #     significant_mask = avg_spectrum > threshold
    #     if significant_mask.any():
    #         cutoff_freq = df[freq_col][significant_mask].iloc[-1]
    #     else:
    #         cutoff_freq = df[freq_col].iloc[-1] if not df[freq_col].empty else 0 # Handle empty case

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     mask = df[freq_col] <= cutoff_freq
    #     plt.plot(df[freq_col][mask], avg_spectrum[mask], 
    #             color=Config.PLOT_COLORS[0], 
    #             linewidth=Config.PLOT_LINE_WIDTH)
        
    #     plt.xlabel("Frequency (Hz)")
    #     plt.ylabel("Magnitude")
    #     plt.title(f"FFT Spectrum {title_suffix}")
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.xticks(rotation=45)
        
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def select_best_subcarriers(fft_df, freq_col='frequency', freq_min=None, freq_max=None):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return []

    #     data_cols = [col for col in fft_df.columns if col != freq_col and pd.api.types.is_numeric_dtype(fft_df[col])] # check dtype
    #     if not data_cols:
    #         return []

    #     if freq_min is None:
    #         freq_min = Config.BREATHING_MIN_FREQ
    #     if freq_max is None:
    #         freq_max = Config.BREATHING_MAX_FREQ

    #     mask = (fft_df[freq_col] >= freq_min) & (fft_df[freq_col] <= freq_max)
    #     target_range = fft_df[mask]

    #     snr_scores = {}
    #     for col in data_cols:
    #         if not pd.api.types.is_numeric_dtype(target_range[col]) or not pd.api.types.is_numeric_dtype(fft_df[~mask][col]):
    #             continue # Skip non-numeric columns that might have slipped through
    #         target_power = np.mean(target_range[col] ** 2)
    #         noise_power = np.mean(fft_df[~mask][col] ** 2) # ensure column exists and is numeric
    #         if noise_power > 0: # and not np.isnan(target_power) and not np.isnan(noise_power):
    #             if not (np.isnan(target_power) or np.isnan(noise_power)): # Check for NaNs
    #                 snr_scores[col] = target_power / noise_power

    #     selected_cols = sorted(snr_scores.items(), key=lambda x: x[1], reverse=True)
    #     selected_cols = [col for col, _ in selected_cols[:Config.TOP_SUBCARRIERS]]
    #     return selected_cols

    # def extract_breathing_rate(fft_df, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return None, []

    #     selected_cols = select_best_subcarriers(fft_df, freq_col, 
    #                                             Config.BREATHING_MIN_FREQ, 
    #                                             Config.BREATHING_MAX_FREQ)
    #     if not selected_cols:
    #         return None, []

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
    #     mask = (fft_df[freq_col] >= Config.BREATHING_MIN_FREQ) & (fft_df[freq_col] <= Config.BREATHING_MAX_FREQ)
        
    #     if not mask.any(): return None, selected_cols

    #     breathing_range = avg_spectrum[mask]
    #     breathing_freqs = fft_df[freq_col][mask]
        
    #     if len(breathing_range) == 0:
    #         return None, selected_cols

    #     peaks, _ = find_peaks(breathing_range, prominence=Config.PEAK_PROMINENCE)
        
    #     if len(peaks) == 0:
    #         return None, selected_cols

    #     peak_freqs = breathing_freqs.iloc[peaks]
    #     peak_heights = breathing_range.iloc[peaks]
    #     dominant_peak_idx = peak_heights.argmax()
    #     breathing_freq = peak_freqs.iloc[dominant_peak_idx]
    #     breathing_rate = breathing_freq * 60
        
    #     return breathing_rate, selected_cols

    # def extract_heart_rate(fft_df, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return None, []

    #     selected_cols = select_best_subcarriers(fft_df, freq_col,
    #                                             Config.HEART_MIN_FREQ,
    #                                             Config.HEART_MAX_FREQ)
    #     if not selected_cols:
    #         return None, []

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
    #     mask = (fft_df[freq_col] >= Config.HEART_MIN_FREQ) & (fft_df[freq_col] <= Config.HEART_MAX_FREQ)

    #     if not mask.any(): return None, selected_cols
    #     heart_range = avg_spectrum[mask]
    #     heart_freqs = fft_df[freq_col][mask]
        
    #     if len(heart_range) == 0:
    #         return None, selected_cols

    #     peaks, _ = find_peaks(heart_range, prominence=Config.HEART_PEAK_PROMINENCE)
        
    #     if len(peaks) == 0:
    #         return None, selected_cols

    #     peak_freqs = heart_freqs.iloc[peaks]
    #     peak_heights = heart_range.iloc[peaks]
    #     dominant_peak_idx = peak_heights.argmax()
    #     heart_freq = peak_freqs.iloc[dominant_peak_idx]
    #     heart_rate = heart_freq * 60
        
    #     return heart_rate, selected_cols

    # def plot_breathing_spectrum(fft_df, breathing_rate, selected_cols, output_path, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns or not selected_cols:
    #         return

    #     avg_spectrum = fft_df[selected_cols].mean(axis=1)
        
    #     threshold = np.max(avg_spectrum) * 0.01
    #     significant_mask = avg_spectrum > threshold
    #     if significant_mask.any():
    #         cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #     else:
    #         cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
        
    #     mask = fft_df[freq_col] <= cutoff_freq
        
    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
    #     plt.plot(fft_df[freq_col][mask], avg_spectrum[mask], 
    #             color=Config.PLOT_COLORS[0], 
    #             linewidth=Config.PLOT_LINE_WIDTH)
        
    #     breathing_mask = (fft_df[freq_col][mask] >= Config.BREATHING_MIN_FREQ) & (fft_df[freq_col][mask] <= Config.BREATHING_MAX_FREQ)
    #     plt.axvspan(Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ, 
    #                 alpha=0.2, color='green', label='Breathing Range')
        
    #     if breathing_rate is not None:
    #         breathing_freq = breathing_rate / 60
    #         plt.axvline(x=breathing_freq, color='red', linestyle='--',
    #                 label=f'Breathing Rate: {breathing_rate:.1f} bpm')
        
    #     plt.xlabel('Frequency (Hz)')
    #     plt.ylabel('Magnitude')
    #     plt.title('FFT Spectrum with Breathing Rate')
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.legend()
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def plot_vital_signs_spectrum(fft_df, breathing_rate, heart_rate, breathing_cols, heart_cols, output_path, freq_col='frequency'):
    #     if fft_df is None or fft_df.empty or freq_col not in fft_df.columns:
    #         return

    #     plt.figure(figsize=Config.PLOT_FIGSIZE)
        
    #     # Calculate cutoff frequency based on significant values
    #     if breathing_cols and all(col in fft_df.columns for col in breathing_cols):
    #         breathing_spectrum = fft_df[breathing_cols].mean(axis=1)
    #         if not np.all(np.abs(np.diff(breathing_spectrum)) <= 1e-10):
    #             threshold = np.max(breathing_spectrum) * 0.01
    #             significant_mask = breathing_spectrum > threshold
    #             if significant_mask.any():
    #                 cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #             else:
    #                 cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
                
    #             mask = fft_df[freq_col] <= cutoff_freq
    #             plt.plot(fft_df[freq_col][mask], breathing_spectrum[mask], 
    #                     color='green', alpha=0.5, label='Breathing Spectrum')
        
    #     if heart_cols and all(col in fft_df.columns for col in heart_cols):
    #         heart_spectrum = fft_df[heart_cols].mean(axis=1)
    #         if not np.all(np.abs(np.diff(heart_spectrum)) <= 1e-10):
    #             threshold = np.max(heart_spectrum) * 0.01
    #             significant_mask = heart_spectrum > threshold
    #             if significant_mask.any():
    #                 cutoff_freq = fft_df[freq_col][significant_mask].iloc[-1]
    #             else:
    #                 cutoff_freq = fft_df[freq_col].iloc[-1] if not fft_df[freq_col].empty else 0
                
    #             mask = fft_df[freq_col] <= cutoff_freq
    #             plt.plot(fft_df[freq_col][mask], heart_spectrum[mask], 
    #                     color='red', alpha=0.5, label='Heart Rate Spectrum')
        
    #     # Only show ranges if there is non-constant data
    #     if (breathing_cols and not np.all(np.abs(np.diff(fft_df[breathing_cols].mean(axis=1))) <= 1e-10)) or \
    #     (heart_cols and not np.all(np.abs(np.diff(fft_df[heart_cols].mean(axis=1))) <= 1e-10)):
    #         plt.axvspan(Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ, 
    #                     alpha=0.2, color='green', label='Breathing Range')
    #         plt.axvspan(Config.HEART_MIN_FREQ, Config.HEART_MAX_FREQ, 
    #                     alpha=0.2, color='red', label='Heart Rate Range')
        
    #     if breathing_rate is not None:
    #         breathing_freq = breathing_rate / 60
    #         plt.axvline(x=breathing_freq, color='green', linestyle='--', label=f'Breathing Rate: {breathing_rate:.1f} bpm')
        
    #     if heart_rate is not None:
    #         heart_freq = heart_rate / 60
    #         plt.axvline(x=heart_freq, color='red', linestyle='--', label=f'Heart Rate: {heart_rate:.1f} bpm')
        
    #     plt.xlabel('Frequency (Hz)')
    #     plt.ylabel('Magnitude')
    #     plt.title('FFT Spectrum with Vital Signs')
    #     plt.grid(True, alpha=Config.PLOT_GRID_ALPHA)
    #     plt.legend()
    #     plt.tight_layout()
    #     plt.savefig(output_path, dpi=300, bbox_inches='tight')
    #     plt.close()

    # def compute_subcarrier_changes(current_df, baseline_df):
    #     """
    #     現在のCSIデータとベースラインCSIデータを比較し、変化の大きいサブキャリアを特定
    #     フーリエ変換後の周波数領域での変化を比較
        
    #     Args:
    #         current_df: 現在のCSIデータのDataFrame
    #         baseline_df: ベースラインCSIデータのDataFrame
        
    #     Returns:
    #         list: 変化の大きいサブキャリアのリスト
    #     """
    #     if current_df is None or baseline_df is None or current_df.empty or baseline_df.empty:
    #         return []
        
    #     # サブキャリア列を取得
    #     subcarrier_cols = [col for col in current_df.columns if col.lstrip('-').isdigit()]
        
    #     # 各サブキャリアのフーリエ変換を計算
    #     current_fft = apply_fourier_transform(current_df, Config.DOWNSAMPLE_INTERVAL_S)
    #     baseline_fft = apply_fourier_transform(baseline_df, Config.DOWNSAMPLE_INTERVAL_S)
        
    #     if current_fft is None or baseline_fft is None or current_fft.empty or baseline_fft.empty:
    #         return []
        
    #     # 呼吸と心拍の周波数帯域を定義
    #     breathing_range = (Config.BREATHING_MIN_FREQ, Config.BREATHING_MAX_FREQ)
    #     heart_range = (Config.HEART_MIN_FREQ, Config.HEART_MAX_FREQ)
        
    #     # 各サブキャリアの変化量を計算
    #     changes = {}
    #     for col in subcarrier_cols:
    #         if col in current_fft.columns and col in baseline_fft.columns:
    #             # 呼吸周波数帯域での変化
    #             breathing_mask = (current_fft['frequency'] >= breathing_range[0]) & \
    #                         (current_fft['frequency'] <= breathing_range[1])
    #             breathing_current = current_fft.loc[breathing_mask, col]
    #             breathing_baseline = baseline_fft.loc[breathing_mask, col]
                
    #             # 心拍周波数帯域での変化
    #             heart_mask = (current_fft['frequency'] >= heart_range[0]) & \
    #                         (current_fft['frequency'] <= heart_range[1])
    #             heart_current = current_fft.loc[heart_mask, col]
    #             heart_baseline = baseline_fft.loc[heart_mask, col]
                
    #             # 各周波数帯域での変化量を計算
    #             breathing_change = np.mean(np.abs(breathing_current - breathing_baseline))
    #             heart_change = np.mean(np.abs(heart_current - heart_baseline))
                
    #             # ベースラインの振幅で正規化
    #             breathing_baseline_amp = np.mean(np.abs(breathing_baseline))
    #             heart_baseline_amp = np.mean(np.abs(heart_baseline))
                
    #             if breathing_baseline_amp > 0 and heart_baseline_amp > 0:
    #                 normalized_breathing_change = breathing_change / breathing_baseline_amp
    #                 normalized_heart_change = heart_change / heart_baseline_amp
                    
    #                 # 呼吸と心拍の変化を重み付けして合計
    #                 total_change = (normalized_breathing_change * 0.6 + normalized_heart_change * 0.4)
    #                 changes[col] = total_change
        
    #     # 変化量でソートし、上位のサブキャリアを選択
    #     sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=True)
    #     selected_subcarriers = [col for col, _ in sorted_changes[:Config.TOP_SUBCARRIERS]]
        
    #     return selected_subcarriers

    # def load_latest_baseline_data(baseline_dir):
    #     """
    #     ベースCSIデータのウィンドウを読み込む関数
        
    #     Args:
    #         baseline_dir (str): ベースCSIデータのディレクトリ
        
    #     Returns:
    #         list: ベースCSIデータのウィンドウのリスト
    #     """
    #     if not os.path.exists(baseline_dir):
    #         raise FileNotFoundError(f"ベースCSIデータディレクトリが見つかりません: {baseline_dir}")
        
    #     # ウィンドウファイルを読み込む
    #     window_files = sorted([f for f in os.listdir(baseline_dir) if f.startswith('window_') and f.endswith('.csv')])
    #     if not window_files:
    #         raise FileNotFoundError(f"ベースCSIデータのウィンドウファイルが見つかりません: {baseline_dir}")
        
    #     baseline_windows = []
    #     for window_file in window_files:
    #         window_path = os.path.join(baseline_dir, window_file)
    #         try:
    #             df = pd.read_csv(window_path)
    #             baseline_windows.append(df)
    #         except Exception as e:
    #             print(f"警告: ウィンドウファイルの読み込みに失敗しました {window_file}: {e}")
    #             continue
        
    #     return baseline_windows

    # def process_pipeline(df, output_dir, input_base, baseline_dir=None):
    #     """
    #     CSIデータの処理パイプライン
        
    #     Args:
    #         df (pd.DataFrame): 処理するCSIデータ
    #         output_dir (str): 出力ディレクトリ
    #         input_base (str): 入力ファイルのベース名
    #         baseline_dir (str, optional): ベースCSIデータのディレクトリ
    #     """
    #     try:
    #         # 初期データの保存
    #         save_initial_data(df, output_dir, input_base)
            
    #         # データの前処理
    #         df = drop_invalid_rows(df)
    #         if df.empty:
    #             raise ValueError("有効なデータがありません")
            
    #         # サブキャリアの正規化
    #         subcarrier_cols = [col for col in df.columns if col.lstrip('-').isdigit()]
    #         for col in subcarrier_cols:
    #             df[col] = normalize_signal(df[col])
            
    #         # バンドパスフィルタの適用
    #         fs = 1.0 / Config.DOWNSAMPLE_INTERVAL_S
    #         df = bandpass_filter_csv(df, Config.BANDPASS_LOWCUT, Config.BANDPASS_HIGHCUT, fs)
            
    #         # フーリエ変換の適用
    #         fft_df = apply_fourier_transform(df, Config.DOWNSAMPLE_INTERVAL_S)
            
    #         # 呼吸数と心拍数の抽出
    #         breathing_rate = extract_breathing_rate(fft_df)
    #         heart_rate = extract_heart_rate(fft_df)
            
    #         # 最適なサブキャリアの選択
    #         breathing_cols = select_best_subcarriers(fft_df, 
    #                                             freq_min=Config.BREATHING_MIN_FREQ,
    #                                             freq_max=Config.BREATHING_MAX_FREQ)
    #         heart_cols = select_best_subcarriers(fft_df,
    #                                         freq_min=Config.HEART_MIN_FREQ,
    #                                         freq_max=Config.HEART_MAX_FREQ)
            
    #         # ベースCSIデータとの比較
    #         if baseline_dir:
    #             try:
    #                 baseline_windows = load_latest_baseline_data(baseline_dir)
    #                 if baseline_windows:
    #                     # 各ベースウィンドウとの類似度を計算
    #                     similarities = []
    #                     for baseline_df in baseline_windows:
    #                         similarity = compute_cosine_similarity(
    #                             df[breathing_cols].values,
    #                             baseline_df[breathing_cols].values
    #                         )
    #                         similarities.append(similarity)
                        
    #                     # 類似度の平均を計算
    #                     avg_similarity = np.mean(similarities)
    #                     print(f"ベースCSIデータとの平均類似度: {avg_similarity:.3f}")
                        
    #                     # 類似度が低い場合は警告
    #                     if avg_similarity < 0.7:
    #                         print("警告: ベースCSIデータとの類似度が低いです")
    #             except Exception as e:
    #                 print(f"警告: ベースCSIデータとの比較に失敗しました: {e}")
            
    #         # 結果のプロット
    #         plot_breathing_spectrum(fft_df, breathing_rate, breathing_cols, 
    #                             os.path.join(output_dir, f"{os.path.basename(input_base)}_breathing.png"))
    #         plot_vital_signs_spectrum(fft_df, breathing_rate, heart_rate,
    #                                 breathing_cols, heart_cols,
    #                                 os.path.join(output_dir, f"{os.path.basename(input_base)}_vital_signs.png"))
            
    #         # 結果の保存
    #         results = {
    #             'breathing_rate': breathing_rate,
    #             'heart_rate': heart_rate,
    #             'breathing_subcarriers': breathing_cols,
    #             'heart_subcarriers': heart_cols
    #         }
            
    #         if baseline_dir and 'avg_similarity' in locals():
    #             results['baseline_similarity'] = avg_similarity
            
    #         # 結果をJSONファイルとして保存
    #         import json
    #         results_file = os.path.join(output_dir, f"{os.path.basename(input_base)}_results.json")
    #         with open(results_file, 'w') as f:
    #             json.dump(results, f, indent=4)
            
    #         print(f"解析結果を保存しました: {results_file}")
            
    #     except Exception as e:
    #         print(f"エラー: データ処理中にエラーが発生しました: {e}")
    #         raise

# サービスインスタンス
pcap_analyzer = PCAPAnalyzer()