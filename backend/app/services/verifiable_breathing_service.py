"""5-1 / Lomb--Scargle比較解析とCircom証明の統合。"""

import asyncio
import inspect
import logging
import math
from pathlib import Path
from typing import Any, Callable, Dict

from app.core.config import settings
from app.services.breathing_pipeline import run_breathing_pipeline
from app.services.lomb_scargle_certificate_service import LombScargleCertificateService
from app.services.lomb_scargle_pipeline import run_lomb_scargle_pipeline
from app.services.preprocess_projection_service import PreprocessProjectionService
from app.services.vmd_approx_service import VmdApproxService

logger = logging.getLogger(__name__)

DISABLED_ANALYSIS_METHODS = ["wavelet", "music", "fft_cosine_similarity"]
_PRIVATE_INPUT_KEYS = {
    "certificate_input",
    "zkp_input",
    "vmd_approx_input",
    "preprocess_projection_input",
    "_lomb_scargle_input",
}


def attach_bpm_evaluation(result: Dict[str, Any], ground_truth_bpm: float) -> Dict[str, Any]:
    """解析後のレスポンスへ、表出力しやすい正解値・計測値の行を追加する。

    正解値は解析パイプラインへ渡さず、この関数を解析完了後にだけ呼び出す。
    """

    truth = float(ground_truth_bpm)
    if not math.isfinite(truth) or not 0 < truth <= 120:
        raise ValueError("正解BPMは0より大きく120以下で指定してください")

    analysis = result.get("analysis") or {}
    lomb_analysis = analysis.get("lomb_scargle") or {}

    measurements = [
        ("5-1", "5-1", analysis.get("breathing_rate_bpm")),
        ("lomb_scargle", "Lomb–Scargle", lomb_analysis.get("breathing_rate_bpm")),
    ]
    rows = []
    for method, label, measured_value in measurements:
        measured = float(measured_value) if measured_value is not None else None
        rows.append(
            {
                "method": method,
                "method_label": label,
                "ground_truth_bpm": truth,
                "measured_bpm": measured,
                "signed_error_bpm": measured - truth if measured is not None else None,
                "absolute_error_bpm": abs(measured - truth) if measured is not None else None,
            }
        )

    result["bpm_evaluation"] = {
        "ground_truth_bpm": truth,
        "rows": rows,
    }
    return result


