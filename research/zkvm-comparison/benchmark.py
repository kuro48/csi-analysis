#!/usr/bin/env python3
"""実CSIで Python+Circom と zkVM の処理時間を1回ずつ計測する。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gc
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path("/app") if Path("/app/app").is_dir() else REPO_ROOT / "backend"
ZKP_ROOT = Path("/zkp") if Path("/zkp/circuits").is_dir() else REPO_ROOT / "zkp"
ZKVM_BINARY = (
    Path("/opt/csi-zkvm/csi-zkvm-host")
    if Path("/opt/csi-zkvm/csi-zkvm-host").is_file()
    else REPO_ROOT / "zkvm" / "target" / "release" / "csi-zkvm-host"
)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


async def read_and_forward_stderr(stream: asyncio.StreamReader) -> bytes:
    chunks = []
    while True:
        chunk = await stream.readline()
        if not chunk:
            break
        chunks.append(chunk)
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()
    return b"".join(chunks)


async def measure_python_circom(matrix: Any) -> dict[str, Any]:
    from app.services.breathing_certificate_service import BreathingCertificateService
    from app.services.breathing_pipeline import (
        collect_pipeline_timings,
        run_breathing_pipeline_from_matrix,
    )

    total_started = time.perf_counter()
    try:
        analysis_started = time.perf_counter()

        def run_analysis() -> tuple[dict[str, Any], list[dict[str, Any]]]:
            with collect_pipeline_timings() as process_timings:
                result = run_breathing_pipeline_from_matrix(
                    matrix,
                    include_zkvm_input=False,
                )
            return result, process_timings

        with open(os.devnull, "w", encoding="utf-8") as null_output:
            with contextlib.redirect_stdout(null_output):
                pipeline_result, process_timings = await asyncio.to_thread(run_analysis)
        analysis_seconds = time.perf_counter() - analysis_started

        started = time.perf_counter()
        service = await asyncio.to_thread(
            BreathingCertificateService,
            zkp_dir=str(ZKP_ROOT),
            auto_compile=False,
        )
        service_init_seconds = time.perf_counter() - started

        certificate = pipeline_result["certificate_input"]
        started = time.perf_counter()
        circuit_input = service._prepare_input(
            certificate["vmdInput"],
            certificate["modes"],
            certificate["sel"],
        )
        input_prepare_seconds = time.perf_counter() - started

        started = time.perf_counter()
        witness_file = await service._generate_witness(circuit_input)
        witness_seconds = time.perf_counter() - started

        started = time.perf_counter()
        proof, public_signals = await service._generate_groth16_proof(witness_file)
        prove_seconds = time.perf_counter() - started

        started = time.perf_counter()
        is_valid = await service.verify_proof(proof, public_signals)
        verify_seconds = time.perf_counter() - started
        if not is_valid:
            raise RuntimeError("generated Circom proof failed local verification")

        return {
            "status": "completed",
            "total_seconds": time.perf_counter() - total_started,
            "timings": {
                "python_analysis_seconds": analysis_seconds,
                "python_processes": process_timings,
                "circom_service_init_seconds": service_init_seconds,
                "circom_input_prepare_seconds": input_prepare_seconds,
                "circom_witness_seconds": witness_seconds,
                "circom_prove_seconds": prove_seconds,
                "circom_verify_seconds": verify_seconds,
            },
            "result": {
                "is_valid": True,
                "is_normal": bool(int(public_signals[0])) if public_signals else False,
                "breathing_rate_bpm": float(pipeline_result["breathing_rate_bpm"]),
            },
        }
    except Exception as exc:
        return {
            "status": "failed",
            "total_seconds": time.perf_counter() - total_started,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def measure_zkvm(matrix: Any) -> dict[str, Any]:
    from app.services.breathing_pipeline import prepare_zkvm_input

    total_started = time.perf_counter()
    try:
        if not ZKVM_BINARY.is_file():
            raise FileNotFoundError(f"zkVM binary not found: {ZKVM_BINARY}")

        started = time.perf_counter()
        pipeline_input = await asyncio.to_thread(prepare_zkvm_input, matrix)
        input_prepare_seconds = time.perf_counter() - started

        with tempfile.TemporaryDirectory(prefix="csi-zkvm-benchmark-") as temp_name:
            input_path = Path(temp_name) / "input.json"
            started = time.perf_counter()
            input_path.write_text(
                json.dumps(pipeline_input, separators=(",", ":")),
                encoding="utf-8",
            )
            input_write_seconds = time.perf_counter() - started

            started = time.perf_counter()
            process = await asyncio.create_subprocess_exec(
                str(ZKVM_BINARY),
                "prove",
                str(input_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stderr_task = asyncio.create_task(read_and_forward_stderr(process.stderr))
            stdout = await process.stdout.read()
            await process.wait()
            stderr = await stderr_task
            prove_and_verify_seconds = time.perf_counter() - started

        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"zkVM failed (exit={process.returncode}): {detail}")

        result = json.loads(stdout)
        if not result.get("isValid"):
            raise RuntimeError("zkVM receipt verification failed")

        return {
            "status": "completed",
            "total_seconds": time.perf_counter() - total_started,
            "timings": {
                "input_prepare_seconds": input_prepare_seconds,
                "input_json_write_seconds": input_write_seconds,
                "prove_and_verify_seconds": prove_and_verify_seconds,
            },
            "result": {
                "is_valid": True,
                "is_normal": bool(result.get("isNormal")),
            },
        }
    except Exception as exc:
        return {
            "status": "failed",
            "total_seconds": time.perf_counter() - total_started,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def measure(csi_file: Path, output: Path) -> dict[str, Any]:
    backend_root = str(BACKEND_ROOT.resolve())
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from app.services.breathing_pipeline import load_csi_matrix

    if not csi_file.is_file() or csi_file.suffix.lower() != ".csi":
        raise FileNotFoundError(f"valid .csi file not found: {csi_file}")

    started = time.perf_counter()
    matrix = load_csi_matrix(str(csi_file))
    csi_read_seconds = time.perf_counter() - started
    gc.collect()

    payload = {
        "input": {
            "csi_file": str(csi_file.resolve()),
            "samples": int(matrix.shape[0]),
            "subcarriers": int(matrix.shape[1]),
        },
        "csi_read_seconds": csi_read_seconds,
        "python_circom": await measure_python_circom(matrix),
        "zkvm": await measure_zkvm(matrix),
    }
    payload["status"] = (
        "completed"
        if payload["python_circom"]["status"] == "completed"
        and payload["zkvm"]["status"] == "completed"
        else "completed_with_failures"
    )
    atomic_write_json(output, payload)
    print(f"[result] {output}")
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csi-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    asyncio.run(measure(args.csi_file, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
