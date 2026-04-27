"""
PCAPAnalyzer の ZKP 向け補助処理。
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.pcap_analyzer_common import _empty_extracted_vectors, _interval_midpoint


def extract_full_subcarrier_vectors(
    self,
    fft_df: pd.DataFrame,
    freq_col: str = "frequency",
    use_binned: bool = False,
    freq_min: Optional[float] = None,
    freq_max: Optional[float] = None,
) -> Dict[str, Any]:
    """呼吸周波数帯域の全サブキャリア行列を抽出する。"""
    if fft_df is None or fft_df.empty:
        self.logger.warning("FFT DataFrameが空です")
        return _empty_extracted_vectors()

    df = fft_df.copy()
    lower = freq_min if freq_min is not None else self.BREATHING_MIN_FREQ
    upper = freq_max if freq_max is not None else self.BREATHING_MAX_FREQ

    if use_binned and "freq_interval" in df.columns:
        df["freq_mid"] = df["freq_interval"].apply(_interval_midpoint).astype(float)
        freq_mask = (df["freq_mid"] >= lower) & (df["freq_mid"] <= upper)
        freq_values = df.loc[freq_mask, "freq_mid"].values
    else:
        freq_mask = (df[freq_col] >= lower) & (df[freq_col] <= upper)
        freq_values = df.loc[freq_mask, freq_col].values

    breathing_df = df[freq_mask]
    if breathing_df.empty:
        if "freq_mid" in df.columns:
            freq_range = f"{df['freq_mid'].min():.4f} - {df['freq_mid'].max():.4f} Hz"
        elif freq_col in df.columns:
            freq_range = f"{df[freq_col].min():.4f} - {df[freq_col].max():.4f} Hz"
        else:
            freq_range = "不明"

        self.logger.warning(
            f"呼吸周波数帯域({self.BREATHING_MIN_FREQ}-{self.BREATHING_MAX_FREQ}Hz)にデータがありません。"
            f"データの周波数範囲: {freq_range}"
        )
        return _empty_extracted_vectors()

    subcarrier_cols = [
        col for col in breathing_df.columns
        if col not in [freq_col, "freq_interval", "freq_mid"]
        and pd.api.types.is_numeric_dtype(breathing_df[col])
    ]
    if not subcarrier_cols:
        self.logger.warning("サブキャリア列が見つかりません")
        return _empty_extracted_vectors()

    csi_matrix = []
    for _, row in breathing_df.iterrows():
        freq_point_data = []
        for col in subcarrier_cols:
            amplitude = row[col]
            if not np.isfinite(amplitude):
                amplitude = 0.0
            freq_point_data.append(max(0, int(amplitude * self.ZKP_SCALE)))
        csi_matrix.append(freq_point_data)

    frequencies = [int(freq * self.ZKP_SCALE) for freq in freq_values]
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
        "num_subcarriers": num_subcarriers,
    }


def prepare_zkp_vectors_from_fft(
    self,
    fft_df: pd.DataFrame,
) -> Tuple[list[list[int]], list[list[int]]]:
    """
    既存互換のための ZKP 入力準備ラッパー。

    現行実装では単一 FFT DataFrame しか受け取らないため、
    自己比較用に同一行列を参照・候補の両方へ返す。
    """
    extracted = self.extract_full_subcarrier_vectors(
        fft_df,
        freq_col="freq_interval",
        use_binned=True,
        freq_min=self.ZKP_FREQ_START,
        freq_max=self.ZKP_FREQ_END,
    )
    matrix = extracted["csi_matrix"]
    return matrix, matrix


async def analyze_and_generate_zkp(
    self,
    file_path: str,
    zkp_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """PCAP 解析後に ZKP 証明生成まで行う互換ヘルパー。"""
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
            "error": "FFT analysis failed",
        }

    reference_matrix, candidate_matrix = self.prepare_zkp_vectors_from_fft(fft_df)

    if zkp_service is None:

        from app.services.zkp_service import ZKPService

        zkp_service = ZKPService()

    try:
        if hasattr(zkp_service, "generate_cosine_similarity_proof"):
            zkp_result = await zkp_service.generate_cosine_similarity_proof(
                reference_vector=reference_matrix,
                candidate_vectors=candidate_matrix,
                scale=self.ZKP_SCALE,
            )
            best_index = zkp_result.get("bestIndex")
        else:
            zkp_result = await zkp_service.generate_proof(
                reference_matrix=reference_matrix,
                candidate_matrix=candidate_matrix,
                scale=self.ZKP_SCALE,
            )
            best_index = zkp_result.get("selectedSubcarrierIndex")

        self.logger.info(
            f"ZKP証明生成完了: "
            f"bestIndex={best_index}, "
            f"similarity={zkp_result.get('normalizedSimilarity', 0.0):.4f}"
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
            "best_index": best_index,
            "best_similarity": zkp_result.get("normalizedSimilarity"),
            "reference_vector": reference_matrix,
            "candidate_vectors": candidate_matrix,
        }
    except Exception as exc:
        self.logger.error(f"ZKP証明生成に失敗: {exc}", exc_info=True)
        return {
            "fft_dataframe": fft_df,
            "wavelet_dataframe": analysis_result["wavelet"],
            "music_dataframe": analysis_result["music"],
            "breathing_rate_fft_bpm": analysis_result["breathing_rate_fft_bpm"],
            "breathing_rate_wavelet_bpm": analysis_result["breathing_rate_wavelet_bpm"],
            "breathing_rate_music_bpm": analysis_result["breathing_rate_music_bpm"],
            "breathing_rate_comparison": analysis_result["breathing_rate_comparison"],
            "zkp_proof": None,
            "error": str(exc),
        }


def extract_matrix_for_zkp(
    self,
    df: pd.DataFrame,
) -> List[List[int]]:
    """FFT・ウェーブレット用ZKP入力行列を抽出する。

    binned DataFrame（freq_interval列付き）から ZKP_FREQ_START～ZKP_FREQ_END の
    周波数帯域を抽出し、ZKP_SCALE倍の整数行列を返す。
    """
    extracted = self.extract_full_subcarrier_vectors(
        df,
        freq_col="freq_interval",
        use_binned=True,
        freq_min=self.ZKP_FREQ_START,
        freq_max=self.ZKP_FREQ_END,
    )
    return extracted["csi_matrix"]


def extract_music_matrix_for_zkp(
    self,
    music_df: pd.DataFrame,
) -> List[List[int]]:
    """MUSIC擬似スペクトルをZKP入力行列に変換する。

    処理フロー:
      1. ZKP_FREQ_START～ZKP_FREQ_END の行を抽出
      2. log10圧縮: log10(1 + x)
      3. サブキャリア単位 min-max 正規化 → [0, 1]
      4. × ZKP_SCALE → 整数化
    """
    if music_df is None or music_df.empty:
        return []

    df = music_df.copy()
    if "freq_interval" in df.columns:
        df["_freq_mid"] = df["freq_interval"].apply(_interval_midpoint).astype(float)
        freq_mask = (df["_freq_mid"] >= self.ZKP_FREQ_START) & (df["_freq_mid"] <= self.ZKP_FREQ_END)
    elif "frequency" in df.columns:
        freq_mask = (df["frequency"] >= self.ZKP_FREQ_START) & (df["frequency"] <= self.ZKP_FREQ_END)
    else:
        return []

    sub_df = df[freq_mask]
    if sub_df.empty:
        return []

    subcarrier_cols = [
        col for col in sub_df.columns
        if col not in {"frequency", "freq_interval", "_freq_mid"}
        and pd.api.types.is_numeric_dtype(sub_df[col])
    ]
    if not subcarrier_cols:
        return []

    matrix = sub_df[subcarrier_cols].to_numpy(dtype=np.float64)
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    # log10圧縮
    matrix = np.log10(1.0 + np.maximum(matrix, 0.0))

    # サブキャリア単位 min-max 正規化
    col_min = matrix.min(axis=0)
    col_max = matrix.max(axis=0)
    col_range = np.where(col_max - col_min == 0.0, 1.0, col_max - col_min)
    matrix = (matrix - col_min) / col_range

    result = []
    for row in matrix:
        result.append([int(v * self.ZKP_SCALE) for v in row])

    return result
