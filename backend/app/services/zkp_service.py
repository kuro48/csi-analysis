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
