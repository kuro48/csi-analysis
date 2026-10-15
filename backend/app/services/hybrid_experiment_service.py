"""Repeatable Python/hybrid/Circom-approximation experiment runner."""

import asyncio
import csv
import hashlib
import inspect
import json
import os
import resource
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core.config import settings
from app.services.breathing_pipeline import collect_pipeline_timings, run_breathing_pipeline
from app.services.committed_breathing_certificate_service import CommittedBreathingCertificateService
from app.services.preprocess_projection_service import PreprocessProjectionService
from app.services.vmd_approx_service import VmdApproxService

_WRITE_LOCK = threading.Lock()
CSV_FIELDS = [
    "experiment_id",
    "measured_at",
    "dataset_id",
    "source_filename",
    "method",
    "status",
    "ground_truth_bpm",
    "estimated_bpm",
    "signed_error_bpm",
    "absolute_error_bpm",
    "within_1_bpm",
    "within_2_bpm",
    "analysis_ms",
    "witness_ms",
    "proof_ms",
    "verification_ms",
    "total_ms",
    "constraint_count",
    "proof_size_bytes",
    "peak_rss_kb",
    "error",
]


class HybridExperimentService:
    def __init__(
        self,
        *,
        pipeline_runner: Callable[[str], Dict[str, Any]] = run_breathing_pipeline,
        committed_factory: Callable[[], CommittedBreathingCertificateService] = CommittedBreathingCertificateService,
        approx_factory: Callable[[], VmdApproxService] = VmdApproxService,
        preprocess_factory: Callable[[], PreprocessProjectionService] = PreprocessProjectionService,
        results_dir: Optional[str] = None,
    ) -> None:
        self.pipeline_runner = pipeline_runner
        self.committed_factory = committed_factory
        self.approx_factory = approx_factory
        self.preprocess_factory = preprocess_factory
        default_dir = Path(__file__).resolve().parents[3] / "research" / "phase2_authenticity" / "results"
        self.results_dir = Path(results_dir or settings.HYBRID_EXPERIMENT_RESULTS_DIR or default_dir)

    async def run(
        self,
        file_path: str,
        *,
        ground_truth_bpm: Optional[float],
        dataset_id: Optional[str],
        source_filename: str,
    ) -> Dict[str, Any]:
        if ground_truth_bpm is not None and not 0 < ground_truth_bpm <= 120:
            raise ValueError("ground_truth_bpm must be greater than 0 and at most 120")
        content_hash = await asyncio.to_thread(self._sha256_file, file_path)
        resolved_dataset_id = dataset_id or content_hash[:16]
        experiment_id = str(uuid.uuid4())
        measured_at = datetime.now(timezone.utc).isoformat()

        pipeline_started = time.perf_counter()
        pipeline_result, stage_timings = await asyncio.to_thread(self._run_pipeline, file_path)
        analysis_ms = (time.perf_counter() - pipeline_started) * 1000
        python_bpm = float(pipeline_result["breathing_rate_bpm"])
        methods = [
            self._method_row(
                method="python_baseline",
                estimated_bpm=python_bpm,
                ground_truth_bpm=ground_truth_bpm,
                analysis_ms=analysis_ms,
            )
        ]

        cert_input = pipeline_result["certificate_input"]
        methods.append(
            await self._proof_method(
                method="python_circom_committed",
                estimated_bpm=python_bpm,
                ground_truth_bpm=ground_truth_bpm,
                analysis_ms=analysis_ms,
                proof_call=lambda: self._generate_with_factory(
                    self.committed_factory,
                    vmd_input=cert_input["vmdInput"],
                    modes=cert_input["modes"],
                    sel=cert_input["sel"],
                ),
            )
        )
        projection_input = pipeline_result["preprocess_projection_input"]
        preprocess_row = await self._proof_method(
            method="circom_preprocess_projection",
            estimated_bpm=None,
            ground_truth_bpm=ground_truth_bpm,
            analysis_ms=analysis_ms,
            proof_call=lambda: self._generate_with_factory(
                self.preprocess_factory,
                centered_x=projection_input["centeredX"],
                weights=projection_input["weights"],
                projected=projection_input["projected"],
            ),
        )
        preprocess_row["diagnostics"] = projection_input["diagnostics"]
        methods.append(preprocess_row)
        projection_commitment = ((preprocess_row.get("proof") or {}).get("projection_commitment") or {}).get("value")
        methods.append(
            await self._proof_method(
                method="circom_vmd_approx",
                estimated_bpm=None,
                ground_truth_bpm=ground_truth_bpm,
                analysis_ms=analysis_ms,
                proof_call=lambda: self._generate_with_factory(
                    self.approx_factory,
                    waveform=pipeline_result["vmd_approx_input"]["waveform"],
                    parent_commitment=projection_commitment,
                ),
                bpm_key="estimatedBpm",
            )
        )

        record = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "measured_at": measured_at,
            "dataset_id": resolved_dataset_id,
            "source_filename": source_filename,
            "source_sha256": content_hash,
            "ground_truth_bpm": ground_truth_bpm,
            "pipeline_stage_timings": stage_timings,
            "pipeline_summary": {
                "n_samples": pipeline_result.get("n_samples"),
                "n_subcarriers_total": pipeline_result.get("n_subcarriers_total"),
                "n_subcarriers_selected": pipeline_result.get("n_subcarriers_selected"),
            },
            "methods": methods,
            "code_version": os.getenv("GIT_COMMIT", "working-tree"),
        }
        await asyncio.to_thread(self._append, record)
        return record

    def _run_pipeline(self, file_path: str) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        with collect_pipeline_timings() as timings:
            parameters = list(inspect.signature(self.pipeline_runner).parameters.values())
            supports_option = any(parameter.name == "include_preprocess_projection_input" for parameter in parameters)
            accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
            if supports_option or accepts_kwargs:
                result = self.pipeline_runner(file_path, include_preprocess_projection_input=True)
            else:
                result = self.pipeline_runner(file_path)
        return result, timings

    @staticmethod
    async def _generate_with_factory(factory: Callable[[], Any], **kwargs: Any) -> Dict[str, Any]:
        service = await asyncio.to_thread(factory)
        return await service.generate_proof(**kwargs)

    async def _proof_method(
        self,
        *,
        method: str,
        estimated_bpm: Optional[float],
        ground_truth_bpm: Optional[float],
        analysis_ms: float,
        proof_call: Callable[[], Any],
        bpm_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            proof_result = await proof_call()
            if bpm_key:
                estimated_bpm = float(proof_result[bpm_key])
            benchmark = proof_result.get("benchmark") or {}
            row = self._method_row(
                method=method,
                estimated_bpm=estimated_bpm,
                ground_truth_bpm=ground_truth_bpm,
                analysis_ms=analysis_ms,
                benchmark=benchmark,
                proof=proof_result.get("proof"),
            )
            row["proof"] = {
                "is_valid": proof_result.get("isValid"),
                "is_normal": proof_result.get("isNormal"),
                "commitment": proof_result.get("commitment"),
                "input_commitment": proof_result.get("inputCommitment"),
                "projection_commitment": proof_result.get("projectionCommitment"),
                "intermediate_hash": proof_result.get("intermediateHash"),
                "parent_commitment": proof_result.get("parentCommitment"),
                "chain_linked": proof_result.get("chainLinked"),
            }
            return row
        except Exception as exc:
            return {
                **self._method_row(
                    method=method,
                    estimated_bpm=estimated_bpm,
                    ground_truth_bpm=ground_truth_bpm,
                    analysis_ms=analysis_ms,
                ),
                "status": "failed",
                "total_ms": round((time.perf_counter() - started) * 1000 + analysis_ms, 3),
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    @staticmethod
    def _method_row(
        *,
        method: str,
        estimated_bpm: Optional[float],
        ground_truth_bpm: Optional[float],
        analysis_ms: float,
        benchmark: Optional[Dict[str, Any]] = None,
        proof: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        benchmark = benchmark or {}
        error = estimated_bpm - ground_truth_bpm if estimated_bpm is not None and ground_truth_bpm is not None else None
        absolute_error = abs(error) if error is not None else None
        proof_size = len(json.dumps(proof, separators=(",", ":")).encode()) if proof is not None else 0
        proof_total = float(benchmark.get("totalMs") or 0)
        return {
            "method": method,
            "status": "completed",
            "estimated_bpm": estimated_bpm,
            "signed_error_bpm": error,
            "absolute_error_bpm": absolute_error,
            "within_1_bpm": absolute_error <= 1 if absolute_error is not None else None,
            "within_2_bpm": absolute_error <= 2 if absolute_error is not None else None,
            "analysis_ms": round(analysis_ms, 3),
            "witness_ms": benchmark.get("witnessGenerationMs"),
            "proof_ms": benchmark.get("proofGenerationMs"),
            "verification_ms": benchmark.get("verificationMs"),
            "total_ms": round(analysis_ms + proof_total, 3),
            "constraint_count": benchmark.get("constraintCount"),
            "proof_size_bytes": proof_size,
            "peak_rss_kb": HybridExperimentService._peak_rss_kb(),
            "error": None,
        }

    @staticmethod
    def _peak_rss_kb() -> int:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # macOS reports bytes; Linux (the production container) reports KiB.
        return value // 1024 if sys.platform == "darwin" else value

    def _append(self, record: Dict[str, Any]) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.results_dir / "runs.jsonl"
        csv_path = self.results_dir / "method_runs.csv"
        with _WRITE_LOCK:
            with jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            write_header = not csv_path.exists() or csv_path.stat().st_size == 0
            with csv_path.open("a", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
                if write_header:
                    writer.writeheader()
                for method in record["methods"]:
                    row = {key: record.get(key) for key in CSV_FIELDS}
                    row.update({key: method[key] for key in CSV_FIELDS if key in method})
                    row["ground_truth_bpm"] = record.get("ground_truth_bpm")
                    writer.writerow(row)

    @staticmethod
    def _sha256_file(file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
