"""
ZKP証明生成サービス

CSI呼吸解析結果からZero-Knowledge Proofを生成するサービス

使用回路: csi_full_similarity.circom (NormalBreathingCheck)
  - 秘密入力: referenceMatrix[31][245], candidateMatrix[31][245]
  - 公開出力: [isNormal, selectedSubcarrierIndex]
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.zkp_circuit_service import ZKPCircuitService

logger = logging.getLogger(__name__)


class ZKPService(ZKPCircuitService):
    """csi_full_similarity 専用 ZKP 証明生成サービス。

    ZKPCircuitService を継承し、csi_full_similarity 回路固有の処理
    （Python側コサイン類似度計算、サブキャリアランキング）を追加する。
    """

    # 回路パラメータ（csi_full_similarity.circom の component main 宣言と同期）
    ZKP_FREQ_START = 0.0       # Hz
    ZKP_FREQ_STEP  = 0.02      # Hz
    ZKP_NORMAL_LOW_BIN  = 5    # 0.10Hz
    ZKP_NORMAL_HIGH_BIN = 25   # 0.50Hz

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(
            circuit_name="csi_full_similarity",
            zkp_dir=zkp_dir,
            auto_compile=auto_compile,
        )

    # ------------------------------------------------------------------ #
    # 証明生成（override）
    # ------------------------------------------------------------------ #

    async def generate_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = ZKPCircuitService.DEFAULT_SCALE,
    ) -> Dict[str, Any]:
        """ZKP証明を生成し、csi_full_similarity 固有の表示メタデータを追加する。

        Returns:
            {
                "proof": Groth16証明オブジェクト,
                "publicSignals": [isNormal, selectedSubcarrierIndex],
                "isNormal": bool,
                "selectedSubcarrierIndex": int (Python計算),
                "normalizedSimilarity": float (Python計算),
                "similarity": float (normalizedSimilarity の別名),
                "isValid": bool,
                "method": "full_similarity",
            }
        """
        result = await super().generate_proof(reference_matrix, candidate_matrix, scale)

        public_signals = result.get("publicSignals", [])
        selected_sub_index = int(public_signals[1]) if len(public_signals) >= 2 else None

        # 表示用メタデータ: 全体コサイン類似度（Python計算 — ZKP公開出力ではない）
        python_sim = await asyncio.to_thread(
            self.compute_python_similarity, reference_matrix, candidate_matrix
        )
        normalized_similarity = python_sim.get("cosine_similarity", 0.0)

        result["selectedSubcarrierIndex"] = selected_sub_index
        result["normalizedSimilarity"] = normalized_similarity
        result["similarity"] = normalized_similarity

        logger.info(
            "ZKP proof completed: isNormal=%s, selectedSubcarrier=%s, similarity=%.4f",
            result.get("isNormal"),
            selected_sub_index,
            normalized_similarity,
        )

        return result

    # ------------------------------------------------------------------ #
    # Python側計算（表示・デバッグ用 — ZKP証明の公開出力ではない）
    # ------------------------------------------------------------------ #

    def compute_python_similarity(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = 10000,
    ) -> Dict[str, Any]:
        """全体コサイン類似度をPythonで計算する（表示・精度検証用）。

        ZKP回路と同じリサイズ処理を適用した上で計算する。
        この値はZKP証明の公開出力ではなく、あくまで表示用の参考値。
        """
        input_data = self._prepare_input(reference_matrix, candidate_matrix)

        ref  = np.array(input_data["referenceMatrix"], dtype=np.float64).flatten()
        cand = np.array(input_data["candidateMatrix"],  dtype=np.float64).flatten()

        dot_product = float(np.dot(ref, cand))
        norm_ref    = float(np.linalg.norm(ref))
        norm_cand   = float(np.linalg.norm(cand))

        cosine = 0.0 if (norm_ref == 0 or norm_cand == 0) else dot_product / (norm_ref * norm_cand)

        return {
            "cosine_similarity": cosine,
            "dot_product": dot_product,
            "norm_ref": norm_ref,
            "norm_cand": norm_cand,
            "vector_length": ref.size,
        }

    def select_lowest_subcarrier(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
    ) -> Dict[str, Any]:
        """サブキャリア単位でコサイン類似度を計算し、最も低いサブキャリアを返す（表示用）。"""
        result = self.select_top_n_subcarriers(reference_matrix, candidate_matrix, top_n=1)
        return {
            "lowest_index":      result["lowest_index"],
            "lowest_similarity": result["lowest_similarity"],
            "similarities":      result["all_similarities"],
        }

    def select_top_n_subcarriers(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """サブキャリア単位でコサイン類似度を計算し、類似度が最も低いN個を返す（表示用）。"""
        actual_cols = len(reference_matrix[0]) if reference_matrix else self.EXPECTED_SUBCARRIERS

        input_data = self._prepare_input(reference_matrix, candidate_matrix)

        ref  = np.array(input_data["referenceMatrix"], dtype=np.float64)
        cand = np.array(input_data["candidateMatrix"],  dtype=np.float64)

        ref  = ref[:,  :actual_cols]
        cand = cand[:, :actual_cols]

        similarities = self._per_subcarrier_cosine(ref, cand)

        sorted_pairs  = sorted(enumerate(similarities), key=lambda x: x[1])
        top_n_items   = sorted_pairs[:min(top_n, len(sorted_pairs))]
        top_n_indices = [i   for i, _ in top_n_items]
        top_n_sims    = [sim for _, sim in top_n_items]

        return {
            "top_n_indices":      top_n_indices,
            "top_n_similarities": top_n_sims,
            "all_similarities":   similarities,
            "lowest_index":       top_n_indices[0] if top_n_indices else 0,
            "lowest_similarity":  top_n_sims[0]    if top_n_sims    else 0.0,
            "num_subcarriers":    len(similarities),
        }

    def extract_top_n_from_similarities(
        self,
        zkp_similarities: List[int],
        scale: int = 10000,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """ZKP回路出力の全サブキャリア類似度から下位N個を抽出する。"""
        normalized = [s / (scale * scale) for s in zkp_similarities]

        sorted_pairs  = sorted(enumerate(normalized), key=lambda x: x[1])
        top_n_items   = sorted_pairs[:min(top_n, len(sorted_pairs))]
        top_n_indices = [i   for i, _ in top_n_items]
        top_n_sims    = [sim for _, sim in top_n_items]

        return {
            "top_n_indices":      top_n_indices,
            "top_n_similarities": top_n_sims,
            "lowest_index":       top_n_indices[0] if top_n_indices else 0,
            "lowest_similarity":  top_n_sims[0]    if top_n_sims    else 0.0,
            "num_subcarriers":    len(zkp_similarities),
        }

    # ------------------------------------------------------------------ #
    # プライベートヘルパー
    # ------------------------------------------------------------------ #

    @staticmethod
    def _per_subcarrier_cosine(
        ref: "np.ndarray",
        cand: "np.ndarray",
    ) -> List[float]:
        """サブキャリアごとにコサイン類似度を計算する内部ヘルパー。"""
        num_subcarriers = ref.shape[1]
        similarities: List[float] = []

        for sc in range(num_subcarriers):
            ref_vec  = ref[:,  sc]
            cand_vec = cand[:, sc]
            dot      = float(np.dot(ref_vec, cand_vec))
            n_ref    = float(np.linalg.norm(ref_vec))
            n_cand   = float(np.linalg.norm(cand_vec))
            cosine   = 0.0 if (n_ref == 0 or n_cand == 0) else dot / (n_ref * n_cand)
            similarities.append(cosine)

        return similarities
