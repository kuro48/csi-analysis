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

    def extract_full_subcarrier_vectors(
        self,
        fft_df: pd.DataFrame,
        freq_col: str = 'frequency',
        use_binned: bool = False
    ) -> Dict[str, Any]:
        """
        全サブキャリアの呼吸周波数帯域データを抽出（生データのまま）

        呼吸周波数帯域（0.15～0.4Hz）の全周波数ポイント × 全サブキャリアの
        データをそのまま返します（平均化なし）。

        Args:
            fft_df: FFT結果のDataFrame
            freq_col: 周波数列名（'frequency' または 'freq_interval'）
            use_binned: ビン平均化後のDataFrameを使用する場合True

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
            freq_mask = (
                (df['freq_mid'] >= self.BREATHING_MIN_FREQ) &
                (df['freq_mid'] <= self.BREATHING_MAX_FREQ)
            )
            freq_values = df.loc[freq_mask, 'freq_mid'].values
        else:
            # frequency列を使用
            freq_mask = (
                (df[freq_col] >= self.BREATHING_MIN_FREQ) &
                (df[freq_col] <= self.BREATHING_MAX_FREQ)
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

# サービスインスタンス
pcap_analyzer = PCAPAnalyzer()