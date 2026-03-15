"""
ZKP証明生成サービス

CSI呼吸解析結果からZero-Knowledge Proofを生成するサービス

使用回路: csi_full_similarity.circom (NormalBreathingCheck)
  - 秘密入力: referenceMatrix[31][245], candidateMatrix[31][245]
  - 公開出力: isNormal (0 or 1)
"""

import asyncio
import json
import os
import subprocess
import tempfile
import uuid
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ZKPService:
    """ZKP証明生成サービス"""

    # 回路パラメータ（csi_full_similarity.circom の component main 宣言と同期）
    EXPECTED_FREQ_POINTS = 31   # 0.00~0.60Hz, 0.02Hz刻み
    EXPECTED_SUBCARRIERS = 245
    ZKP_FREQ_START = 0.0        # Hz
    ZKP_FREQ_STEP  = 0.02       # Hz
    ZKP_NORMAL_LOW_BIN  = 5     # 0.10Hz
    ZKP_NORMAL_HIGH_BIN = 25    # 0.50Hz
    DEFAULT_SCALE = 100

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True):
        """
        初期化

        Args:
            zkp_dir: zkpディレクトリのパス（デフォルトはプロジェクトルート/zkp）
            auto_compile: 自動コンパイルを有効にするか（デフォルト: True）
        """
        if zkp_dir is None:
            zkp_dir_env = os.getenv("ZKP_DIR")
            if zkp_dir_env:
                zkp_dir = zkp_dir_env
            else:
                # Docker環境では /zkp にマウントされている
                docker_zkp = Path("/zkp")
                if docker_zkp.exists():
                    zkp_dir = docker_zkp
                else:
                    # ローカル環境: backend/app/services -> backend -> project_root
                    current_file = Path(__file__)
                    project_root = current_file.parent.parent.parent.parent
                    zkp_dir = project_root / "zkp"

        self.zkp_dir = Path(zkp_dir)
        self.circuits_dir = self.zkp_dir
        self.build_dir = self.zkp_dir / "build"
        self.keys_dir = self.zkp_dir / "keys"
        self.auto_compile = auto_compile
        self.temp_dir = Path(tempfile.gettempdir())

        # 出力ディレクトリを先に用意
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.mkdir(parents=True, exist_ok=True)

        self._check_setup()

    # ------------------------------------------------------------------ #
    # セットアップ                                                          #
    # ------------------------------------------------------------------ #

    def _check_setup(self) -> None:
        """ZKP環境のセットアップが完了しているか確認（自動コンパイル対応）"""
        full_sim_wasm = self.build_dir / "csi_full_similarity_js" / "csi_full_similarity.wasm"
        full_sim_zkey = self.keys_dir / "csi_full_similarity_final.zkey"

        has_full_similarity = full_sim_wasm.exists() and full_sim_zkey.exists()

        if not has_full_similarity:
            if self.auto_compile:
                logger.warning("ZKP circuit files not found. Starting auto-compilation...")
                try:
                    self._auto_compile_circuits()
                except Exception as e:
                    logger.error(f"Auto-compilation failed: {e}")
                    logger.warning(
                        "ZKP circuits not available. Please manually run:\n"
                        "  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                    )
                    return
            else:
                logger.warning(
                    "ZKP circuit files not found. Please run:\n"
                    "  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                )
                return

        if has_full_similarity:
            logger.info("Full Similarity ZKP circuit is ready")

    def _auto_compile_circuits(self) -> None:
        """ZKP回路の自動コンパイルとセットアップ"""
        circuit_name = "csi_full_similarity"
        circuit_file = self.zkp_dir / "circuits" / f"{circuit_name}.circom"

        logger.warning("Starting automatic compilation of ZKP circuits. This may take a long time...")

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
            logger.info("Circuit already compiled, skipping...")
            return

        if not circuit_file.exists():
            raise RuntimeError(f"Circuit file not found: {circuit_file}")

        logger.info("Compiling circuit (this may take several minutes)...")
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
        self._run_trusted_setup(circuit_name, "Full Similarity")

    def _run_trusted_setup(self, circuit_name: str, display_name: str) -> None:
        """
        Trusted Setup（Groth16 Setup + Contribute + Verification Key Export）

        Args:
            circuit_name: 回路名（例: csi_full_similarity）
            display_name: ログ用表示名
        """
        logger.warning(f"Starting Trusted Setup for {display_name} (this may take 10-60 minutes)...")

        ptau_file = self.keys_dir / "powersOfTau28_hez_final_19.ptau"
        if not ptau_file.exists():
            logger.info("Downloading Powers of Tau 2^19 file...")
            ptau_url = "https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_19.ptau"
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
            input="random_entropy_12345\n",
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
    # 証明生成・検証                                                        #
    # ------------------------------------------------------------------ #

    async def generate_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = DEFAULT_SCALE
    ) -> Dict[str, Any]:
        """
        ZKP証明を生成する。

        回路 csi_full_similarity が入力行列を秘密入力として受け取り、
        isNormal（呼吸が正常域か）を公開出力として証明する。

        Args:
            reference_matrix: 参照CSIデータ [周波数ポイント][サブキャリア]
            candidate_matrix: 候補CSIデータ [周波数ポイント][サブキャリア]
            scale: 表示用類似度計算のスケール（ZKP回路には影響しない）

        Returns:
            {
                "proof": Groth16証明オブジェクト,
                "publicSignals": [isNormal],
                "isNormal": bool,
                "selectedSubcarrierIndex": 表示用サブキャリアインデックス（Python計算）,
                "normalizedSimilarity": 表示用類似度（Python計算）,
                "isValid": bool,
            }

        Raises:
            FileNotFoundError: ZKP回路ファイルが存在しない場合
            ValueError: 入力行列が不正な場合
            RuntimeError: 証明生成に失敗した場合
        """
        import time

        try:
            logger.info("=" * 80)
            logger.info("🚀 Starting ZKP Proof Generation")
            logger.info("=" * 80)
            total_start_time = time.time()

            full_sim_wasm = self.build_dir / "csi_full_similarity_js" / "csi_full_similarity.wasm"
            full_sim_zkey = self.keys_dir / "csi_full_similarity_final.zkey"

            if not full_sim_wasm.exists() or not full_sim_zkey.exists():
                raise FileNotFoundError(
                    f"ZKP circuit files not found.\n"
                    f"WASM: {full_sim_wasm} (exists: {full_sim_wasm.exists()})\n"
                    f"zkey: {full_sim_zkey} (exists: {full_sim_zkey.exists()})\n"
                    f"Please run: cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                )

            if not reference_matrix or not candidate_matrix:
                raise ValueError("Reference and candidate matrices cannot be empty")

            if len(reference_matrix) != len(candidate_matrix):
                raise ValueError("Reference and candidate must have same number of frequency points")

            if len(reference_matrix[0]) != len(candidate_matrix[0]):
                raise ValueError("Reference and candidate must have same number of subcarriers")

            logger.info(
                f"Generating ZKP proof: "
                f"{len(reference_matrix)} freq points × {len(reference_matrix[0])} subcarriers (before resize)"
            )

            input_data = self._prepare_input(reference_matrix, candidate_matrix)
            witness_file = await self._generate_witness(input_data)
            proof, public_signals = await self._generate_groth16_proof(witness_file)

            # public_signals = [isNormal] の1値のみ
            actual_len = len(public_signals)
            logger.info(f"Public signals length: actual={actual_len}, expected=1 (isNormal only)")

            is_normal = bool(int(public_signals[0])) if actual_len >= 1 else False

            # 表示用メタデータ: ZKP証明の外でPython計算（プライバシーに影響しない）
            per_sub = self.select_lowest_subcarrier(
                reference_matrix=reference_matrix,
                candidate_matrix=candidate_matrix
            )
            selected_sub_index = per_sub.get("lowest_index")
            normalized_similarity = per_sub.get("lowest_similarity", 0.0)

            result = {
                "proof": proof,
                "publicSignals": public_signals,
                "isNormal": is_normal,
                # 以下は表示用（ZKP証明の公開出力ではなくPython計算値）
                "selectedSubcarrierIndex": selected_sub_index,
                "normalizedSimilarity": normalized_similarity,
                "similarity": normalized_similarity,
                "isValid": is_normal,
            }

            total_time = time.time() - total_start_time
            logger.info("=" * 80)
            logger.info(f"✅ ZKP Proof Generation COMPLETED in {total_time:.3f} seconds")
            logger.info(f"   Is Normal (ZKP public output): {is_normal}")
            logger.info(f"   Selected Subcarrier (display): {selected_sub_index}")
            logger.info(f"   Similarity (display): {normalized_similarity:.4f}")
            logger.info("=" * 80)

            return result

        except Exception as e:
            logger.error(f"ZKP proof generation failed: {e}", exc_info=True)
            raise RuntimeError(f"ZKP proof generation failed: {str(e)}")

    async def verify_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int]
    ) -> bool:
        """
        ZKP証明を検証する。

        Args:
            proof: ZKP証明データ
            public_signals: 公開信号

        Returns:
            検証結果（True: 有効, False: 無効）

        Raises:
            RuntimeError: 検証処理に失敗した場合
        """
        import time

        try:
            vkey_path = str(self.keys_dir / "csi_full_similarity_verification_key.json")

            if not os.path.exists(vkey_path):
                raise FileNotFoundError(f"Verification key not found: {vkey_path}")

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as proof_file:
                json.dump(proof, proof_file)
                proof_path = proof_file.name

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as public_file:
                json.dump(public_signals, public_file)
                public_path = public_file.name

            try:
                cmd = ["npx", "snarkjs", "groth16", "verify", vkey_path, public_path, proof_path]

                logger.info("⏱️ Starting proof verification...")
                start_time = time.time()

                result = subprocess.run(
                    cmd,
                    cwd=self.zkp_dir,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                verification_time = time.time() - start_time
                logger.info(f"Verification output: {result.stdout}")

                if result.returncode != 0:
                    logger.error(f"Verification failed: {result.stderr}")
                    return False

                is_valid = "OK" in result.stdout

                if is_valid:
                    logger.info(f"✅ Proof verification PASSED in {verification_time:.3f} seconds")
                else:
                    logger.warning(f"❌ Proof verification FAILED in {verification_time:.3f} seconds")

                return is_valid

            finally:
                if os.path.exists(proof_path):
                    os.unlink(proof_path)
                if os.path.exists(public_path):
                    os.unlink(public_path)

        except Exception as e:
            logger.error(f"Proof verification failed: {e}", exc_info=True)
            raise RuntimeError(f"Proof verification failed: {str(e)}")

    # ------------------------------------------------------------------ #
    # Python側計算（表示・デバッグ用 — ZKP証明の公開出力ではない）           #
    # ------------------------------------------------------------------ #

    def compute_python_similarity(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = 10000
    ) -> Dict[str, Any]:
        """
        全体コサイン類似度をPythonで計算する（表示・精度検証用）。

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
            "vector_length": ref.size
        }

    def select_lowest_subcarrier(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]]
    ) -> Dict[str, Any]:
        """
        サブキャリア単位でコサイン類似度を計算し、最も低いサブキャリアを返す（表示用）。
        """
        input_data = self._prepare_input(reference_matrix, candidate_matrix)

        ref  = np.array(input_data["referenceMatrix"], dtype=np.float64)
        cand = np.array(input_data["candidateMatrix"],  dtype=np.float64)

        similarities = self._per_subcarrier_cosine(ref, cand)

        lowest_similarity = min(similarities)
        lowest_index      = similarities.index(lowest_similarity)

        return {
            "lowest_index":      lowest_index,
            "lowest_similarity": lowest_similarity,
            "similarities":      similarities
        }

    def select_top_n_subcarriers(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        サブキャリア単位でコサイン類似度を計算し、類似度が最も低いN個を返す（表示用）。

        Args:
            reference_matrix: 参照CSIマトリックス
            candidate_matrix: 候補CSIマトリックス
            top_n: 返すサブキャリア数

        Returns:
            top_n_indices, top_n_similarities, all_similarities,
            lowest_index, lowest_similarity, num_subcarriers
        """
        input_data = self._prepare_input(reference_matrix, candidate_matrix)

        ref  = np.array(input_data["referenceMatrix"], dtype=np.float64)
        cand = np.array(input_data["candidateMatrix"],  dtype=np.float64)

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
            "num_subcarriers":    len(similarities)
        }

    def extract_top_n_from_similarities(
        self,
        zkp_similarities: List[int],
        scale: int = 10000,
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        ZKP回路出力の全サブキャリア類似度から下位N個を抽出する。

        Args:
            zkp_similarities: ZKP回路が計算した類似度配列（スケール済み整数値）
            scale: 固定小数点スケール
            top_n: 返すサブキャリア数

        Returns:
            top_n_indices, top_n_similarities, lowest_index, lowest_similarity, num_subcarriers
        """
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
            "num_subcarriers":    len(zkp_similarities)
        }

    # ------------------------------------------------------------------ #
    # プライベートヘルパー                                                   #
    # ------------------------------------------------------------------ #

    def _prepare_input(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]]
    ) -> Dict[str, Any]:
        """
        Witness生成用の入力データを準備する（回路の期待サイズにリサイズ）。

        Args:
            reference_matrix: 参照CSIデータ [周波数ポイント][サブキャリア]
            candidate_matrix: 候補CSIデータ [周波数ポイント][サブキャリア]

        Returns:
            {"referenceMatrix": [[int, ...], ...], "candidateMatrix": [[int, ...], ...]}
        """
        def resize_matrix(matrix: List[List[int]], target_rows: int, target_cols: int) -> List[List[int]]:
            resized = []
            for i in range(target_rows):
                if i < len(matrix):
                    row = matrix[i][:target_cols]
                    row.extend([0] * (target_cols - len(row)))
                else:
                    row = [0] * target_cols
                resized.append(row)
            return resized

        ref_rows  = len(reference_matrix)
        ref_cols  = len(reference_matrix[0]) if reference_matrix else 0
        cand_rows = len(candidate_matrix)
        cand_cols = len(candidate_matrix[0]) if candidate_matrix else 0

        logger.info(
            f"Input matrix sizes - Reference: {ref_rows}×{ref_cols}, "
            f"Candidate: {cand_rows}×{cand_cols}, "
            f"Expected: {self.EXPECTED_FREQ_POINTS}×{self.EXPECTED_SUBCARRIERS}"
        )

        reference_matrix = resize_matrix(reference_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS)
        candidate_matrix = resize_matrix(candidate_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS)

        return {
            "referenceMatrix": reference_matrix,
            "candidateMatrix": candidate_matrix
        }

    async def _generate_witness(
        self,
        input_data: Dict[str, Any]
    ) -> str:
        """
        snarkjs を使って Witness ファイルを生成する。

        Args:
            input_data: {"referenceMatrix": ..., "candidateMatrix": ...}

        Returns:
            生成された Witness ファイルのパス（文字列）

        Raises:
            RuntimeError: Witness 生成に失敗した場合
        """
        import time

        try:
            input_file   = self.temp_dir / f"csi_input_{uuid.uuid4()}.json"
            witness_file = self.temp_dir / f"csi_witness_{uuid.uuid4()}.wtns"
            wasm_file    = self.circuits_dir / "build" / "csi_full_similarity_js" / "csi_full_similarity.wasm"

            if not wasm_file.exists():
                raise RuntimeError(f"WASM file not found: {wasm_file}")

            with open(input_file, 'w') as f:
                json.dump(input_data, f)

            cmd = [
                "node",
                "--experimental-wasm-modules",
                "node_modules/.bin/snarkjs",
                "wtns", "calculate",
                str(wasm_file),
                str(input_file),
                str(witness_file)
            ]

            logger.info("⏱️ Starting witness generation...")
            start_time = time.time()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.circuits_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            witness_time = time.time() - start_time

            if proc.returncode != 0:
                stdout_msg = stdout.decode() if stdout else ""
                stderr_msg = stderr.decode() if stderr else ""
                error_msg  = f"stdout: {stdout_msg}\nstderr: {stderr_msg}" if (stdout_msg or stderr_msg) else "Unknown error"
                raise RuntimeError(f"Witness generation failed: {error_msg}")

            logger.info(f"✅ Witness generated in {witness_time:.3f} seconds: {witness_file}")
            return str(witness_file)

        except Exception as e:
            logger.error(f"Witness generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Witness generation failed: {str(e)}")

    async def _generate_groth16_proof(
        self,
        witness_file: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        snarkjs groth16 prove で Groth16 証明を生成する。

        Args:
            witness_file: Witness ファイルのパス

        Returns:
            (proof, publicSignals)

        Raises:
            RuntimeError: 証明生成に失敗した場合
        """
        import time

        try:
            zkey_file   = self.circuits_dir / "keys" / "csi_full_similarity_final.zkey"
            proof_file  = self.temp_dir / f"csi_proof_{uuid.uuid4()}.json"
            public_file = self.temp_dir / f"csi_public_{uuid.uuid4()}.json"

            if not zkey_file.exists():
                raise RuntimeError(
                    f"zkey file not found: {zkey_file}\n"
                    f"Please run: cd zkp && npm run setup:full_similarity"
                )

            cmd = [
                "node",
                "node_modules/.bin/snarkjs",
                "groth16", "prove",
                str(zkey_file),
                witness_file,
                str(proof_file),
                str(public_file)
            ]

            logger.info("⏱️ Starting proof generation...")
            start_time = time.time()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.circuits_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            generation_time = time.time() - start_time

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Proof generation failed: {error_msg}")

            with open(proof_file,  'r') as f:
                proof = json.load(f)
            with open(public_file, 'r') as f:
                public_signals = json.load(f)

            logger.info(f"✅ Groth16 proof generated in {generation_time:.3f} seconds")
            return proof, public_signals

        except Exception as e:
            logger.error(f"Groth16 proof generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Proof generation failed: {str(e)}")

    @staticmethod
    def _per_subcarrier_cosine(
        ref: "np.ndarray",
        cand: "np.ndarray"
    ) -> List[float]:
        """
        サブキャリアごとにコサイン類似度を計算する内部ヘルパー。

        Args:
            ref:  参照行列 ndarray [freq_points × subcarriers]
            cand: 候補行列 ndarray [freq_points × subcarriers]

        Returns:
            各サブキャリアのコサイン類似度リスト
        """
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
