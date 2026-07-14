"""5-1.ipynb 解析と Circom / zkVM 並列証明のオーケストレーション。"""

import asyncio
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
    """5-1 を1回実行し、2つの証明方式を同時に起動する。"""

    def __init__(
        self,
        pipeline_runner: Callable[[str], Dict[str, Any]] = run_breathing_pipeline,
        circom_service_factory: Callable[[], BreathingCertificateService] = lambda: BreathingCertificateService(
            auto_compile=settings.ZKP_AUTO_COMPILE
        ),
        zkvm_service: Optional[ZkVMBreathingService] = None,
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.circom_service_factory = circom_service_factory
        self.zkvm_service = zkvm_service or ZkVMBreathingService()

    async def analyze(self, file_path: str) -> Dict[str, Any]:
        if Path(file_path).suffix.lower() != ".csi":
            raise ValueError("5-1 呼吸解析は PicoScenes .csi ファイルのみ対応します")

        pipeline_result = await asyncio.to_thread(self.pipeline_runner, file_path)
        certificate_input = pipeline_result["certificate_input"]
        zkvm_input = pipeline_result["zkvm_input"]

        circom_result, zkvm_result = await asyncio.gather(
            self._run_circom(certificate_input),
            self.zkvm_service.generate_proof(zkvm_input),
            return_exceptions=True,
        )
        proofs = {
            "python_circom": self._normalize_result(circom_result),
            "zkvm": self._normalize_result(zkvm_result),
        }
        completed = sum(item["status"] == "completed" for item in proofs.values())
        status = "completed" if completed == 2 else "partial" if completed == 1 else "failed"

        analysis = {key: value for key, value in pipeline_result.items() if key not in _PRIVATE_INPUT_KEYS}
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