class VerifiableBreathingService:
    """5-1とLomb--Scargleを同じCSIで解析し、各Circom判定を返す。"""

    def __init__(
        self,
        pipeline_runner: Callable[..., Dict[str, Any]] = run_breathing_pipeline,
        circom_service_factory: Callable[[], VmdApproxService] = lambda: VmdApproxService(
            auto_compile=settings.ZKP_AUTO_COMPILE
        ),
        lomb_scargle_runner: Callable[[str], Dict[str, Any]] = run_lomb_scargle_pipeline,
        lomb_circom_service_factory: Callable[
            [], LombScargleCertificateService
        ] = lambda: LombScargleCertificateService(auto_compile=settings.ZKP_AUTO_COMPILE),
        preprocess_circom_service_factory: Callable[
            [], PreprocessProjectionService
        ] = lambda: PreprocessProjectionService(auto_compile=settings.ZKP_AUTO_COMPILE),
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.circom_service_factory = circom_service_factory
        self.lomb_scargle_runner = lomb_scargle_runner
        self.lomb_circom_service_factory = lomb_circom_service_factory
        self.preprocess_circom_service_factory = preprocess_circom_service_factory

    async def analyze(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        if path.suffix.lower() != ".csi":
            raise ValueError("5-1 呼吸解析は PicoScenes .csi ファイルのみ対応します")

        runner_parameters = list(inspect.signature(self.pipeline_runner).parameters.values())
        accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in runner_parameters)
        supports_lomb_option = any(parameter.name == "include_lomb_scargle_input" for parameter in runner_parameters)
        supports_preprocess_option = any(
            parameter.name == "include_preprocess_projection_input" for parameter in runner_parameters
        )
        pipeline_options: Dict[str, bool] = {}
        if supports_lomb_option or accepts_kwargs:
            pipeline_options["include_lomb_scargle_input"] = True
        if supports_preprocess_option or accepts_kwargs:
            pipeline_options["include_preprocess_projection_input"] = True
        if pipeline_options:
            pipeline_result = await asyncio.to_thread(
                self.pipeline_runner,
                file_path,
                **pipeline_options,
            )
        else:
            # Keep lightweight injected runners used by callers/tests compatible.
            pipeline_result = await asyncio.to_thread(self.pipeline_runner, file_path)
        certificate_input = pipeline_result["certificate_input"]

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

        projection_input = pipeline_result.get("preprocess_projection_input")
        if projection_input is None:
            preprocess_circom_result: Any = ValueError("preprocess projection input is unavailable")
        else:
            (preprocess_circom_result,) = await asyncio.gather(
                self._run_preprocess_circom(projection_input),
                return_exceptions=True,
            )

        if isinstance(preprocess_circom_result, BaseException):
            parent_commitment = None
        else:
            parent_commitment = str(preprocess_circom_result["projectionCommitment"]["value"])

        if parent_commitment is None:
            chain_error = RuntimeError("preprocess projection proof did not provide a parent commitment")
            circom_result: Any = chain_error
            lomb_circom_result: Any = lomb_result if isinstance(lomb_result, BaseException) else chain_error
        else:
            circom_task = self._run_circom(pipeline_result["vmd_approx_input"], parent_commitment)
            if lomb_certificate_input is None:
                (circom_result,) = await asyncio.gather(circom_task, return_exceptions=True)
                lomb_circom_result = lomb_result
            else:
                circom_result, lomb_circom_result = await asyncio.gather(
                    circom_task,
                    self._run_lomb_circom(lomb_certificate_input, parent_commitment),
                    return_exceptions=True,
                )

        proofs = {
            "preprocess_projection": self._normalize_result(preprocess_circom_result),
            "python_circom": self._normalize_result(circom_result),
            "lomb_scargle_circom": self._normalize_result(lomb_circom_result),
        }
        proof_chain = self._build_proof_chain(proofs)
        completed = [proof["status"] == "completed" for proof in proofs.values()]
        if all(completed) and proof_chain["status"] == "verified":
            status = "completed"
        elif any(completed):
            status = "partial"
        else:
            status = "failed"

        analysis = {key: value for key, value in pipeline_result.items() if key not in _PRIVATE_INPUT_KEYS}
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
            "proofChain": proof_chain,
            "intermediateHashes": {
                proof_name: proof_result["intermediateHash"]
                for proof_name, proof_result in proofs.items()
                if proof_result.get("status") == "completed" and "intermediateHash" in proof_result
            },
            "disabled_methods": list(DISABLED_ANALYSIS_METHODS),
        }

    async def _run_circom(self, vmd_input: Dict[str, Any], parent_commitment: str) -> Dict[str, Any]:
        service = await asyncio.to_thread(self.circom_service_factory)
        return await service.generate_proof(
            waveform=vmd_input["waveform"],
            parent_commitment=parent_commitment,
        )

    async def _run_lomb_circom(self, certificate_input: Dict[str, Any], parent_commitment: str) -> Dict[str, Any]:
        service = await asyncio.to_thread(self.lomb_circom_service_factory)
        return await service.generate_proof(
            samples=certificate_input["samples"],
            timestamps_ms=certificate_input["timestampsMs"],
            parent_commitment=parent_commitment,
        )

    async def _run_preprocess_circom(self, projection_input: Dict[str, Any]) -> Dict[str, Any]:
        service = await asyncio.to_thread(self.preprocess_circom_service_factory)
        return await service.generate_proof(
            centered_x=projection_input["centeredX"],
            weights=projection_input["weights"],
            projected=projection_input["projected"],
        )

    @staticmethod
    def _build_proof_chain(proofs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        preprocess = proofs["preprocess_projection"]
        projection = preprocess.get("projectionCommitment") or {}
        parent = str(projection.get("value")) if projection.get("value") is not None else None
        edges = []
        for target in ("python_circom", "lomb_scargle_circom"):
            child = proofs[target]
            child_parent = child.get("parentCommitment")
            edges.append(
                {
                    "from": "preprocess_projection",
                    "to": target,
                    "commitment": parent,
                    "verified": (
                        parent is not None
                        and child.get("status") == "completed"
                        and child.get("isValid") is True
                        and str(child_parent) == parent
                    ),
                }
            )
        verified = (
            preprocess.get("status") == "completed"
            and preprocess.get("isValid") is True
            and all(edge["verified"] for edge in edges)
        )
        return {
            "status": "verified" if verified else "failed",
            "rootInputCommitment": (preprocess.get("inputCommitment") or {}).get("value"),
            "branchCommitment": parent,
            "edges": edges,
            "transitionScope": "commitment continuity; reduced-projection to branch-input transformation is not proved",
        }

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
