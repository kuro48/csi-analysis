"""
ZKP証明生成サービス（汎用Circom回路版）

使用回路:
  - csi_breathing_normality.circom → ZKPBreathingService
"""

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.zkp_circuit_metrics import read_r1cs_metrics
from app.services.zkp_paths import resolve_zkp_dir
from app.services.zkp_stage_profile import build_stage_breakdown

logger = logging.getLogger(__name__)


class ZKPCircuitService:
    """Circom/snarkjs Groth16 回路汎用ZKP証明生成サービス。"""

    EXPECTED_FREQ_POINTS = 45
    EXPECTED_SUBCARRIERS = 971
    DEFAULT_SCALE = 100
    # 2^24 Powers of Tau を使う大規模回路は 4GB ヒープでは OOM する。
    LARGE_CIRCUITS = ("csi_lomb_scargle_normality",)
    DEFAULT_NODE_HEAP_MB = 4096
    LARGE_NODE_HEAP_MB = 14336
    # Perpetual Powers of Tau contribution 0080 の phase-2 準備済み 2^24 ファイル。
    PTAU24_URL = (
        "https://pse-trusted-setup-ppot.s3.eu-central-1.amazonaws.com/pot28_0080/ppot_0080_24.ptau"
    )
    PTAU24_SIZE = 19327446162
    _constraint_count_cache: Dict[Tuple[str, int], Optional[int]] = {}

    def __init__(
        self,
        circuit_name: str,
        zkp_dir: Optional[str] = None,
        auto_compile: bool = True,
    ) -> None:
        self.circuit_name = circuit_name
        # "csi_breathing_normality" → "Breathing_normality"
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

    def _circuit_source_files(self) -> List[Path]:
        """Return the main circuit and every locally resolvable include dependency."""
        main = self.zkp_dir / "circuits" / f"{self.circuit_name}.circom"
        pending = [main]
        sources: List[Path] = []
        seen: set[Path] = set()

        while pending:
            source = pending.pop()
            try:
                source = source.resolve()
            except OSError:
                continue
            if source in seen or not source.is_file():
                continue
            seen.add(source)
            sources.append(source)

            try:
                text = source.read_text(encoding="utf-8")
            except OSError:
                continue
            for include in re.findall(r'^\s*include\s+"([^"]+)"\s*;', text, re.MULTILINE):
                candidates = (
                    source.parent / include,
                    self.zkp_dir / include,
                    self.zkp_dir / "node_modules" / include,
                )
                dependency = next((candidate for candidate in candidates if candidate.is_file()), None)
                if dependency is not None:
                    pending.append(dependency)

        return sources

    def _circuit_build_is_stale(self, wasm: Path, zkey: Path) -> bool:
        """Detect artifacts generated for an older circuit source or include file."""
        r1cs = self.build_dir / f"{self.circuit_name}.r1cs"
        artifacts = (wasm, r1cs, zkey)
        if any(not artifact.is_file() for artifact in artifacts):
            return True

        sources = self._circuit_source_files()
        if not sources:
            return False
        newest_source = max(source.stat().st_mtime_ns for source in sources)
        return any(artifact.stat().st_mtime_ns < newest_source for artifact in artifacts)

    def _check_setup(self) -> None:
        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        build_is_stale = self._circuit_build_is_stale(wasm, zkey)

        if build_is_stale:
            if self.auto_compile:
                logger.warning("%s ZKP circuit files are missing or stale. Starting auto-compilation...", self.label)
                try:
                    self._auto_compile_circuit()
                except Exception as exc:
                    logger.error("Auto-compilation failed: %s", exc)
                    logger.warning(
                        "Please manually run:\n" "  cd zkp && npm run compile:%s && npm run setup:%s",
                        self.label.lower(),
                        self.label.lower(),
                    )
            else:
                logger.warning(
                    "%s ZKP circuit files are missing or stale. "
                    "Please run: cd zkp && npm run compile:%s && npm run setup:%s",
                    self.label,
                    self.label.lower(),
                    self.label.lower(),
                )
        else:
            logger.info("%s ZKP circuit is ready", self.label)

    def _auto_compile_circuit(self) -> None:
        circuit_file = self.zkp_dir / "circuits" / f"{self.circuit_name}.circom"

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

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not self._circuit_build_is_stale(wasm, zkey):
            return

        if not circuit_file.exists():
            raise RuntimeError(f"Circuit file not found: {circuit_file}")

        logger.info("Compiling %s circuit (this may take several minutes)...", self.label)
        result = subprocess.run(
            [
                "circom",
                str(circuit_file),
                "--r1cs",
                "--wasm",
                "--sym",
                "--c",
                "-o",
                str(self.build_dir),
                "-l",
                str(self.zkp_dir / "node_modules"),
            ],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Circuit compilation failed: {result.stderr}")

        self._run_trusted_setup()

    def _node_env(self) -> Dict[str, str]:
        """snarkjs/node に渡すヒープ上限。回路規模に応じて既定値を変える。"""
        default_mb = self.LARGE_NODE_HEAP_MB if self.circuit_name in self.LARGE_CIRCUITS else self.DEFAULT_NODE_HEAP_MB
        override = os.getenv("ZKP_NODE_MAX_OLD_SPACE_MB", "")
        heap_mb = int(override) if override.isdigit() else default_mb
        return {**os.environ, "NODE_OPTIONS": f"--max-old-space-size={heap_mb}"}

    def _ptau_is_complete(self, ptau_file: Path, expected: int) -> bool:
        """ptauが揃っているか。中断した旧ダウンロードの残骸は末尾を切り詰める。

        バインドマウント上ではtruncate直後のサイズ報告が遅れるため、
        過大なサイズは不足と区別して完了扱いにする。
        """
        control = ptau_file.with_name(ptau_file.name + ".aria2")
        if not ptau_file.exists() or control.exists():
            return False
        size = ptau_file.stat().st_size
        if size < expected:
            return False
        if size > expected:
            with open(ptau_file, "r+b") as handle:
                handle.truncate(expected)
        return True

    def _ensure_ptau(self, ptau_power: int) -> Path:
        ptau_file = self.keys_dir / f"powersOfTau28_hez_final_{ptau_power}.ptau"

        if ptau_power != 24:
            if not ptau_file.exists():
                import urllib.request

                url = f"https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_{ptau_power}.ptau"
                urllib.request.urlretrieve(url, str(ptau_file))
            return ptau_file

        # 2^24 は約19GBあり、切断からの再開が必須なのでダウンローダに任せる。
        url = os.getenv("LOMB_PTAU_URL", self.PTAU24_URL)
        expected = int(os.getenv("LOMB_PTAU_SIZE", str(self.PTAU24_SIZE)))

        if not self._ptau_is_complete(ptau_file, expected):
            logger.warning("Downloading the 2^24 Powers of Tau file (about 19GB)...")
            if shutil.which("aria2c"):
                command = [
                    "aria2c",
                    "--continue=true",
                    "--allow-overwrite=true",
                    "--auto-file-renaming=false",
                    "--file-allocation=none",
                    "--split=16",
                    "--max-connection-per-server=16",
                    f"--dir={self.keys_dir}",
                    f"--out={ptau_file.name}",
                    url,
                ]
            else:
                command = [
                    "curl",
                    "--fail",
                    "--show-error",
                    "--location",
                    "--continue-at",
                    "-",
                    "--output",
                    str(ptau_file),
                    url,
                ]
            subprocess.run(command, cwd=str(self.zkp_dir), check=True)

        if not self._ptau_is_complete(ptau_file, expected):
            actual = ptau_file.stat().st_size if ptau_file.exists() else 0
            raise RuntimeError(
                f"2^24 Powers of Tau file is incomplete: {ptau_file} ({actual}/{expected} bytes). "
                "Set LOMB_PTAU_URL to a trusted phase-2 ceremony file, or place it manually."
            )
        return ptau_file

    def _run_trusted_setup(self) -> None:
        logger.warning("Starting Trusted Setup for %s circuit (this may take 10-60 minutes)...", self.label)

        ptau_power = 24 if self.circuit_name in self.LARGE_CIRCUITS else 19
        ptau_file = self._ensure_ptau(ptau_power)

        r1cs = self.build_dir / f"{self.circuit_name}.r1cs"
        zkey_0 = self.keys_dir / f"{self.circuit_name}_0000.zkey"
        zkey_final = self.keys_dir / f"{self.circuit_name}_final.zkey"
        vkey = self.keys_dir / f"{self.circuit_name}_verification_key.json"

        setup_env = self._node_env()
        subprocess.run(
            ["snarkjs", "groth16", "setup", str(r1cs), str(ptau_file), str(zkey_0)],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True,
            check=True,
            env=setup_env,
        )
        subprocess.run(
            ["snarkjs", "zkey", "contribute", str(zkey_0), str(zkey_final), f"--name={self.label} contribution", "-v"],
            cwd=str(self.zkp_dir),
            input=secrets.token_hex(32) + "\n",
            capture_output=True,
            text=True,
            check=True,
            env=setup_env,
        )
        subprocess.run(
            ["snarkjs", "zkey", "export", "verificationkey", str(zkey_final), str(vkey)],
            cwd=str(self.zkp_dir),
            capture_output=True,
            text=True,
            check=True,
            env=setup_env,
        )
        logger.info("%s Trusted Setup completed", self.label)

    # ------------------------------------------------------------------ #
    # 回路メトリクス・計測
    # ------------------------------------------------------------------ #

    @property
    def r1cs_path(self) -> Path:
        return self.build_dir / f"{self.circuit_name}.r1cs"

    def circuit_metrics(self) -> Dict[str, Any]:
        """回路の静的メトリクス。.r1cs が読めない場合は回路名だけを返す。"""
        return {"circuit_name": self.circuit_name, **(read_r1cs_metrics(self.r1cs_path) or {})}

    async def _prove_with_metrics(
        self,
        input_data: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
        """witness 生成と Groth16 証明を実行し、制約数・所要時間を添えて返す。"""
        witness_started = time.perf_counter()
        witness_file = await self._generate_witness(input_data)
        witness_seconds = time.perf_counter() - witness_started

        prove_started = time.perf_counter()
        proof, public_signals = await self._generate_groth16_proof(witness_file)
        prove_seconds = time.perf_counter() - prove_started

        performance = {
            **self.circuit_metrics(),
            "witness_time_seconds": witness_seconds,
            "prove_time_seconds": prove_seconds,
            "generation_time_seconds": witness_seconds + prove_seconds,
        }
        logger.info(
            "[%s] proof generated in %.3fs (witness %.3fs + prove %.3fs) — constraints=%s",
            self.label,
            performance["generation_time_seconds"],
            witness_seconds,
            prove_seconds,
            performance.get("constraint_count", "unknown"),
        )
        return proof, public_signals, performance

    async def _verify_with_metrics(
        self,
        proof: Dict[str, Any],
        public_signals: List[str],
        performance: Dict[str, Any],
    ) -> Tuple[bool, Dict[str, Any]]:
        """ローカル検証を実行し、検証時間を加えた新しい performance を返す。"""
        started = time.perf_counter()
        is_valid = await self.verify_proof(proof, public_signals)
        verify_seconds = time.perf_counter() - started
        logger.info("[%s] proof verified in %.3fs — isValid=%s", self.label, verify_seconds, is_valid)
        return is_valid, {**performance, "verify_time_seconds": verify_seconds}

    # ------------------------------------------------------------------ #
    # 証明生成・検証
    # ------------------------------------------------------------------ #

    def _get_constraint_count(self) -> Optional[int]:
        """コンパイル済みR1CSから非線形制約数を取得する。

        snarkjsの起動時間はベンチマークに含めず、同じR1CSについてはプロセス内で
        キャッシュする。取得不能でも証明生成自体は継続する。
        """
        r1cs = self.build_dir / f"{self.circuit_name}.r1cs"
        if not r1cs.exists():
            return None

        cache_key = (str(r1cs.resolve()), r1cs.stat().st_mtime_ns)
        if cache_key in self._constraint_count_cache:
            return self._constraint_count_cache[cache_key]

        snarkjs = shutil.which("snarkjs")
        command = [snarkjs, "r1cs", "info", str(r1cs)] if snarkjs else ["npx", "snarkjs", "r1cs", "info", str(r1cs)]
        count: Optional[int] = None
        try:
            result = subprocess.run(
                command,
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = f"{result.stdout}\n{result.stderr}"
            match = re.search(r"# of Constraints:\s*([0-9,]+)", output)
            if result.returncode == 0 and match:
                count = int(match.group(1).replace(",", ""))
            else:
                logger.warning("[%s] Could not read R1CS constraint count", self.label)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("[%s] Could not read R1CS constraint count: %s", self.label, exc)

        self._constraint_count_cache[cache_key] = count
        return count

    async def _generate_proof_with_benchmark(
        self,
        input_data: Dict[str, Any],
        *,
        verify: bool = False,
    ) -> Tuple[Dict[str, Any], List[str], Optional[bool], Dict[str, Any]]:
        """Witness・Groth16証明・検証を個別計測して研究用メタデータを返す。"""
        measured_at = datetime.now(timezone.utc).isoformat()
        constraint_count = await asyncio.to_thread(self._get_constraint_count)

        started = time.perf_counter()
        witness_file = await self._generate_witness(input_data)
        witness_seconds = time.perf_counter() - started

        started = time.perf_counter()
        proof, public_signals = await self._generate_groth16_proof(witness_file)
        proof_seconds = time.perf_counter() - started

        verification_seconds: Optional[float] = None
        is_valid: Optional[bool] = None
        if verify:
            started = time.perf_counter()
            is_valid = await self.verify_proof(proof, public_signals)
            verification_seconds = time.perf_counter() - started

        witness_ms = witness_seconds * 1000
        proof_ms = proof_seconds * 1000
        verification_ms = verification_seconds * 1000 if verification_seconds is not None else None
        total_ms = witness_ms + proof_ms + (verification_ms or 0)
        average_ns = (
            proof_seconds * 1_000_000_000 / constraint_count
            if constraint_count is not None and constraint_count > 0
            else None
        )
        benchmark = {
            "circuitName": self.circuit_name,
            "provingSystem": "groth16",
            "curve": "bn128",
            "constraintCount": constraint_count,
            "witnessGenerationMs": round(witness_ms, 3),
            "proofGenerationMs": round(proof_ms, 3),
            "verificationMs": round(verification_ms, 3) if verification_ms is not None else None,
            "totalMs": round(total_ms, 3),
            "averageProofTimePerConstraintNs": round(average_ns, 3) if average_ns is not None else None,
            "measuredAt": measured_at,
            "stageBreakdown": build_stage_breakdown(self.zkp_dir, self.circuit_name, proof_ms, constraint_count),
        }
        return proof, public_signals, is_valid, benchmark

    def _performance_from_benchmark(self, benchmark: Dict[str, Any]) -> Dict[str, Any]:
        """benchmark(ミリ秒・camelCase)を performance(秒・snake_case)へ変換する。

        証明生成は高価なので計測は一度だけ行い、研究用のCSV出力が使う benchmark と
        UIの制約数テーブルが使う performance の両方を同じ実測値から組み立てる。
        """
        witness_seconds = benchmark["witnessGenerationMs"] / 1000
        prove_seconds = benchmark["proofGenerationMs"] / 1000
        verification_ms = benchmark.get("verificationMs")

        performance = {
            **self.circuit_metrics(),
            "witness_time_seconds": witness_seconds,
            "prove_time_seconds": prove_seconds,
            "generation_time_seconds": witness_seconds + prove_seconds,
        }
        if verification_ms is not None:
            performance["verify_time_seconds"] = verification_ms / 1000
        return performance

    async def generate_proof(
        self,
        reference_matrix: List[List[int]],
        candidate_matrix: List[List[int]],
        scale: int = DEFAULT_SCALE,
    ) -> Dict[str, Any]:
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
            self.label,
            len(reference_matrix),
            len(reference_matrix[0]),
        )

        input_data = self._prepare_input(reference_matrix, candidate_matrix)
        proof, public_signals, _, benchmark = await self._generate_proof_with_benchmark(input_data)
        performance = self._performance_from_benchmark(benchmark)

        is_normal = bool(int(public_signals[0])) if public_signals else False
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_normal,
            "method": self.label.lower(),
            "performance": performance,
            "benchmark": benchmark,
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
            snarkjs = shutil.which("snarkjs")
            command = (
                [snarkjs, "groth16", "verify", vkey_path, signals_path, proof_path]
                if snarkjs
                else ["npx", "snarkjs", "groth16", "verify", vkey_path, signals_path, proof_path]
            )
            result = subprocess.run(
                command,
                cwd=str(self.zkp_dir),
                capture_output=True,
                text=True,
                timeout=60,
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

        try:
            with open(input_file, "w") as f:
                json.dump(input_data, f)
            input_file.chmod(0o600)

            env = self._node_env()
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(generate_witness_js),
                str(wasm),
                str(input_file),
                str(witness_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await proc.communicate()
        finally:
            input_file.unlink(missing_ok=True)

        if proc.returncode != 0:
            raise RuntimeError(
                f"[{self.label}] Witness generation failed: returncode={proc.returncode}\n"
                f"stdout: {stdout.decode(errors='replace') if stdout else ''}\n"
                f"stderr: {stderr.decode(errors='replace') if stderr else ''}"
            )
        witness_file.chmod(0o600)
        return str(witness_file)

    async def _generate_groth16_proof(self, witness_file: str) -> Tuple[Dict[str, Any], List[str]]:
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        proof_file = self.temp_dir / f"{self.circuit_name}_proof_{uuid.uuid4()}.json"
        public_file = self.temp_dir / f"{self.circuit_name}_public_{uuid.uuid4()}.json"

        if not zkey.exists():
            raise RuntimeError(f"zkey file not found: {zkey}")
        if not Path(witness_file).exists():
            raise RuntimeError(f"Witness file not found: {witness_file}")

        env = self._node_env()
        try:
            proc = await asyncio.create_subprocess_exec(
                "snarkjs",
                "groth16",
                "prove",
                str(zkey),
                str(witness_file),
                str(proof_file),
                str(public_file),
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
        finally:
            Path(witness_file).unlink(missing_ok=True)
            proof_file.unlink(missing_ok=True)
            public_file.unlink(missing_ok=True)


class ZKPBreathingService(ZKPCircuitService):
    """5-1.ipynb パイプライン呼吸正常判定回路サービス。

    入力: vmd[T] — VMDで抽出した呼吸成分の時系列
          (ゼロ中心化・±100 正規化済み整数、T=300固定、5Hz)
    回路: csi_breathing_normality.circom (BreathingNormalityCheck)
    判定: 回路内 DFT のグローバルピークが 6〜22 bpm 内 → isNormal=1
    """

    T = 300  # 時系列長 (60s × 5Hz)

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__("csi_breathing_normality", zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(
        self,
        vmd_signal: Optional[List[int]] = None,
        scale: int = ZKPCircuitService.DEFAULT_SCALE,
        # 基底クラスシグネチャとの互換 (無視される)
        reference_matrix: Optional[List[List[int]]] = None,
        candidate_matrix: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        if vmd_signal is None:
            raise ValueError("vmd_signal is required for BreathingNormalityCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                f"Run: cd zkp && npm run compile:breathing_normality && npm run setup:breathing_normality"
            )

        logger.info("[%s] Generating ZKP proof: vmd[%d]", self.label, len(vmd_signal))
        input_data = self._prepare_breathing_input(vmd_signal)
        proof, public_signals, _, benchmark = await self._generate_proof_with_benchmark(input_data)
        performance = self._performance_from_benchmark(benchmark)

        is_normal = bool(int(public_signals[0])) if public_signals else False
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_normal,
            "method": "breathing_normality",
            "performance": performance,
            "benchmark": benchmark,
        }

    def _prepare_breathing_input(self, vmd_signal: List[int]) -> Dict[str, Any]:
        T = self.T
        if len(vmd_signal) >= T:
            vmd_fixed = [int(v) for v in vmd_signal[:T]]
        else:
            vmd_fixed = [int(v) for v in vmd_signal] + [0] * (T - len(vmd_signal))
        return {"vmd": vmd_fixed}
