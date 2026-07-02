"""
ZKP証明生成サービス（汎用Circom回路版）

使用回路:
  - csi_music_similarity.circom  → ZKPMusicService
  - csi_wavelet_similarity.circom → ZKPWaveletService
"""

import asyncio
import json
import logging
import os
import secrets
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.zkp_paths import resolve_zkp_dir

logger = logging.getLogger(__name__)


class ZKPCircuitService:
    """Circom/snarkjs Groth16 回路汎用ZKP証明生成サービス。"""

    EXPECTED_FREQ_POINTS = 45
    EXPECTED_SUBCARRIERS = 971
    DEFAULT_SCALE = 100

    def __init__(
        self,
        circuit_name: str,
        zkp_dir: Optional[str] = None,
        auto_compile: bool = True,
    ) -> None:
        self.circuit_name = circuit_name
        # "csi_music_similarity" → "Music"
        self.label = circuit_name.replace("csi_", "").replace("_similarity", "").capitalize()

        self.zkp_dir = resolve_zkp_dir(zkp_dir)
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
        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"

        if not (wasm.exists() and zkey.exists()):
            if self.auto_compile:
                logger.warning("%s ZKP circuit files not found. Starting auto-compilation...", self.label)
                try:
                    self._auto_compile_circuit()
                except Exception as exc:
                    logger.error("Auto-compilation failed: %s", exc)
                    logger.warning(
                        "Please manually run:\n"
                        "  cd zkp && npm run compile:%s && npm run setup:%s",
                        self.label.lower(), self.label.lower(),
                    )
            else:
                logger.warning(
                    "%s ZKP circuit files not found. Please run: cd zkp && npm run compile:%s && npm run setup:%s",
                    self.label, self.label.lower(), self.label.lower(),
                )
        else:
            logger.info("%s ZKP circuit is ready", self.label)

    def _auto_compile_circuit(self) -> None:
        circuit_file = self.zkp_dir / "circuits" / f"{self.circuit_name}.circom"

        node_modules = self.zkp_dir / "node_modules"
        if not node_modules.exists():
            result = subprocess.run(
                ["npm", "install"], cwd=str(self.zkp_dir), capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"npm install failed: {result.stderr}")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if wasm.exists() and zkey.exists():
            return

        if not circuit_file.exists():
            raise RuntimeError(f"Circuit file not found: {circuit_file}")

        logger.info("Compiling %s circuit (this may take several minutes)...", self.label)
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
        logger.warning(
            "Starting Trusted Setup for %s circuit (this may take 10-60 minutes)...", self.label
        )

        ptau_file = self.keys_dir / "powersOfTau28_hez_final_19.ptau"
        if not ptau_file.exists():
            import urllib.request
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_19.ptau",
                str(ptau_file),
            )

        r1cs = self.build_dir / f"{self.circuit_name}.r1cs"
        zkey_0 = self.keys_dir / f"{self.circuit_name}_0000.zkey"
        zkey_final = self.keys_dir / f"{self.circuit_name}_final.zkey"
        vkey = self.keys_dir / f"{self.circuit_name}_verification_key.json"

        subprocess.run(
            ["snarkjs", "groth16", "setup", str(r1cs), str(ptau_file), str(zkey_0)],
            cwd=str(self.zkp_dir), capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["snarkjs", "zkey", "contribute", str(zkey_0), str(zkey_final),
             f"--name={self.label} contribution", "-v"],
            cwd=str(self.zkp_dir),
            input=secrets.token_hex(32) + "\n",
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            ["snarkjs", "zkey", "export", "verificationkey", str(zkey_final), str(vkey)],
            cwd=str(self.zkp_dir), capture_output=True, text=True, check=True,
        )
        logger.info("%s Trusted Setup completed", self.label)

    # ------------------------------------------------------------------ #
    # 証明生成・検証
    # ------------------------------------------------------------------ #

    async def generate_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = DEFAULT_SCALE,
    ) -> Dict[str, Any]:
        import time

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"

        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                f"Please run: cd zkp && npm run compile:{self.label.lower()} && npm run setup:{self.label.lower()}"
            )
        if not reference_matrix or not candidate_matrix:
            raise ValueError("Reference and candidate matrices cannot be empty")

        logger.info(
            "[%s] Generating ZKP proof: %d freq × %d subcarriers",
            self.label, len(reference_matrix), len(reference_matrix[0]),
        )

        start = time.time()
        input_data = self._prepare_input(reference_matrix, candidate_matrix)
        witness_file = await self._generate_witness(input_data)
        proof, public_signals = await self._generate_groth16_proof(witness_file)

        is_normal = bool(int(public_signals[0])) if public_signals else False
        logger.info(
            "[%s] ZKP proof done in %.3fs — isNormal=%s",
            self.label, time.time() - start, is_normal,
        )
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_normal,
            "method": self.label.lower(),
        }

    async def verify_proof(
        self,
        proof: Dict[str, Any],
        public_signals: List[int],
    ) -> bool:
        vkey_path = str(self.keys_dir / f"{self.circuit_name}_verification_key.json")
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
        except Exception as exc:
            logger.error("[%s] Proof verification failed: %s", self.label, exc, exc_info=True)
            raise RuntimeError(f"{self.label} proof verification failed: {exc}")
        finally:
            for p in (proof_path, signals_path):
                if os.path.exists(p):
                    os.unlink(p)

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
                row = [max(0, int(v)) for v in matrix[i][:cols]] if i < len(matrix) else []
                row.extend([0] * (cols - len(row)))
                result.append(row)
            return result

        return {
            "referenceMatrix": resize(reference_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS),
            "candidateMatrix": resize(candidate_matrix, self.EXPECTED_FREQ_POINTS, self.EXPECTED_SUBCARRIERS),
        }

    async def _generate_witness(self, input_data: Dict[str, Any]) -> str:
        input_file = self.temp_dir / f"{self.circuit_name}_input_{uuid.uuid4()}.json"
        witness_file = self.temp_dir / f"{self.circuit_name}_witness_{uuid.uuid4()}.wtns"
        generate_witness_js = self.build_dir / f"{self.circuit_name}_js" / "generate_witness.js"
        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"

        if not generate_witness_js.exists():
            raise RuntimeError(f"generate_witness.js not found: {generate_witness_js}")

        with open(input_file, "w") as f:
            json.dump(input_data, f)

        env = {**os.environ, "NODE_OPTIONS": "--max-old-space-size=4096"}
        proc = await asyncio.create_subprocess_exec(
            "node", str(generate_witness_js), str(wasm), str(input_file), str(witness_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"[{self.label}] Witness generation failed: returncode={proc.returncode}\n"
                f"stdout: {stdout.decode(errors='replace') if stdout else ''}\n"
                f"stderr: {stderr.decode(errors='replace') if stderr else ''}"
            )
        return str(witness_file)

    async def _generate_groth16_proof(self, witness_file: str) -> Tuple[Dict[str, Any], List[str]]:
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        proof_file = self.temp_dir / f"{self.circuit_name}_proof_{uuid.uuid4()}.json"
        public_file = self.temp_dir / f"{self.circuit_name}_public_{uuid.uuid4()}.json"

        if not zkey.exists():
            raise RuntimeError(f"zkey file not found: {zkey}")
        if not Path(witness_file).exists():
            raise RuntimeError(f"Witness file not found: {witness_file}")

        env = {**os.environ, "NODE_OPTIONS": "--max-old-space-size=4096"}
        proc = await asyncio.create_subprocess_exec(
            "snarkjs", "groth16", "prove",
            str(zkey), str(witness_file), str(proof_file), str(public_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"[{self.label}] Proof generation failed: returncode={proc.returncode}\n"
                f"stdout: {stdout.decode(errors='replace') if stdout else ''}\n"
                f"stderr: {stderr.decode(errors='replace') if stderr else ''}"
            )

        with open(proof_file) as f:
            proof = json.load(f)
        with open(public_file) as f:
            public_signals = json.load(f)

        return proof, public_signals


class ZKPWaveletService(ZKPCircuitService):
    """ウェーブレット DFT 近似回路サービス。

    入力: avg_csi[T] — 時系列 CSI 平均振幅 (整数、T=150固定)
    回路: csi_wavelet_similarity.circom (WaveletDFTBreathingCheck)
    """

    T = 150  # 時系列長 (30s × 5Hz)

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__("csi_wavelet_similarity", zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(
        self,
        avg_csi: Optional[List[int]] = None,
        scale: int = ZKPCircuitService.DEFAULT_SCALE,
        # 旧シグネチャとの後方互換 (無視される)
        reference_matrix: Optional[List[List[int]]] = None,
        candidate_matrix: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        import time

        if avg_csi is None:
            raise ValueError("avg_csi is required for WaveletDFTBreathingCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                f"Run: cd zkp && npm run compile:wavelet && npm run setup:wavelet"
            )

        logger.info("[%s] Generating ZKP proof: avg_csi[%d]", self.label, len(avg_csi))
        start = time.time()
        input_data = self._prepare_wavelet_input(avg_csi)
        witness_file = await self._generate_witness(input_data)
        proof, public_signals = await self._generate_groth16_proof(witness_file)

        is_normal = bool(int(public_signals[0])) if public_signals else False
        logger.info("[%s] ZKP proof done in %.3fs — isNormal=%s", self.label, time.time() - start, is_normal)
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_normal,
            "method": "wavelet",
        }

    def _prepare_wavelet_input(self, avg_csi: List[int]) -> Dict[str, Any]:
        T = self.T
        if len(avg_csi) >= T:
            csi_fixed = [int(v) for v in avg_csi[:T]]
        else:
            csi_fixed = [int(v) for v in avg_csi] + [0] * (T - len(avg_csi))
        return {"csi": csi_fixed}


class ZKPMusicService(ZKPCircuitService):
    """MUSIC ノイズ部分空間回路サービス。

    入力: en[L][K] — ノイズ固有ベクトル行列 (整数、L=32, K=30固定)
    回路: csi_music_similarity.circom (MUSICNoiseSubspaceCheck)
    """

    L = 32  # MUSIC_EMBEDDING_DIM
    K = 30  # L - MUSIC_MODEL_ORDER (32 - 2)
    EN_SCALE = 1000

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__("csi_music_similarity", zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(
        self,
        noise_subspace: Optional[List[List[int]]] = None,
        scale: int = ZKPCircuitService.DEFAULT_SCALE,
        # 旧シグネチャとの後方互換 (無視される)
        reference_matrix: Optional[List[List[int]]] = None,
        candidate_matrix: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        import time

        if noise_subspace is None:
            raise ValueError("noise_subspace is required for MUSICNoiseSubspaceCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                f"Run: cd zkp && npm run compile:music && npm run setup:music"
            )

        logger.info("[%s] Generating ZKP proof: en[%d][%d]", self.label, len(noise_subspace), len(noise_subspace[0]) if noise_subspace else 0)
        start = time.time()
        input_data = self._prepare_music_input(noise_subspace)
        witness_file = await self._generate_witness(input_data)
        proof, public_signals = await self._generate_groth16_proof(witness_file)

        is_normal = bool(int(public_signals[0])) if public_signals else False
        logger.info("[%s] ZKP proof done in %.3fs — isNormal=%s", self.label, time.time() - start, is_normal)
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_normal,
            "method": "music",
        }

    def _prepare_music_input(self, noise_subspace: List[List[int]]) -> Dict[str, Any]:
        L, K = self.L, self.K
        en = []
        for m in range(L):
            if m < len(noise_subspace):
                row = list(noise_subspace[m])
            else:
                row = []
            row = row[:K] + [0] * max(0, K - len(row))
            en.append([int(v) for v in row])
        return {"en": en}
