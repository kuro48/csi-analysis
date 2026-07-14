"""RISC Zero zkVM の CSI 呼吸解析ホスト CLI アダプタ。"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


def _default_binary_path() -> Path:
    configured = os.getenv("CSI_ZKVM_BINARY")
    if configured:
        return Path(configured)
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "zkvm" / "target" / "release" / "csi-zkvm-host"


class ZkVMBreathingService:
    """JSON 入力を RISC Zero host に渡し、検証済み receipt を受け取る。"""

    def __init__(
        self,
        binary_path: Optional[Union[str, Path]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.binary_path = Path(binary_path) if binary_path is not None else _default_binary_path()
        self.timeout_seconds = timeout_seconds or int(os.getenv("CSI_ZKVM_TIMEOUT_SECONDS", "1800"))

    async def generate_proof(self, pipeline_input: Dict[str, Any]) -> Dict[str, Any]:
        if not self.binary_path.is_file():
            raise FileNotFoundError(
                f"zkVM prover binary not found: {self.binary_path}. "
                "Build it with: cd zkvm && cargo build --release -p csi-zkvm-host"
            )
        expected_commitment = str(pipeline_input.get("input_commitment", ""))
        if not expected_commitment:
            raise ValueError("zkVM input_commitment is required")

        request_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                prefix="csi_zkvm_",
                delete=False,
                encoding="utf-8",
            ) as request_file:
                json.dump(pipeline_input, request_file, separators=(",", ":"))
                request_path = Path(request_file.name)
            request_path.chmod(0o600)

            process = await asyncio.create_subprocess_exec(
                str(self.binary_path),
                "prove",
                str(request_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise RuntimeError(f"zkVM proof generation timed out after {self.timeout_seconds}s") from exc

            if process.returncode != 0:
                detail = stderr.decode(errors="replace")[-4000:]
                raise RuntimeError(f"zkVM proof generation failed (exit={process.returncode}): {detail}")
            try:
                result = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("zkVM prover returned invalid JSON") from exc

            journal = result.get("journal") or {}
            if journal.get("input_commitment") != expected_commitment:
                raise RuntimeError("zkVM public input commitment does not match the submitted CSI")
            if result.get("isValid") is not True:
                raise RuntimeError("zkVM host did not return a locally verified receipt")
            return result
        finally:
            if request_path is not None:
                request_path.unlink(missing_ok=True)
