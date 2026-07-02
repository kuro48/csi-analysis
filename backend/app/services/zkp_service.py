"""
ZKP証明生成サービス

CSI呼吸解析結果からZero-Knowledge Proofを生成するサービス

使用回路: csi_full_similarity.circom (NormalBreathingCheck)
  - 秘密入力: referenceMatrix[31][245], candidateMatrix[31][245]
  - 公開出力: [isNormal, selectedSubcarrierIndex]
"""

import asyncio
import logging
import secrets
import subprocess
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
    ZKP_FREQ_START = 0.15      # Hz
    ZKP_FREQ_STEP  = 0.01      # Hz
    ZKP_NORMAL_LOW_BIN  = 0    # 0.15Hz
    ZKP_NORMAL_HIGH_BIN = 35   # 0.505Hz ≈ 0.50Hz

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(
            circuit_name="csi_full_similarity",
            zkp_dir=zkp_dir,
            auto_compile=auto_compile,
        )

    # ------------------------------------------------------------------ #
    # セットアップ                                                          #
    # ------------------------------------------------------------------ #

    def _get_circuit_hash(self) -> str:
        """回路ファイルのMD5ハッシュを返す（WASM/zkey との整合性確認用）。"""
        import hashlib
        circuit_file = self.zkp_dir / "circuits" / "csi_full_similarity.circom"
        if not circuit_file.exists():
            return ""
        with open(circuit_file, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _check_setup(self) -> None:
        """ZKP環境のセットアップが完了しているか確認（自動コンパイル対応）。

        回路ファイルのハッシュを使って WASM/zkey の鮮度を検証し、
        回路が変更されていれば古い zkey を削除してTrusted Setupのみ再実行する。
        """
        circuit_name  = "csi_full_similarity"
        full_sim_wasm = self.build_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm"
        full_sim_zkey = self.keys_dir / f"{circuit_name}_final.zkey"
        hash_file     = self.keys_dir / f"{circuit_name}_circuit_hash.txt"

        has_files     = full_sim_wasm.exists() and full_sim_zkey.exists()
        current_hash  = self._get_circuit_hash()
        stored_hash   = hash_file.read_text().strip() if hash_file.exists() else ""
        hash_ok       = bool(current_hash) and current_hash == stored_hash

        if has_files and hash_ok:
            logger.info("Full Similarity ZKP circuit is ready")
            return

        # ハッシュファイルが存在しないが zkey は有効: ハッシュファイルを再生成して終了
        # （ハッシュファイルを削除しただけで zkey 自体は最新の場合）
        if has_files and not hash_file.exists() and current_hash:
            hash_file.write_text(current_hash)
            logger.info("Full Similarity ZKP circuit is ready (hash file regenerated)")
            return

        if not self.auto_compile:
            logger.warning(
                "ZKP circuit files not found or outdated. Please run:\n"
                "  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
            )
            return

        # ハッシュが不一致（回路ソース変更）の場合のみ古い zkey を削除して再実行
        if has_files and not hash_ok:
            logger.warning(
                "Circuit source has changed since the zkey was generated. "
                "Deleting stale zkeys and re-running Trusted Setup..."
            )
            for stale in self.keys_dir.glob(f"{circuit_name}*.zkey"):
                stale.unlink(missing_ok=True)
        else:
            logger.warning("ZKP circuit files not found. Starting auto-compilation...")

        try:
            self._auto_compile_circuits()
            if current_hash:
                hash_file.write_text(current_hash)
        except Exception as e:
            logger.error(f"Auto-compilation failed: {e}")
            logger.warning(
                "ZKP circuits not available. Please manually run:\n"
                "  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
            )

    def _auto_compile_circuits(self) -> None:
        """ZKP回路の自動コンパイルとセットアップ。

        - WASM が存在しない場合: circom コンパイル → Trusted Setup
        - WASM が存在するが zkey が存在しない場合: Trusted Setup のみ（再コンパイルをスキップ）
        - 両方存在する場合: スキップ
        """
        circuit_name = "csi_full_similarity"
        circuit_file = self.zkp_dir / "circuits" / f"{circuit_name}.circom"

        node_modules = self.zkp_dir / "node_modules"
        if not node_modules.exists():
            logger.info("Installing npm packages...")
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"npm install failed: {result.stderr}")

        wasm_file = self.build_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm"
        zkey_file = self.keys_dir / f"{circuit_name}_final.zkey"

        if wasm_file.exists() and zkey_file.exists():
            logger.info("Circuit already compiled and zkey exists, skipping...")
            return

        if not wasm_file.exists():
            # WASM が無い → circom でフルコンパイル
            if not circuit_file.exists():
                raise RuntimeError(f"Circuit file not found: {circuit_file}")

            logger.warning("Compiling circuit (this may take several minutes)...")
            compile_cmd = [
                "circom",
                str(circuit_file),
                "--r1cs",
                "--wasm",
                "--sym",
                "--c",
                "-o", str(self.build_dir),
                "-l", str(self.zkp_dir / "node_modules")
            ]

            result = subprocess.run(
                compile_cmd,
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(f"Circuit compilation failed: {result.stderr}")

            logger.info("Circuit compilation completed")
        else:
            # WASM は最新だが zkey が古い/存在しない → Trusted Setup のみ
            logger.warning(
                "WASM exists but zkey is missing or stale. "
                "Running Trusted Setup only (skipping circuit compilation)..."
            )

        self._run_trusted_setup(circuit_name, "Full Similarity")

    def _run_trusted_setup(self, circuit_name: str, display_name: str) -> None:
        """
        Trusted Setup（Groth16 Setup + Contribute + Verification Key Export）

        Args:
            circuit_name: 回路名（例: csi_full_similarity）
            display_name: ログ用表示名
        """
        logger.warning(f"Starting Trusted Setup for {display_name} (this may take 10-60 minutes)...")

        # csi_full_similarity は 626K constraints → ptau20 (2^20=1048576) が必要
        ptau_file = self.keys_dir / "powersOfTau28_hez_final_20.ptau"
        if not ptau_file.exists():
            logger.info("Downloading Powers of Tau 2^20 file...")
            ptau_url = "https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_20.ptau"
            import urllib.request
            try:
                urllib.request.urlretrieve(ptau_url, str(ptau_file))
                logger.info("Powers of Tau file downloaded successfully")
            except Exception as e:
                raise RuntimeError(f"Failed to download Powers of Tau file: {e}")

        r1cs_file = self.build_dir / f"{circuit_name}.r1cs"
        zkey_0     = self.keys_dir / f"{circuit_name}_0000.zkey"
        zkey_final = self.keys_dir / f"{circuit_name}_final.zkey"
        vkey_file  = self.keys_dir / f"{circuit_name}_verification_key.json"

        logger.info(f"Running groth16 setup for {display_name}...")
        result = subprocess.run(
            ["snarkjs", "groth16", "setup", str(r1cs_file), str(ptau_file), str(zkey_0)],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Groth16 setup failed: {result.stderr}")

        logger.info(f"Running zkey contribution for {display_name}...")
        result = subprocess.run(
            ["snarkjs", "zkey", "contribute", str(zkey_0), str(zkey_final),
             "--name=Auto-generated contribution", "-v"],
            cwd=str(self.zkp_dir),
            input=secrets.token_hex(32) + "\n",
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"zkey contribution failed: {result.stderr}")

        logger.info(f"Exporting verification key for {display_name}...")
        result = subprocess.run(
            ["snarkjs", "zkey", "export", "verificationkey", str(zkey_final), str(vkey_file)],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Verification key export failed: {result.stderr}")

        logger.info(f"Trusted Setup completed for {display_name}")
        logger.info(f"  WASM: {self.build_dir}/{circuit_name}_js/{circuit_name}.wasm")
        logger.info(f"  zkey: {zkey_final}")
        logger.info(f"  vkey: {vkey_file}")

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
