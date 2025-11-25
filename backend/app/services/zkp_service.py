"""
ZKP証明生成サービス

CSI呼吸解析結果からZero-Knowledge Proofを生成するサービス
"""

import asyncio
import json
import os
import subprocess
import tempfile
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

import numpy as np

logger = logging.getLogger(__name__)


class ZKPService:
    """ZKP証明生成サービス"""

    def __init__(self, zkp_dir: Optional[str] = None):
        """
        初期化

        Args:
            zkp_dir: zkpディレクトリのパス（デフォルトはプロジェクトルート/zkp）
        """
        if zkp_dir is None:
            # デフォルトはプロジェクトルートから相対パス
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent.parent
            zkp_dir = project_root / "zkp"

        self.zkp_dir = Path(zkp_dir)
        self.build_dir = self.zkp_dir / "build"
        self.keys_dir = self.zkp_dir / "keys"

        # 必要なファイルの存在チェック
        self._check_setup()

    def _check_setup(self) -> None:
        """ZKP環境のセットアップが完了しているか確認"""
        wasm_file = self.build_dir / "breathing_verifier_js" / "breathing_verifier.wasm"
        zkey_file = self.keys_dir / "breathing_verifier.zkey"

        if not wasm_file.exists():
            raise FileNotFoundError(
                f"WASM file not found: {wasm_file}. Please run 'npm run compile' in zkp directory."
            )

        if not zkey_file.exists():
            raise FileNotFoundError(
                f"zKey file not found: {zkey_file}. Please run 'npm run setup' in zkp directory."
            )

    def _calculate_poseidon_commitment(
        self, csi_data: List[int], salt: int
    ) -> str:
        """
        PoseidonハッシュによるCSIデータのコミットメント計算

        Note: 実際の実装では circomlibjs を使用してPoseidonハッシュを計算する必要があります。
        現在はプレースホルダーとしてSHA256を使用しています。

        Args:
            csi_data: CSI振幅データ（64サンプル）
            salt: ソルト値

        Returns:
            コミットメント値（文字列）
        """
        # TODO: circomlibjs の poseidon を使用した実装に置き換える
        # 現在はSHA256でシミュレート
        data_str = ",".join(map(str, csi_data)) + f",{salt}"
        hash_obj = hashlib.sha256(data_str.encode())
        return str(int.from_bytes(hash_obj.digest()[:8], byteorder='big'))

    def _prepare_circuit_input(
        self,
        csi_data: np.ndarray,
        breathing_rate: float,
        breathing_frequency: float,
        confidence_score: float,
        timestamp: datetime,
        salt: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        回路入力データの準備

        Args:
            csi_data: CSI振幅時系列データ
            breathing_rate: 呼吸数（回/分）
            breathing_frequency: 呼吸周波数（Hz）
            confidence_score: 信頼度スコア（0.0-1.0）
            timestamp: タイムスタンプ
            salt: ソルト値（Noneの場合はランダム生成）

        Returns:
            回路入力データ
        """
        # CSIデータを64サンプルに調整（パディングまたは切り捨て）
        if len(csi_data) < 64:
            # 不足分をゼロパディング
            padded_data = np.pad(csi_data, (0, 64 - len(csi_data)), mode='constant')
        else:
            # 64サンプルに切り捨て
            padded_data = csi_data[:64]

        # 整数化（振幅値を整数スケールに変換）
        csi_data_int = [int(x) for x in padded_data]

        # ソルトの生成
        if salt is None:
            salt = int.from_bytes(os.urandom(4), byteorder='big')

        # コミットメント計算
        commitment = self._calculate_poseidon_commitment(csi_data_int, salt)

        # 回路入力データの構築
        input_data = {
            # 公開入力
            "csiCommitment": commitment,
            "breathingRate": int(breathing_rate),
            "confidenceScore": int(confidence_score * 100),  # 0-100スケール
            "timestamp": int(timestamp.timestamp()),
            # 秘密入力
            "csiData": csi_data_int,
            "breathingFrequency": int(breathing_frequency * 1000),  # 1000倍整数化
            "salt": salt,
        }

        return input_data

    async def _run_node_script(
        self, script_name: str, input_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Node.jsスクリプトの実行

        Args:
            script_name: スクリプト名（compile, prove, verify）
            input_data: 入力データ（proveの場合に使用）

        Returns:
            実行結果
        """
        script_path = self.zkp_dir / "scripts" / f"{script_name}.js"

        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")

        # 一時ディレクトリで実行
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # 入力データをファイルに保存（proveの場合）
            if input_data and script_name == "prove":
                input_file = self.build_dir / "input.json"
                with open(input_file, "w") as f:
                    json.dump(input_data, f, indent=2)

            # スクリプト実行
            cmd = ["node", str(script_path)]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(self.zkp_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode()
                    logger.error(f"Node script failed: {error_msg}")
                    raise RuntimeError(f"Script execution failed: {error_msg}")

                logger.info(f"Script {script_name} executed successfully")
                return {"stdout": stdout.decode(), "stderr": stderr.decode()}

            except Exception as e:
                logger.error(f"Failed to run node script: {e}")
                raise

    async def generate_proof(
        self,
        csi_data: np.ndarray,
        breathing_rate: float,
        breathing_frequency: float,
        confidence_score: float,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        ZKP証明の生成

        Args:
            csi_data: CSI振幅時系列データ
            breathing_rate: 呼吸数（回/分）
            breathing_frequency: 呼吸周波数（Hz）
            confidence_score: 信頼度スコア（0.0-1.0）
            timestamp: タイムスタンプ（Noneの場合は現在時刻）

        Returns:
            証明データ
            {
                "proof": {...},
                "publicSignals": [...],
                "commitment": "...",
                "metadata": {...}
            }
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        logger.info(f"Generating ZKP for breathing rate: {breathing_rate} bpm")

        try:
            # 1. 回路入力データの準備
            input_data = self._prepare_circuit_input(
                csi_data=csi_data,
                breathing_rate=breathing_rate,
                breathing_frequency=breathing_frequency,
                confidence_score=confidence_score,
                timestamp=timestamp,
            )

            # 2. Witnessの計算
            logger.info("Calculating witness...")
            wasm_file = (
                self.build_dir / "breathing_verifier_js" / "breathing_verifier.wasm"
            )
            input_file = self.build_dir / "input.json"
            witness_file = self.build_dir / "witness.wtns"

            # 入力データを保存
            with open(input_file, "w") as f:
                json.dump(input_data, f)

            # snarkjs witness計算
            witness_cmd = [
                "snarkjs",
                "wtns",
                "calculate",
                str(wasm_file),
                str(input_file),
                str(witness_file),
            ]

            process = await asyncio.create_subprocess_exec(
                *witness_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode != 0:
                raise RuntimeError("Witness calculation failed")

            # 3. 証明の生成
            logger.info("Generating proof...")
            zkey_file = self.keys_dir / "breathing_verifier.zkey"
            proof_file = self.build_dir / "proof.json"
            public_file = self.build_dir / "public.json"

            prove_cmd = [
                "snarkjs",
                "groth16",
                "prove",
                str(zkey_file),
                str(witness_file),
                str(proof_file),
                str(public_file),
            ]

            process = await asyncio.create_subprocess_exec(
                *prove_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode != 0:
                raise RuntimeError("Proof generation failed")

            # 4. 証明データの読み込み
            with open(proof_file, "r") as f:
                proof = json.load(f)

            with open(public_file, "r") as f:
                public_signals = json.load(f)

            logger.info("ZKP generation completed successfully")

            return {
                "proof": proof,
                "publicSignals": public_signals,
                "commitment": input_data["csiCommitment"],
                "metadata": {
                    "breathingRate": breathing_rate,
                    "confidenceScore": confidence_score,
                    "timestamp": timestamp.isoformat(),
                    "protocol": "Groth16",
                    "curve": "bn128",
                },
            }

        except Exception as e:
            logger.error(f"ZKP generation failed: {e}")
            raise

    async def verify_proof(
        self, proof: Dict, public_signals: List[str]
    ) -> bool:
        """
        証明の検証

        Args:
            proof: 証明データ
            public_signals: 公開入力

        Returns:
            検証結果（True: 有効, False: 無効）
        """
        logger.info("Verifying ZKP...")

        try:
            vkey_file = self.keys_dir / "breathing_verifier_verification_key.json"
            proof_file = self.build_dir / "verify_proof.json"
            public_file = self.build_dir / "verify_public.json"

            # 証明データを一時ファイルに保存
            with open(proof_file, "w") as f:
                json.dump(proof, f)

            with open(public_file, "w") as f:
                json.dump(public_signals, f)

            # snarkjs verify実行
            verify_cmd = [
                "snarkjs",
                "groth16",
                "verify",
                str(vkey_file),
                str(public_file),
                str(proof_file),
            ]

            process = await asyncio.create_subprocess_exec(
                *verify_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            # 出力から検証結果を判定
            is_valid = b"OK" in stdout

            logger.info(f"ZKP verification result: {'VALID' if is_valid else 'INVALID'}")

            return is_valid

        except Exception as e:
            logger.error(f"ZKP verification failed: {e}")
            return False

    # ========== コサイン類似度計算用ZKPメソッド ==========

    async def generate_cosine_similarity_proof(
        self,
        reference_vector: List[int],
        candidate_vectors: List[List[int]],
        scale: int = 10000
    ) -> Dict[str, Any]:
        """
        コサイン類似度のZKP証明を生成（本番環境用）

        本番環境では、全てのコサイン類似度計算をこの関数で実行します。
        JavaScript/Python実装の代わりにこの関数を使用します。

        Args:
            reference_vector: 参照ベクトル（Pythagorean triple近似済み）[4次元]
            candidate_vectors: 候補ベクトルリスト（最大2個）[各4次元]
            scale: 固定小数点スケール（デフォルト: 10000）

        Returns:
            {
                "proof": ZKP証明オブジェクト,
                "publicSignals": 公開信号リスト,
                "bestIndex": 最適サブキャリアインデックス,
                "bestSimilarity": 最大類似度（整数値）,
                "normalizedSimilarity": 正規化された類似度（0.0-1.0）
            }

        Raises:
            ValueError: 入力データが不正な場合
            RuntimeError: ZKP証明生成に失敗した場合
        """
        try:
            # 入力検証
            if len(candidate_vectors) > 2:
                raise ValueError("Maximum 2 candidate vectors supported")

            if len(reference_vector) != 4:
                raise ValueError("Reference vector must have 4 dimensions")

            for i, cand in enumerate(candidate_vectors):
                if len(cand) != 4:
                    raise ValueError(f"Candidate vector {i} must have 4 dimensions")

            logger.info(f"Generating cosine similarity ZKP for {len(candidate_vectors)} candidates")

            # 1. Witness生成用の入力データ準備
            input_data = self._prepare_cosine_similarity_input(
                reference_vector,
                candidate_vectors,
                scale
            )

            # 2. Witness生成
            witness_file = await self._generate_cosine_similarity_witness(input_data)

            # 3. ZKP証明生成
            proof, public_signals = await self._generate_cosine_similarity_groth16_proof(witness_file)

            # 4. 結果パース
            best_index = int(public_signals[0])
            best_similarity = int(public_signals[1])

            result = {
                "proof": proof,
                "publicSignals": public_signals,
                "bestIndex": best_index,
                "bestSimilarity": best_similarity,
                "normalizedSimilarity": best_similarity / scale
            }

            logger.info(
                f"Cosine similarity ZKP generated: "
                f"bestIndex={best_index}, similarity={best_similarity/scale:.4f}"
            )

            return result

        except Exception as e:
            logger.error(f"Cosine similarity ZKP generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Cosine similarity ZKP generation failed: {str(e)}")

    async def verify_cosine_similarity_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int]
    ) -> bool:
        """
        コサイン類似度ZKP証明を検証（本番環境用）

        Args:
            proof: ZKP証明オブジェクト
            public_signals: 公開信号リスト

        Returns:
            True: 検証成功, False: 検証失敗
        """
        temp_proof_file = None
        temp_public_file = None

        try:
            import uuid
            unique_id = uuid.uuid4().hex[:8]
            temp_proof_file = self.build_dir / f"csi_proof_{unique_id}.json"
            temp_public_file = self.build_dir / f"csi_public_{unique_id}.json"

            # 証明ファイルを一時保存
            with open(temp_proof_file, 'w') as f:
                json.dump(proof, f)

            with open(temp_public_file, 'w') as f:
                json.dump(public_signals, f)

            # snarkjs groth16 verify 実行
            verification_key = self.keys_dir / "csi_subcarrier_selector_verification_key.json"

            if not verification_key.exists():
                raise FileNotFoundError(
                    f"Verification key not found: {verification_key}. "
                    "Please run ZKP setup script first."
                )

            verify_cmd = [
                "snarkjs", "groth16", "verify",
                str(verification_key),
                str(temp_public_file),
                str(temp_proof_file)
            ]

            process = await asyncio.create_subprocess_exec(
                *verify_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Cosine similarity verification failed: {stderr.decode()}")
                return False

            # 検証結果パース
            is_valid = b"OK" in stdout

            logger.info(f"Cosine similarity ZKP verification: {'VALID' if is_valid else 'INVALID'}")
            return is_valid

        except Exception as e:
            logger.error(f"Cosine similarity ZKP verification failed: {e}", exc_info=True)
            return False
        finally:
            # 一時ファイル削除
            if temp_proof_file and temp_proof_file.exists():
                temp_proof_file.unlink()
            if temp_public_file and temp_public_file.exists():
                temp_public_file.unlink()

    def _prepare_cosine_similarity_input(
        self,
        reference: List[int],
        candidates: List[List[int]],
        scale: int
    ) -> Dict[str, Any]:
        """
        コサイン類似度Witness生成用の入力データを準備

        Args:
            reference: 参照ベクトル
            candidates: 候補ベクトルリスト
            scale: 固定小数点スケール

        Returns:
            ZKP回路への入力データ
        """
        # ノルム計算
        def calculate_norm(vec: List[int]) -> int:
            sum_squares = sum(x**2 for x in vec)
            return int(sum_squares ** 0.5)

        # 類似度計算
        def calculate_similarity(vec_a: List[int], vec_b: List[int]):
            """Returns: (similarity, norm_a, norm_b, dot_product)"""
            dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = calculate_norm(vec_a)
            norm_b = calculate_norm(vec_b)

            if norm_a == 0 or norm_b == 0:
                return 0, norm_a, norm_b, dot_product

            similarity = round((dot_product * scale) / (norm_a * norm_b))
            return similarity, norm_a, norm_b, dot_product

        # 各候補の類似度を計算
        ref_norm = calculate_norm(reference)
        candidate_data = []

        for i, cand in enumerate(candidates):
            sim, _, cand_norm, dot_prod = calculate_similarity(reference, cand)
            candidate_data.append({
                "vector": cand,
                "norm": cand_norm,
                "similarity": sim,
                "dotProduct": dot_prod
            })

        # 候補が1つの場合は2つ目をダミーで埋める（回路仕様に合わせる）
        while len(candidate_data) < 2:
            candidate_data.append({
                "vector": [0, 0, 0, 0],
                "norm": 0,
                "similarity": 0,
                "dotProduct": 0
            })

        # 入力データ構築
        input_data = {
            "reference": reference,
            "refNorm": ref_norm,
            "candidates": [c["vector"] for c in candidate_data],
            "candNorms": [c["norm"] for c in candidate_data],
            "similarities": [c["similarity"] for c in candidate_data],
            "dotProducts": [c["dotProduct"] for c in candidate_data]
        }

        return input_data

    async def _generate_cosine_similarity_witness(
        self, input_data: Dict[str, Any]
    ) -> Path:
        """
        コサイン類似度用Witness生成

        Args:
            input_data: 入力データ

        Returns:
            生成されたWitnessファイルのパス
        """
        circuit_name = "csi_subcarrier_selector"
        input_file = self.build_dir / "csi_input.json"
        witness_file = self.build_dir / f"{circuit_name}_js" / "witness.wtns"
        wasm_file = self.build_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm"
        generate_witness_script = self.build_dir / f"{circuit_name}_js" / "generate_witness.js"

        # ファイル存在確認
        if not wasm_file.exists():
            raise FileNotFoundError(
                f"WASM file not found: {wasm_file}. "
                "Please compile the CSI selector circuit first: npm run compile:csi_selector"
            )

        if not generate_witness_script.exists():
            raise FileNotFoundError(
                f"Witness generation script not found: {generate_witness_script}"
            )

        # 入力データ保存
        with open(input_file, 'w') as f:
            json.dump(input_data, f, indent=2)

        # Witness生成実行
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                str(generate_witness_script),
                str(wasm_file),
                str(input_file),
                str(witness_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Cosine similarity witness generation failed: {error_msg}")

            if not witness_file.exists():
                raise RuntimeError("Witness file was not created")

            logger.info(f"Cosine similarity witness generated: {witness_file}")
            return witness_file

        except Exception as e:
            logger.error(f"Witness generation error: {e}")
            raise

    async def _generate_cosine_similarity_groth16_proof(
        self, witness_file: Path
    ):
        """
        コサイン類似度用ZKP証明生成

        Args:
            witness_file: Witnessファイルのパス

        Returns:
            (proof, public_signals)
        """
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        proof_file = self.build_dir / f"csi_proof_{unique_id}.json"
        public_file = self.build_dir / f"csi_public_{unique_id}.json"
        zkey_file = self.keys_dir / "csi_subcarrier_selector_final.zkey"

        # zkeyファイル存在確認
        if not zkey_file.exists():
            raise FileNotFoundError(
                f"zkey file not found: {zkey_file}. "
                "Please run ZKP setup script first: npm run setup:csi_selector"
            )

        try:
            # snarkjs groth16 prove 実行
            prove_cmd = [
                "snarkjs", "groth16", "prove",
                str(zkey_file),
                str(witness_file),
                str(proof_file),
                str(public_file)
            ]

            process = await asyncio.create_subprocess_exec(
                *prove_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Cosine similarity proof generation failed: {error_msg}")

            # 証明と公開信号を読み込み
            with open(proof_file) as f:
                proof = json.load(f)

            with open(public_file) as f:
                public_signals = json.load(f)

            logger.info("Cosine similarity ZKP proof generated successfully")
            return proof, public_signals

        except Exception as e:
            logger.error(f"Proof generation error: {e}")
            raise
        finally:
            # 一時ファイルは保持（デバッグ用・監査用）
            pass
