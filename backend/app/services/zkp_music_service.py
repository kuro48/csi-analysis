"""
ZKP証明生成サービス（MUSIC法版）

使用回路: csi_music_similarity.circom (MusicBreathingCheck)
  - 秘密入力: referenceMatrix[31][245], candidateMatrix[31][245]
             ※ Python側でlog10圧縮・サブキャリア正規化・線形31点に再ビン化・整数スケール済み
  - 公開出力: isNormal (0 or 1)
"""

import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

CIRCUIT_NAME = "csi_music_similarity"


class ZKPMusicService:
    """MUSIC法用ZKP証明生成サービス"""

    EXPECTED_FREQ_POINTS = 31
    EXPECTED_SUBCARRIERS = 245
    ZKP_NORMAL_LOW_BIN = 5
    ZKP_NORMAL_HIGH_BIN = 25
    DEFAULT_SCALE = 100

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True):
        if zkp_dir is None:
            zkp_dir_env = os.getenv("ZKP_DIR")
            if zkp_dir_env:
                zkp_dir = zkp_dir_env
            else:
                docker_zkp = Path("/zkp")
                if docker_zkp.exists():
                    zkp_dir = docker_zkp
                else:
                    current_file = Path(__file__)
                    project_root = current_file.parent.parent.parent.parent
                    zkp_dir = project_root / "zkp"

        self.zkp_dir = Path(zkp_dir)
        self.circuits_dir = self.zkp_dir
        self.build_dir = self.zkp_dir / "build"
        self.keys_dir = self.zkp_dir / "keys"
        self.auto_compile = auto_compile
        self.temp_dir = Path(tempfile.gettempdir())

        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.mkdir(parents=True, exist_ok=True)

        self._check_setup()

    # ------------------------------------------------------------------ #
    # セットアップ
    # ------------------------------------------------------------------ #

    def _check_setup(self) -> None:
        wasm = self.build_dir / f"{CIRCUIT_NAME}_js" / f"{CIRCUIT_NAME}.wasm"
        zkey = self.keys_dir / f"{CIRCUIT_NAME}_final.zkey"

        if not (wasm.exists() and zkey.exists()):
            if self.auto_compile:
                logger.warning("Music ZKP circuit files not found. Starting auto-compilation...")
                try:
                    self._auto_compile_circuit()
                except Exception as e:
                    logger.error(f"Auto-compilation failed: {e}")
                    logger.warning(
                        "Please manually run:\n"
                        "  cd zkp && npm run compile:music && npm run setup:music"
                    )
            else:
                logger.warning(
                    "Music ZKP circuit files not found. Please run:\n"
                    "  cd zkp && npm run compile:music && npm run setup:music"
                )
        else:
            logger.info("Music ZKP circuit is ready")

    def _auto_compile_circuit(self) -> None:
        circuit_file = self.zkp_dir / "circuits" / f"{CIRCUIT_NAME}.circom"

        node_modules = self.zkp_dir / "node_modules"
        if not node_modules.exists():
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"npm install failed: {result.stderr}")

        wasm = self.build_dir / f"{CIRCUIT_NAME}_js" / f"{CIRCUIT_NAME}.wasm"
        zkey = self.keys_dir / f"{CIRCUIT_NAME}_final.zkey"
        if wasm.exists() and zkey.exists():
            return

        if not circuit_file.exists():
            raise RuntimeError(f"Circuit file not found: {circuit_file}")

        logger.info("Compiling music circuit (this may take several minutes)...")
        result = subprocess.run(
            [
                "circom", str(circuit_file),
                "--r1cs", "--wasm", "--sym", "--c",
                "-o", str(self.build_dir),
                "-l", str(self.zkp_dir / "node_modules"),
            ],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Circuit compilation failed: {result.stderr}")

        self._run_trusted_setup()

    def _run_trusted_setup(self) -> None:
        logger.warning("Starting Trusted Setup for Music circuit (this may take 10-60 minutes)...")

        ptau_file = self.keys_dir / "powersOfTau28_hez_final_19.ptau"
        if not ptau_file.exists():
            import urllib.request
            ptau_url = "https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_19.ptau"
            urllib.request.urlretrieve(ptau_url, str(ptau_file))

        r1cs = self.build_dir / f"{CIRCUIT_NAME}.r1cs"
        zkey_0 = self.keys_dir / f"{CIRCUIT_NAME}_0000.zkey"
        zkey_final = self.keys_dir / f"{CIRCUIT_NAME}_final.zkey"
        vkey = self.keys_dir / f"{CIRCUIT_NAME}_verification_key.json"

        subprocess.run(
            ["snarkjs", "groth16", "setup", str(r1cs), str(ptau_file), str(zkey_0)],
            cwd=str(self.zkp_dir), capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["snarkjs", "zkey", "contribute", str(zkey_0), str(zkey_final),
             "--name=Music contribution", "-v"],
            cwd=str(self.zkp_dir),
            input=secrets.token_hex(32) + "\n",
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["snarkjs", "zkey", "export", "verificationkey", str(zkey_final), str(vkey)],
            cwd=str(self.zkp_dir), capture_output=True, text=True, check=True,
        )
        logger.info("Music Trusted Setup completed")

    # ------------------------------------------------------------------ #
    # 証明生成・検証
    # ------------------------------------------------------------------ #

    async def generate_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = DEFAULT_SCALE,
    ) -> Dict[str, Any]:
        """
        MUSIC擬似スペクトル行列からZKP証明を生成する。

        Args:
            reference_matrix: 参照CSI [周波数ポイント][サブキャリア]（整数スケール済み）
            candidate_matrix: 候補CSI [周波数ポイント][サブキャリア]（整数スケール済み）
            scale: 表示用スケール（ZKP回路には影響しない）

        Returns:
            proof, publicSignals, isNormal, isValid, method を含む辞書
        """
        import time

        try:
            wasm = self.build_dir / f"{CIRCUIT_NAME}_js" / f"{CIRCUIT_NAME}.wasm"
            zkey = self.keys_dir / f"{CIRCUIT_NAME}_final.zkey"

            if not wasm.exists() or not zkey.exists():
                raise FileNotFoundError(
                    "Music ZKP circuit files not found.\n"
                    "Please run: cd zkp && npm run compile:music && npm run setup:music"
                )

            if not reference_matrix or not candidate_matrix:
                raise ValueError("Reference and candidate matrices cannot be empty")

            logger.info(
                f"[Music] Generating ZKP proof: "
                f"{len(reference_matrix)} freq × {len(reference_matrix[0])} subcarriers"
            )

            total_start = time.time()
            input_data = self._prepare_input(reference_matrix, candidate_matrix)
            witness_file = await self._generate_witness(input_data)
            proof, public_signals = await self._generate_groth16_proof(witness_file)

            is_normal = bool(int(public_signals[0])) if public_signals else False

            logger.info(
                f"[Music] ZKP proof done in {time.time() - total_start:.3f}s "
                f"— isNormal={is_normal}"
            )
            return {
                "proof": proof,
                "publicSignals": public_signals,
                "isNormal": is_normal,
                "isValid": is_normal,
                "method": "music",
            }

        except Exception as e:
            logger.error(f"[Music] ZKP proof generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Music ZKP proof generation failed: {e}")

    async def verify_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int],
    ) -> bool:
        try:
            vkey_path = str(self.keys_dir / f"{CIRCUIT_NAME}_verification_key.json")
            if not os.path.exists(vkey_path):
                raise FileNotFoundError(f"Verification key not found: {vkey_path}")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as pf:
                json.dump(proof, pf)
                proof_path = pf.name

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as sf:
                json.dump(public_signals, sf)
                signals_path = sf.name

            try:
                result = subprocess.run(
                    ["npx", "snarkjs", "groth16", "verify", vkey_path, signals_path, proof_path],
                    cwd=str(self.zkp_dir),
                    capture_output=True, text=True, timeout=10,
                )
                return result.returncode == 0 and "OK" in result.stdout
            finally:
                for p in (proof_path, signals_path):
                    if os.path.exists(p):
                        os.unlink(p)

        except Exception as e:
            logger.error(f"[Music] Proof verification failed: {e}", exc_info=True)
            raise RuntimeError(f"Music proof verification failed: {e}")

    # ------------------------------------------------------------------ #
    # プライベートヘルパー
    # ------------------------------------------------------------------ #

    def _prepare_input(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
    ) -> Dict[str, Any]:
        def resize(matrix: List[List[int]], rows: int, cols: int) -> List[List[int]]:
            result = []
            for i in range(rows):
                row = list(matrix[i][:cols]) if i < len(matrix) else []
                row.extend([0] * (cols - len(row)))
                result.append(row)
            return result

        return {
            "referenceMatrix": resize(reference_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS),
            "candidateMatrix": resize(candidate_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS),
        }

    async def _generate_witness(self, input_data: Dict[str, Any]) -> str:
        wasm = self.circuits_dir / "build" / f"{CIRCUIT_NAME}_js" / f"{CIRCUIT_NAME}.wasm"
        input_file = self.temp_dir / f"music_input_{uuid.uuid4()}.json"
        witness_file = self.temp_dir / f"music_witness_{uuid.uuid4()}.wtns"

        with open(input_file, "w") as f:
            json.dump(input_data, f)

        proc = await asyncio.create_subprocess_exec(
            "node", "--experimental-wasm-modules",
            "node_modules/.bin/snarkjs",
            "wtns", "calculate",
            str(wasm), str(input_file), str(witness_file),
            cwd=str(self.circuits_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Music witness generation failed: {stderr.decode()}")

        return str(witness_file)

    async def _generate_groth16_proof(self, witness_file: str) -> Tuple[Dict[str, Any], List[str]]:
        zkey = self.circuits_dir / "keys" / f"{CIRCUIT_NAME}_final.zkey"
        proof_file = self.temp_dir / f"music_proof_{uuid.uuid4()}.json"
        public_file = self.temp_dir / f"music_public_{uuid.uuid4()}.json"

        proc = await asyncio.create_subprocess_exec(
            "node", "node_modules/.bin/snarkjs",
            "groth16", "prove",
            str(zkey), witness_file,
            str(proof_file), str(public_file),
            cwd=str(self.circuits_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Music proof generation failed: {stderr.decode()}")

        with open(proof_file) as f:
            proof = json.load(f)
        with open(public_file) as f:
            public_signals = json.load(f)

        return proof, public_signals
