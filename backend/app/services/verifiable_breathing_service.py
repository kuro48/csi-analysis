"""5-1 / Lomb--Scargle比較解析とCircom、および任意のzkVM証明の統合。"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core.config import settings
from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.breathing_pipeline import run_breathing_pipeline
from app.services.lomb_scargle_certificate_service import LombScargleCertificateService
from app.services.lomb_scargle_pipeline import run_lomb_scargle_pipeline
from app.services.zkvm_service import ZkVMBreathingService

logger = logging.getLogger(__name__)

DISABLED_ANALYSIS_METHODS = ["wavelet", "music", "fft_cosine_similarity"]
_PRIVATE_INPUT_KEYS = {"certificate_input", "zkvm_input", "zkp_input", "_lomb_scargle_input"}


class VerifiableBreathingService:
    """5-1とLomb--Scargleを同じCSIで解析し、各Circom判定を返す。"""

    def __init__(
        self,
        pipeline_runner: Callable[..., Dict[str, Any]] = run_breathing_pipeline,
        circom_service_factory: Callable[[], BreathingCertificateService] = lambda: BreathingCertificateService(
            auto_compile=settings.ZKP_AUTO_COMPILE
        ),
        lomb_scargle_runner: Callable[[str], Dict[str, Any]] = run_lomb_scargle_pipeline,
        lomb_circom_service_factory: Callable[
            [], LombScargleCertificateService
        ] = lambda: LombScargleCertificateService(auto_compile=settings.ZKP_AUTO_COMPILE),
        zkvm_service: Optional[ZkVMBreathingService] = None,
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.circom_service_factory = circom_service_factory
        self.lomb_scargle_runner = lomb_scargle_runner
        self.lomb_circom_service_factory = lomb_circom_service_factory
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

        runner_parameters = list(inspect.signature(self.pipeline_runner).parameters.values())
        accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in runner_parameters)
        supports_zkvm_option = any(parameter.name == "include_zkvm_input" for parameter in runner_parameters)
        supports_lomb_option = any(parameter.name == "include_lomb_scargle_input" for parameter in runner_parameters)
        if supports_zkvm_option or supports_lomb_option or accepts_kwargs:
            runner_options: Dict[str, Any] = {}
            if supports_zkvm_option or accepts_kwargs:
                runner_options["include_zkvm_input"] = not skip_zkvm
            if supports_lomb_option or accepts_kwargs:
                runner_options["include_lomb_scargle_input"] = True
            pipeline_result = await asyncio.to_thread(
                self.pipeline_runner,
                file_path,
                **runner_options,
            )
        else:
            # Keep lightweight injected runners used by callers/tests compatible.
            pipeline_result = await asyncio.to_thread(self.pipeline_runner, file_path)
        certificate_input = pipeline_result["certificate_input"]
        zkvm_input = pipeline_result.get("zkvm_input")

        lomb_input = pipeline_result.get("_lomb_scargle_input")
        try:
            # Production path: the existing pipeline has already performed CSI loading,
            # amplitude extraction, SNR selection, bandpass, and PCA. Injected legacy
            # runners used by tests/callers continue to receive the file path.
            lomb_source = lomb_input if lomb_input is not None else file_path
            lomb_result: Any = await asyncio.to_thread(self.lomb_scargle_runner, lomb_source)
            lomb_certificate_input = lomb_result["certificate_input"]
        except Exception as exc:
            logger.warning("Lomb-Scargle analysis failed: %s", exc, exc_info=True)
            lomb_result = exc
            lomb_certificate_input = None

        if skip_zkvm:
            circom_task = self._run_circom(certificate_input)
            if lomb_certificate_input is None:
                (circom_result,) = await asyncio.gather(circom_task, return_exceptions=True)
                lomb_circom_result: Any = lomb_result
            else:
                circom_result, lomb_circom_result = await asyncio.gather(
                    circom_task,
                    self._run_lomb_circom(lomb_certificate_input),
                    return_exceptions=True,
                )
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
            proof_tasks = [
                self._run_circom(certificate_input),
                self.zkvm_service.generate_proof(zkvm_input),
            ]
            if lomb_certificate_input is not None:
                proof_tasks.append(self._run_lomb_circom(lomb_certificate_input))
            proof_results = await asyncio.gather(*proof_tasks, return_exceptions=True)
            circom_result, zkvm_result = proof_results[:2]
            lomb_circom_result = proof_results[2] if len(proof_results) == 3 else lomb_result
        proofs = {
            "python_circom": self._normalize_result(circom_result),
            "lomb_scargle_circom": self._normalize_result(lomb_circom_result),
            "zkvm": zkvm_result if skip_zkvm else self._normalize_result(zkvm_result),
        }
        circom_completed = proofs["python_circom"]["status"] == "completed"
        lomb_circom_completed = proofs["lomb_scargle_circom"]["status"] == "completed"
        zkvm_completed = proofs["zkvm"]["status"] == "completed"
        if circom_completed and lomb_circom_completed and (zkvm_completed or not zkvm_enabled):
            status = "completed"
        elif circom_completed or lomb_circom_completed or zkvm_completed:
            status = "partial"
        else:
            status = "failed"

        analysis = {key: value for key, value in pipeline_result.items() if key not in _PRIVATE_INPUT_KEYS}
        if zkvm_input is not None:
            analysis["input_commitment"] = zkvm_input["input_commitment"]
        analysis["pipeline"] = "5-1.ipynb"
        analysis["certificate_diagnostics"] = certificate_input.get("diagnostics", {})
        if isinstance(lomb_result, BaseException):
            analysis["lomb_scargle"] = {
                "status": "failed",
                "error": str(lomb_result),
                "error_type": type(lomb_result).__name__,
            }
        else:
            lomb_analysis = {key: value for key, value in lomb_result.items() if key not in _PRIVATE_INPUT_KEYS}
            analysis["lomb_scargle"] = {"status": "completed", **lomb_analysis}
            current_bpm = pipeline_result.get("breathing_rate_bpm")
            lomb_bpm = lomb_result.get("breathing_rate_bpm")
            analysis["algorithm_comparison"] = {
                "current_algorithm": "5-1.ipynb",
                "lomb_scargle_algorithm": lomb_result.get("algorithm_version"),
                "current_breathing_rate_bpm": current_bpm,
                "lomb_scargle_breathing_rate_bpm": lomb_bpm,
                "absolute_difference_bpm": (
                    abs(float(current_bpm) - float(lomb_bpm))
                    if current_bpm is not None and lomb_bpm is not None
                    else None
                ),
                "current_is_normal": proofs["python_circom"].get("isNormal"),
                "lomb_scargle_is_normal": proofs["lomb_scargle_circom"].get("isNormal"),
            }

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

    async def _run_lomb_circom(self, certificate_input: Dict[str, Any]) -> Dict[str, Any]:
        service = await asyncio.to_thread(self.lomb_circom_service_factory)
        return await service.generate_proof(powers=certificate_input["powers"])

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
