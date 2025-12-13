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
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging

import numpy as np

logger = logging.getLogger(__name__)


class ZKPService:
    """ZKP証明生成サービス"""

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True):
        """
        初期化

        Args:
            zkp_dir: zkpディレクトリのパス（デフォルトはプロジェクトルート/zkp）
            auto_compile: 自動コンパイルを有効にするか（デフォルト: True）
        """
        if zkp_dir is None:
            # 環境変数から取得、なければデフォルト
            zkp_dir_env = os.getenv("ZKP_DIR")
            if zkp_dir_env:
                zkp_dir = zkp_dir_env
            else:
                # Docker環境では /zkp にマウントされている
                # ローカル環境ではプロジェクトルート/zkp
                docker_zkp = Path("/zkp")
                if docker_zkp.exists():
                    zkp_dir = docker_zkp
                else:
                    # ローカル環境: backend/app/services -> backend -> project_root
                    current_file = Path(__file__)
                    project_root = current_file.parent.parent.parent.parent
                    zkp_dir = project_root / "zkp"

        self.zkp_dir = Path(zkp_dir)
        self.circuits_dir = self.zkp_dir  # circuits_dir エイリアス
        self.build_dir = self.zkp_dir / "build"
        self.keys_dir = self.zkp_dir / "keys"
        self.auto_compile = auto_compile
        self.temp_dir = Path(tempfile.gettempdir())

        # 出力ディレクトリを先に用意（初回のcircom/snarkjs実行で "invalid output path" を避ける）
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.mkdir(parents=True, exist_ok=True)

        # 必要なファイルの存在チェック（自動コンパイルあり）
        self._check_setup()

    def _check_setup(self) -> None:
        """ZKP環境のセットアップが完了しているか確認（自動コンパイル対応）"""
        # 全サブキャリア類似度回路のチェック
        full_sim_wasm = self.build_dir / "csi_full_similarity_js" / "csi_full_similarity.wasm"
        full_sim_zkey = self.keys_dir / "csi_full_similarity_final.zkey"

        # 呼吸検証回路のチェック
        breathing_wasm = self.build_dir / "breathing_verifier_js" / "breathing_verifier.wasm"
        breathing_zkey = self.keys_dir / "breathing_verifier.zkey"

        # 少なくとも1つの回路が利用可能かチェック
        has_full_similarity = full_sim_wasm.exists() and full_sim_zkey.exists()
        has_breathing_verifier = breathing_wasm.exists() and breathing_zkey.exists()

        if not has_full_similarity and not has_breathing_verifier:
            if self.auto_compile:
                logger.warning("ZKP circuit files not found. Starting auto-compilation...")
                try:
                    self._auto_compile_circuits()
                except Exception as e:
                    logger.error(f"Auto-compilation failed: {e}")
                    logger.warning(
                        f"ZKP circuits not available. Please manually run:\n"
                        f"  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                    )
                    # エラーを投げずに警告のみ
                    return
            else:
                logger.warning(
                    f"ZKP circuit files not found. Please run:\n"
                    f"  cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                )
                # エラーを投げずに警告のみ
                return

        if has_full_similarity:
            logger.info("Full Similarity ZKP circuit is ready")
        if has_breathing_verifier:
            logger.info("Breathing Verifier ZKP circuit is ready")

    def _auto_compile_circuits(self) -> None:
        """
        ZKP回路の自動コンパイルとセットアップ

        対象回路:
        - csi_full_similarity: 全サブキャリア類似度計算
        - breathing_verifier: 呼吸検証

        警告: この処理には10分〜60分かかる可能性があります
        """
        import subprocess
        import sys

        circuits_to_compile = [
            {
                "name": "csi_full_similarity",
                "circuit_file": "csi_full_similarity.circom",
                "display_name": "Full Similarity"
            },
            # {
            #     "name": "breathing_verifier",
            #     "circuit_file": "breathing_verifier.circom",
            #     "display_name": "Breathing Verifier"
            # }
        ]

        logger.warning("Starting automatic compilation of ZKP circuits. This may take a long time...")

        # 1. npmパッケージのインストール確認
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

        # 2. 各回路のコンパイル
        for circuit_info in circuits_to_compile:
            circuit_name = circuit_info["name"]
            circuit_file = self.zkp_dir / "circuits" / circuit_info["circuit_file"]

            # 既にコンパイル済みかチェック
            wasm_file = self.build_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm"
            zkey_file = self.keys_dir / f"{circuit_name}.zkey"

            if wasm_file.exists() and zkey_file.exists():
                logger.info(f"{circuit_info['display_name']} circuit already compiled, skipping...")
                continue

            if not circuit_file.exists():
                logger.warning(f"Circuit file not found: {circuit_file}, skipping...")
                continue

            logger.info(f"Compiling {circuit_info['display_name']} circuit (this may take several minutes)...")
            compile_cmd = [
                "circom",
                str(circuit_file),
                "--r1cs",
                "--wasm",
                "--sym",
                "--c",
                "-o", str(self.build_dir)
            ]

            result = subprocess.run(
                compile_cmd,
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"{circuit_info['display_name']} compilation failed: {result.stderr}")
                continue

            logger.info(f"{circuit_info['display_name']} circuit compilation completed")

            # 3. Trusted Setupを実行
            self._run_trusted_setup(circuit_name, circuit_info['display_name'])

        logger.info("All circuits compilation completed")

    def _run_trusted_setup(self, circuit_name: str, display_name: str) -> None:
        """
        特定回路のTrusted Setup実行

        Args:
            circuit_name: 回路名（例: csi_full_similarity）
            display_name: 表示用名前（例: Full Similarity）
        """
        import subprocess

        logger.warning(f"Starting Trusted Setup for {display_name} (this may take 10-60 minutes)...")

        # Powers of Tau ファイルの確認
        ptau_file = self.keys_dir / "powersOfTau28_hez_final_16.ptau"
        if not ptau_file.exists():
            logger.info("Downloading Powers of Tau 2^16 file...")
            ptau_url = "https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_16.ptau"
            import urllib.request
            try:
                urllib.request.urlretrieve(ptau_url, str(ptau_file))
                logger.info("Powers of Tau file downloaded successfully")
            except Exception as e:
                raise RuntimeError(f"Failed to download Powers of Tau file: {e}")

        r1cs_file = self.build_dir / f"{circuit_name}.r1cs"
        zkey_0 = self.keys_dir / f"{circuit_name}_0000.zkey"
        zkey_final = self.keys_dir / f"{circuit_name}_final.zkey"
        vkey_file = self.keys_dir / f"{circuit_name}_verification_key.json"

        # Setup
        logger.info(f"Running groth16 setup for {display_name}...")
        setup_cmd = [
            "snarkjs", "groth16", "setup",
            str(r1cs_file),
            str(ptau_file),
            str(zkey_0)
        ]

        result = subprocess.run(
            setup_cmd,
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Groth16 setup failed for {display_name}: {result.stderr}")

        # Contribute
        logger.info(f"Running zkey contribution for {display_name}...")
        contribute_cmd = [
            "snarkjs", "zkey", "contribute",
            str(zkey_0),
            str(zkey_final),
            "--name=Auto-generated contribution",
            "-v"
        ]

        # エントロピー入力を自動化
        result = subprocess.run(
            contribute_cmd,
            cwd=str(self.zkp_dir),
            input="random_entropy_12345\n",
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"zkey contribution failed for {display_name}: {result.stderr}")

        # Export verification key
        logger.info(f"Exporting verification key for {display_name}...")
        export_cmd = [
            "snarkjs", "zkey", "export", "verificationkey",
            str(zkey_final),
            str(vkey_file)
        ]

        result = subprocess.run(
            export_cmd,
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Verification key export failed for {display_name}: {result.stderr}")

        logger.info(f"Trusted Setup completed successfully for {display_name}")
        logger.info(f"  WASM: {self.build_dir / circuit_name}_js/{circuit_name}.wasm")
        logger.info(f"  zkey: {zkey_final}")
        logger.info(f"  vkey: {vkey_file}")

    def _calculate_poseidon_commitment(
        self, csi_data: List[int], salt: int
    ) -> str:
        """
        PoseidonハッシュによるCSIデータのコミットメント計算

        Args:
            csi_data: CSI振幅データ（64サンプル）
            salt: ソルト値

        Returns:
            コミットメント値（10進文字列）
        """
        return self._poseidon_hash(csi_data + [salt])

    def _poseidon_hash(self, inputs: List[int]) -> str:
        """
        circomlib の Poseidon 実装を Node.js 経由で呼び出してハッシュを計算

        Args:
            inputs: 整数配列

        Returns:
            Poseidonハッシュ（10進文字列）
        """
        script_path = self.zkp_dir / "scripts" / "poseidon_hash.js"
        if not script_path.exists():
            raise FileNotFoundError(f"Poseidon script not found: {script_path}")

        # 入力をJSONで一時ファイル化（BigInt安全のため文字列にして渡す）
        tmp_input = self.temp_dir / f"poseidon_input_{uuid.uuid4()}.json"
        with open(tmp_input, "w") as f:
            json.dump([str(v) for v in inputs], f)

        try:
            result = subprocess.run(
                ["node", str(script_path), str(tmp_input)],
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Poseidon hash failed: {result.stderr.strip() or result.stdout.strip()}"
                )

            output = result.stdout.strip()
            if not output:
                raise RuntimeError("Poseidon hash returned empty output")

            return output
        finally:
            if tmp_input.exists():
                tmp_input.unlink()

    def _prepare_circuit_input(
        self,
        breathing_rate: float,
        confidence_score: float,
    ) -> Dict[str, Any]:
        """
        回路入力データの準備（breathing_verifier.circom用）

        Args:
            breathing_rate: 呼吸数（回/分）
            confidence_score: 信頼度スコア（0.0-1.0）

        Returns:
            回路入力データ
        """
        # 現在の breathing_verifier.circom は breathingRate と confidenceScore のみを受け取る
        # シンプルな検証回路のため、CSIデータやコミットメントは不要

        # 回路入力データの構築（公開入力のみ）
        input_data = {
            "breathingRate": int(breathing_rate),
            "confidenceScore": int(confidence_score * 100),  # 0-100スケール
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
                breathing_rate=breathing_rate,
                confidence_score=confidence_score,
            )

            # 2. Witnessの計算
            logger.info("Calculating witness...")
            wasm_file = (
                self.build_dir / "breathing_verifier_js" / "breathing_verifier.wasm"
            )
            input_file = self.build_dir / "input.json"
            witness_file = self.build_dir / "witness.wtns"

            # WASMファイルの存在確認
            if not wasm_file.exists():
                error_msg = f"WASM file not found: {wasm_file}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

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
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                stdout_msg = stdout.decode() if stdout else ""
                stderr_msg = stderr.decode() if stderr else ""
                error_msg = f"stdout: {stdout_msg}\nstderr: {stderr_msg}" if (stdout_msg or stderr_msg) else "Unknown error"
                logger.error(f"Witness calculation failed: {error_msg}")
                raise RuntimeError(f"Witness calculation failed: {error_msg}")

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
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                stdout_msg = stdout.decode() if stdout else ""
                stderr_msg = stderr.decode() if stderr else ""
                error_msg = f"stdout: {stdout_msg}\nstderr: {stderr_msg}" if (stdout_msg or stderr_msg) else "Unknown error"
                logger.error(f"Proof generation failed: {error_msg}")
                raise RuntimeError(f"Proof generation failed: {error_msg}")

            # 4. 証明データの読み込み
            with open(proof_file, "r") as f:
                proof = json.load(f)

            with open(public_file, "r") as f:
                public_signals = json.load(f)

            logger.info("ZKP generation completed successfully")

            return {
                "proof": proof,
                "publicSignals": public_signals,
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

    async def generate_full_cosine_similarity_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = 10000
    ) -> Dict[str, Any]:
        """
        全サブキャリア × 全周波数ポイントのコサイン類似度ZKP証明を生成

        Args:
            reference_matrix: 参照CSIデータ [周波数ポイント][サブキャリア]
            candidate_matrix: 候補CSIデータ [周波数ポイント][サブキャリア]
            scale: 固定小数点スケール（デフォルト: 10000）

        Returns:
            {
                "proof": ZKP証明オブジェクト,
                "publicSignals": 公開信号リスト,
                "similarity": 類似度（整数値）,
                "normalizedSimilarity": 正規化された類似度（0.0-1.0）,
                "normA_squared": 参照ベクトルのノルム二乗,
                "normB_squared": 候補ベクトルのノルム二乗,
                "dotProduct": 内積,
                "isValid": 有効性フラグ
            }

        Raises:
            ValueError: 入力データが不正な場合
            RuntimeError: ZKP証明生成に失敗した場合
        """
        import time

        try:
            logger.info("=" * 80)
            logger.info("🚀 Starting Full Cosine Similarity ZKP Proof Generation")
            logger.info("=" * 80)
            total_start_time = time.time()

            # ZKP回路ファイルの存在チェック
            full_sim_wasm = self.build_dir / "csi_full_similarity_js" / "csi_full_similarity.wasm"
            full_sim_zkey = self.keys_dir / "csi_full_similarity_final.zkey"

            if not full_sim_wasm.exists() or not full_sim_zkey.exists():
                raise FileNotFoundError(
                    f"Full similarity ZKP circuit files not found.\n"
                    f"WASM: {full_sim_wasm} (exists: {full_sim_wasm.exists()})\n"
                    f"zkey: {full_sim_zkey} (exists: {full_sim_zkey.exists()})\n"
                    f"Please run: cd zkp && npm run compile:full_similarity && npm run setup:full_similarity"
                )

            # 入力検証
            if not reference_matrix or not candidate_matrix:
                raise ValueError("Reference and candidate matrices cannot be empty")

            if len(reference_matrix) != len(candidate_matrix):
                raise ValueError("Reference and candidate must have same number of frequency points")

            if len(reference_matrix[0]) != len(candidate_matrix[0]):
                raise ValueError("Reference and candidate must have same number of subcarriers")

            original_freq_points = len(reference_matrix)
            original_subcarriers = len(reference_matrix[0])

            logger.info(
                f"Generating full cosine similarity ZKP: "
                f"{original_freq_points} freq points × {original_subcarriers} subcarriers (before resize)"
            )

            # 1. Witness生成用の入力データ準備（内部で期待サイズにリサイズ）
            input_data = self._prepare_full_cosine_similarity_input(
                reference_matrix,
                candidate_matrix,
                scale
            )

            # 回路の期待サイズ（リサイズ後の実サイズ）
            num_freq_points = len(input_data["referenceMatrix"])
            num_subcarriers = len(input_data["referenceMatrix"][0])

            # 2. Witness生成
            witness_file = await self._generate_full_cosine_similarity_witness(input_data)

            # 3. ZKP証明生成
            proof, public_signals = await self._generate_full_cosine_similarity_groth16_proof(witness_file)

            # 4. 結果パース
            # Public signals: [referenceMatrix..., candidateMatrix..., similarity, dotProduct, isValid]
            num_matrix_elements = num_freq_points * num_subcarriers
            expected_len = 2 * num_matrix_elements + 3
            actual_len = len(public_signals)

            logger.info(
                f"Public signals length: actual={actual_len}, expected>={expected_len}"
            )

            if actual_len < 3:
                raise RuntimeError(
                    f"publicSignals length too short: got {actual_len}, need at least 3 outputs"
                )

            # 出力は末尾3つを使用（前段の長さに依存せず安全に取得）
            similarity = int(public_signals[-3])
            dotProduct = int(public_signals[-2])
            isValid = int(public_signals[-1])

            # 注: 回路で出力されるsimilarityは dotProduct * SCALE
            # 実際のコサイン類似度を計算するには、public signalsから
            # normA_squaredとnormB_squaredを計算する必要がある
            # ここでは簡易的に、similarityを正規化して返す

            result = {
                "proof": proof,
                "publicSignals": public_signals,
                "similarity": similarity,
                "normalizedSimilarity": similarity / (scale * scale),  # dotProduct * SCALE を正規化
                "dotProduct": dotProduct,
                "isValid": bool(isValid)
            }

            total_time = time.time() - total_start_time

            logger.info("=" * 80)
            logger.info(f"✅ Full Cosine Similarity ZKP Proof Generation COMPLETED")
            logger.info(f"   Total Time: {total_time:.3f} seconds")
            logger.info(f"   Similarity: {similarity / (scale * scale):.4f}")
            logger.info(f"   Dot Product: {dotProduct}")
            logger.info(f"   Is Valid: {bool(isValid)}")
            logger.info("=" * 80)

            return result

        except Exception as e:
            logger.error(f"Full cosine similarity ZKP generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Full cosine similarity ZKP generation failed: {str(e)}")

    def _prepare_full_cosine_similarity_input(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int
    ) -> Dict[str, Any]:
        """
        全データコサイン類似度Witness生成用の入力データを準備

        Args:
            reference_matrix: 参照CSIデータ [周波数ポイント][サブキャリア]
            candidate_matrix: 候補CSIデータ [周波数ポイント][サブキャリア]
            scale: 固定小数点スケール

        Returns:
            ZKP回路への入力データ
        """
        # 回路の期待サイズ
        EXPECTED_FREQ_POINTS = 25
        EXPECTED_SUBCARRIERS = 200

        # マトリックスを期待サイズにリサイズ（パディングまたはトリミング）
        def resize_matrix(matrix: List[List[int]], target_rows: int, target_cols: int) -> List[List[int]]:
            resized = []
            for i in range(target_rows):
                if i < len(matrix):
                    row = matrix[i][:target_cols]  # トリミング
                    # 不足分をゼロパディング
                    row.extend([0] * (target_cols - len(row)))
                else:
                    # 行が足りない場合はゼロ行を追加
                    row = [0] * target_cols
                resized.append(row)
            return resized

        # マトリックスサイズをログ出力
        ref_rows = len(reference_matrix)
        ref_cols = len(reference_matrix[0]) if reference_matrix else 0
        cand_rows = len(candidate_matrix)
        cand_cols = len(candidate_matrix[0]) if candidate_matrix else 0

        logger.info(
            f"Input matrix sizes - Reference: {ref_rows}×{ref_cols}, "
            f"Candidate: {cand_rows}×{cand_cols}, "
            f"Expected: {EXPECTED_FREQ_POINTS}×{EXPECTED_SUBCARRIERS}"
        )

        # マトリックスをリサイズ
        reference_matrix = resize_matrix(reference_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)
        candidate_matrix = resize_matrix(candidate_matrix, EXPECTED_FREQ_POINTS, EXPECTED_SUBCARRIERS)

        # 入力データ構築（マトリックスのみ）
        input_data = {
            "referenceMatrix": reference_matrix,
            "candidateMatrix": candidate_matrix
        }

        logger.info(
            f"Full cosine similarity input prepared: "
            f"referenceMatrix: {len(reference_matrix)}x{len(reference_matrix[0])}, "
            f"candidateMatrix: {len(candidate_matrix)}x{len(candidate_matrix[0])}"
        )

        return input_data

    async def _generate_full_cosine_similarity_witness(
        self,
        input_data: Dict[str, Any]
    ) -> str:
        """
        全データコサイン類似度のWitnessを生成

        Args:
            input_data: 入力データ

        Returns:
            Witnessファイルのパス

        Raises:
            RuntimeError: Witness生成に失敗した場合
        """
        try:
            # 入力データのサイズをログ出力
            logger.info(f"Full cosine similarity input data keys: {list(input_data.keys())}")
            for key, value in input_data.items():
                if isinstance(value, list):
                    logger.info(f"  {key}: list of {len(value)} elements")
                else:
                    logger.info(f"  {key}: {type(value).__name__}")

            # 入力データをJSONファイルに保存
            input_file = self.temp_dir / f"full_cosine_similarity_input_{uuid.uuid4()}.json"
            with open(input_file, 'w') as f:
                json.dump(input_data, f)

            logger.info(f"Input file saved: {input_file}")

            # Witnessファイルのパス
            witness_file = self.temp_dir / f"full_cosine_similarity_witness_{uuid.uuid4()}.wtns"

            # WASMファイルのパス
            wasm_file = self.circuits_dir / "build" / "csi_full_similarity_js" / "csi_full_similarity.wasm"

            if not wasm_file.exists():
                raise RuntimeError(f"WASM file not found: {wasm_file}")

            # snarkjsでWitness生成
            cmd = [
                "node",
                "--experimental-wasm-modules",
                "node_modules/.bin/snarkjs",
                "wtns",
                "calculate",
                str(wasm_file),
                str(input_file),
                str(witness_file)
            ]

            import time
            logger.info("⏱️ Starting witness generation...")
            start_time = time.time()

            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.circuits_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await result.communicate()

            witness_time = time.time() - start_time

            if result.returncode != 0:
                stdout_msg = stdout.decode() if stdout else ""
                stderr_msg = stderr.decode() if stderr else ""
                error_msg = f"stdout: {stdout_msg}\nstderr: {stderr_msg}" if (stdout_msg or stderr_msg) else "Unknown error"
                logger.error(f"Full cosine similarity witness calculation failed: {error_msg}")
                raise RuntimeError(f"Witness generation failed: {error_msg}")

            logger.info(f"✅ Full cosine similarity witness generated in {witness_time:.3f} seconds: {witness_file}")

            return str(witness_file)

        except Exception as e:
            logger.error(f"Full cosine similarity witness generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Witness generation failed: {str(e)}")

    async def _generate_full_cosine_similarity_groth16_proof(
        self,
        witness_file: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        全データコサイン類似度のGroth16証明を生成

        Args:
            witness_file: Witnessファイルのパス

        Returns:
            (proof, publicSignals)

        Raises:
            RuntimeError: 証明生成に失敗した場合
        """
        import time

        try:
            # zkeyファイルのパス
            zkey_file = self.circuits_dir / "keys" / "csi_full_similarity_final.zkey"

            if not zkey_file.exists():
                raise RuntimeError(
                    f"zkey file not found: {zkey_file}\n"
                    f"Please run: cd zkp && npm run setup:full_similarity"
                )

            # 出力ファイル
            proof_file = self.temp_dir / f"full_cosine_similarity_proof_{uuid.uuid4()}.json"
            public_file = self.temp_dir / f"full_cosine_similarity_public_{uuid.uuid4()}.json"

            # snarkjsで証明生成
            cmd = [
                "node",
                "node_modules/.bin/snarkjs",
                "groth16",
                "prove",
                str(zkey_file),
                witness_file,
                str(proof_file),
                str(public_file)
            ]

            logger.info("⏱️ Starting proof generation...")
            start_time = time.time()

            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.circuits_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await result.communicate()

            generation_time = time.time() - start_time

            if result.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Proof generation failed: {error_msg}")

            # 証明と公開信号を読み込み
            with open(proof_file, 'r') as f:
                proof = json.load(f)

            with open(public_file, 'r') as f:
                public_signals = json.load(f)

            logger.info(f"✅ Full cosine similarity Groth16 proof generated in {generation_time:.3f} seconds")

            return proof, public_signals

        except Exception as e:
            logger.error(f"Full cosine similarity Groth16 proof generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Proof generation failed: {str(e)}")

    async def verify_full_cosine_similarity_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int]
    ) -> bool:
        """
        全CSIデータのコサイン類似度ZKP証明を検証

        Args:
            proof: ZKP証明データ
            public_signals: 公開信号

        Returns:
            検証結果（True: 有効, False: 無効）
        """
        import time

        try:
            # 検証キーパス
            vkey_path = str(self.keys_dir / "csi_full_similarity_verification_key.json")

            if not os.path.exists(vkey_path):
                raise FileNotFoundError(f"Verification key not found: {vkey_path}")

            # 一時ファイル作成
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            ) as proof_file:
                json.dump(proof, proof_file)
                proof_path = proof_file.name

            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            ) as public_file:
                json.dump(public_signals, public_file)
                public_path = public_file.name

            try:
                # snarkjs検証実行
                cmd = [
                    "npx", "snarkjs", "groth16", "verify",
                    vkey_path,
                    public_path,
                    proof_path
                ]

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

                # snarkjsの出力から検証結果を判定
                is_valid = "OK" in result.stdout

                if is_valid:
                    logger.info(f"✅ Full cosine similarity proof verification PASSED in {verification_time:.3f} seconds")
                else:
                    logger.warning(f"❌ Full cosine similarity proof verification FAILED in {verification_time:.3f} seconds")

                return is_valid

            finally:
                # 一時ファイル削除
                if os.path.exists(proof_path):
                    os.unlink(proof_path)
                if os.path.exists(public_path):
                    os.unlink(public_path)

        except Exception as e:
            logger.error(f"Proof verification failed: {e}", exc_info=True)
            raise RuntimeError(f"Proof verification failed: {str(e)}")

    # ========== 全DataFrame解析用ZKPメソッド ==========
