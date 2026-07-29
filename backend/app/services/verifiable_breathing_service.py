"""5-1.ipynb解析とCircom、および任意のzkVM証明のオーケストレーション。"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core.config import settings
from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.breathing_pipeline import run_breathing_pipeline
from app.services.zkvm_service import ZkVMBreathingService

logger = logging.getLogger(__name__)

DISABLED_ANALYSIS_METHODS = ["wavelet", "music", "fft_cosine_similarity"]
_PRIVATE_INPUT_KEYS = {"certificate_input", "zkvm_input", "zkp_input"}


class VerifiableBreathingService:
    """5-1解析と、設定で有効な証明方式を実行する。"""

    def __init__(
        self,
        pipeline_runner: Callable[..., Dict[str, Any]] = run_breathing_pipeline,
        circom_service_factory: Callable[[], BreathingCertificateService] = lambda: BreathingCertificateService(
            auto_compile=settings.ZKP_AUTO_COMPILE
        ),
        zkvm_service: Optional[ZkVMBreathingService] = None,
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.circom_service_factory = circom_service_factory
        self.zkvm_service = zkvm_service or ZkVMBreathingService()

    async def analyze(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        if path.suffix.lower() != ".csi":
            raise ValueError("5-1 呼吸解析は PicoScenes .csi ファイルのみ対応します")

        zkvm_enabled = settings.CSI_ZKVM_ENABLED
        zkvm_limit_mb = settings.CSI_ZKVM_MAX_FILE_SIZE_MB
        file_size = path.stat().st_size if path.exists() else 0
        exceeds_zkvm_limit = zkvm_limit_mb > 0 and file_size > zkvm_limit_mb * 1024 * 1024
        skip_zkvm = not zkvm_enabled or exceeds_zkvm_limit
        if not zkvm_enabled:
            logger.info("zkVM proof is disabled by configuration")
        elif exceeds_zkvm_limit:
            logger.warning(
                "Skipping zkVM proof for large CSI file: %s bytes exceeds %s MB",
                file_size,
                zkvm_limit_mb,
            )

        runner_parameters = inspect.signature(self.pipeline_runner).parameters.values()
        supports_zkvm_option = any(
            parameter.name == "include_zkvm_input" or parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in runner_parameters
        )
        if supports_zkvm_option:
            pipeline_result = await asyncio.to_thread(
                self.pipeline_runner,
                file_path,
                include_zkvm_input=not skip_zkvm,
            )
        else:
            # Keep lightweight injected runners used by callers/tests compatible.
            pipeline_result = await asyncio.to_thread(self.pipeline_runner, file_path)
        certificate_input = pipeline_result["certificate_input"]
        zkvm_input = pipeline_result.get("zkvm_input")

        if skip_zkvm:
            circom_result = await self._run_circom(certificate_input)
            if not zkvm_enabled:
                zkvm_result: Any = {
                    "status": "disabled",
                    "reason": "disabled_by_configuration",
                }
            else:
                zkvm_result = {
                    "status": "skipped",
                    "reason": "file_too_large",
                    "file_size": file_size,
                    "threshold_mb": zkvm_limit_mb,
                }
        else:
            circom_result, zkvm_result = await asyncio.gather(
                self._run_circom(certificate_input),
                self.zkvm_service.generate_proof(zkvm_input),
                return_exceptions=True,
            )
        proofs = {
            "python_circom": self._normalize_result(circom_result),
            "zkvm": zkvm_result if skip_zkvm else self._normalize_result(zkvm_result),
        }
        circom_completed = proofs["python_circom"]["status"] == "completed"
        zkvm_completed = proofs["zkvm"]["status"] == "completed"
        if circom_completed and (zkvm_completed or not zkvm_enabled):
            status = "completed"
        elif circom_completed or zkvm_completed:
            status = "partial"
        else:
            status = "failed"

        analysis = {key: value for key, value in pipeline_result.items() if key not in _PRIVATE_INPUT_KEYS}
        if zkvm_input is not None:
            analysis["input_commitment"] = zkvm_input["input_commitment"]
        analysis["pipeline"] = "5-1.ipynb"
        analysis["certificate_diagnostics"] = certificate_input.get("diagnostics", {})

        return {
            "status": status,
            "analysis": analysis,
            "proofs": proofs,
            "disabled_methods": list(DISABLED_ANALYSIS_METHODS),
        }

    async def _run_circom(self, certificate_input: Dict[str, Any]) -> Dict[str, Any]:
        service = await asyncio.to_thread(self.circom_service_factory)
        return await service.generate_proof(
            vmd_input=certificate_input["vmdInput"],
            modes=certificate_input["modes"],
            sel=certificate_input["sel"],
        )

    @staticmethod
    def _normalize_result(result: Any) -> Dict[str, Any]:
        if isinstance(result, BaseException):
            logger.warning("Proof branch failed: %s", result)
            return {
                "status": "failed",
                "error": str(result),
                "error_type": type(result).__name__,
            }
        return {"status": "completed", **result}
