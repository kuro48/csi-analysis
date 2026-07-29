#!/usr/bin/env python3
"""Python+Circom と RISC Zero zkVM の再現可能な時間計測。

本番コードには計測処理を混ぜず、既存のサービスと CLI をそのまま呼び出す。
実行環境に重い依存があるため、NumPy や backend モジュールは execution
サブコマンドを選んだ時だけ import する。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import gc
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Sequence


SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKEND_ROOT = Path("/app") if Path("/app/app").is_dir() else REPO_ROOT / "backend"
DEFAULT_ZKP_ROOT = Path("/zkp") if Path("/zkp/circuits").is_dir() else REPO_ROOT / "zkp"
DEFAULT_ZKVM_BINARY = (
    Path("/opt/csi-zkvm/csi-zkvm-host")
    if Path("/opt/csi-zkvm/csi-zkvm-host").is_file()
    else REPO_ROOT / "zkvm" / "target" / "release" / "csi-zkvm-host"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def percentile(values: Sequence[float], fraction: float) -> float:
    """線形補間 percentile。外部統計依存を増やさないための小さな実装。"""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_runs(runs: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    keys = sorted(
        {
            key
            for run in runs
            for key, value in run.items()
            if key.endswith("_seconds") and isinstance(value, (int, float))
        }
    )
    summary: dict[str, dict[str, float]] = {}
    for key in keys:
        values = [float(run[key]) for run in runs if isinstance(run.get(key), (int, float))]
        summary[key] = {
            "count": len(values),
            "min": min(values),
            "median": statistics.median(values),
            "mean": statistics.fmean(values),
            "p95": percentile(values, 0.95),
            "max": max(values),
        }
    return summary


def environment_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
    }
    memory_limit = Path("/sys/fs/cgroup/memory.max")
    if memory_limit.is_file():
        raw_limit = memory_limit.read_text(encoding="utf-8").strip()
        metadata["cgroup_memory_limit_bytes"] = int(raw_limit) if raw_limit.isdigit() else raw_limit
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.is_file():
        for line in cpu_info.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                metadata["cpu_model"] = line.split(":", 1)[-1].strip()
                break
    return metadata


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_timed_json(path: Path, payload: dict[str, Any]) -> float:
    """Write a result JSON and store the primary write duration in that JSON."""
    started = time.perf_counter()
    atomic_write_json(path, payload)
    elapsed = time.perf_counter() - started
    payload["result_output_seconds"] = elapsed
    payload["result_output_metadata_rewrite_excluded"] = True
    atomic_write_json(path, payload)
    return elapsed


def default_output(prefix: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    result_root = Path("/results") if Path("/results").is_dir() else Path(__file__).resolve().parent / "results"
    return result_root / f"{prefix}-{stamp}.json"


def command_version(command: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None


def run_timed_command(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path | None = None,
) -> dict[str, Any]:
    print(f"[build] {name}: {' '.join(command)}", flush=True)
    started = time.perf_counter()
    result = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    elapsed = time.perf_counter() - started
    output = result.stdout or ""
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n## {name}\n$ {' '.join(command)}\n")
            log.write(output)
    if result.returncode != 0:
        tail = "\n".join(output.splitlines()[-40:])
        raise RuntimeError(f"{name} failed (exit={result.returncode})\n{tail}")
    return {
        "name": name,
        "command": list(command),
        "wall_seconds": elapsed,
    }


def resolve_executable(name: str, fallback: Path | None = None) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if fallback is not None and fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(f"required executable not found: {name}")


def build_circom(args: argparse.Namespace) -> dict[str, Any]:
    zkp_root = args.zkp_root.resolve()
    circuit = zkp_root / "circuits" / "csi_breathing_certificate.circom"
    ptau = args.ptau.resolve()
    for required in (circuit, ptau, zkp_root / "node_modules"):
        if not required.exists():
            raise FileNotFoundError(f"required Circom build input not found: {required}")

    circom = resolve_executable("circom")
    snarkjs = resolve_executable("snarkjs", zkp_root / "node_modules" / ".bin" / "snarkjs")
    output = args.output or default_output("build-circom")
    log_path = output.with_suffix(".log")
    started_at = utc_now()

    if args.artifact_dir:
        artifact_context: contextlib.AbstractContextManager[str] = contextlib.nullcontext(
            str(args.artifact_dir.resolve())
        )
        args.artifact_dir.mkdir(parents=True, exist_ok=True)
    else:
        artifact_context = tempfile.TemporaryDirectory(prefix="csi-circom-build-")

    phases: list[dict[str, Any]] = []
    with artifact_context as artifact_name:
        artifact_dir = Path(artifact_name)
        phases.append(
            run_timed_command(
                "circom_compile",
                [
                    circom,
                    str(circuit),
                    "--r1cs",
                    "--wasm",
                    "--sym",
                    "--c",
                    "-o",
                    str(artifact_dir),
                    "-l",
                    str(zkp_root / "node_modules"),
                ],
                cwd=zkp_root,
                log_path=log_path,
            )
        )
        r1cs = artifact_dir / "csi_breathing_certificate.r1cs"
        initial_zkey = artifact_dir / "csi_breathing_certificate_0000.zkey"
        final_zkey = artifact_dir / "csi_breathing_certificate_final.zkey"
        verification_key = artifact_dir / "csi_breathing_certificate_verification_key.json"
        phases.append(
            run_timed_command(
                "groth16_setup",
                [snarkjs, "groth16", "setup", str(r1cs), str(ptau), str(initial_zkey)],
                cwd=zkp_root,
                log_path=log_path,
            )
        )
        phases.append(
            run_timed_command(
                "zkey_contribute",
                [
                    snarkjs,
                    "zkey",
                    "contribute",
                    str(initial_zkey),
                    str(final_zkey),
                    "--name=benchmark-only",
                    "-e=csi-zkvm-comparison-benchmark-only",
                ],
                cwd=zkp_root,
                log_path=log_path,
            )
        )
        phases.append(
            run_timed_command(
                "verification_key_export",
                [snarkjs, "zkey", "export", "verificationkey", str(final_zkey), str(verification_key)],
                cwd=zkp_root,
                log_path=log_path,
            )
        )
        artifact_sizes = {
            path.name: path.stat().st_size
            for path in (r1cs, final_zkey, verification_key)
            if path.exists()
        }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "build",
        "method": "python_circom",
        "started_at": started_at,
        "finished_at": utc_now(),
        "definition": (
            "Python依存とnpm install、Powers of Tau生成は除外。"
            "Circomコンパイル、Groth16 setup、contribution、検証鍵exportを計測。"
        ),
        "environment": environment_metadata(),
        "versions": {
            "circom": command_version([circom, "--version"]),
            "snarkjs": command_version([snarkjs, "--version"]),
        },
        "inputs": {
            "circuit": str(circuit),
            "circuit_sha256": file_sha256(circuit),
            "ptau": str(ptau),
            "ptau_size_bytes": ptau.stat().st_size,
        },
        "phases": phases,
        "total_build_seconds": sum(float(phase["wall_seconds"]) for phase in phases),
        "artifact_sizes_bytes": artifact_sizes,
    }
    write_timed_json(output, payload)
    print(f"[result] {output}")
    return payload


def build_zkvm(args: argparse.Namespace) -> dict[str, Any]:
    docker = resolve_executable("docker")
    output = args.output or default_output("build-zkvm")
    log_path = output.with_suffix(".log")
    command = [
        docker,
        "build",
        "--platform",
        args.platform,
        "--tag",
        args.image_tag,
    ]
    if args.no_cache:
        command.append("--no-cache")
    command.extend(["--file", str(REPO_ROOT / "zkvm" / "Dockerfile"), str(REPO_ROOT / "zkvm")])

    started_at = utc_now()
    phase = run_timed_command(
        "zkvm_docker_build",
        command,
        cwd=REPO_ROOT,
        log_path=log_path,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "build",
        "method": "zkvm",
        "started_at": started_at,
        "finished_at": utc_now(),
        "definition": (
            "本番 zkvm/Dockerfile のフルビルド。--no-cache 指定時は OS package、"
            "RISC Zero toolchain、Cargo依存取得も含む deployment build time。"
        ),
        "environment": environment_metadata(),
        "versions": {"docker": command_version([docker, "--version"])},
        "cache_mode": "clean" if args.no_cache else "docker_cache_enabled",
        "platform": args.platform,
        "image_tag": args.image_tag,
        "phases": [phase],
        "total_build_seconds": float(phase["wall_seconds"]),
    }
    write_timed_json(output, payload)
    print(f"[result] {output}")
    return payload


def install_backend_path(backend_root: Path) -> None:
    root = str(backend_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def load_execution_matrix(args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    if args.csi_file.suffix.lower() != ".csi":
        raise ValueError(f"input must be a PicoScenes .csi file: {args.csi_file}")
    if not args.csi_file.is_file():
        raise FileNotFoundError(f"CSI input not found: {args.csi_file}")

    from app.services.breathing_pipeline import load_csi_matrix

    source = args.csi_file.resolve()
    csi_read_started = time.perf_counter()
    matrix = load_csi_matrix(str(source))
    csi_read_seconds = time.perf_counter() - csi_read_started
    source_hash_started = time.perf_counter()
    source_sha256 = file_sha256(source)
    source_hash_seconds = time.perf_counter() - source_hash_started
    subset_started = time.perf_counter()
    metadata: dict[str, Any] = {
        "kind": "picoscenes_csi",
        "source": str(source),
        "source_size_bytes": source.stat().st_size,
        "source_sha256": source_sha256,
    }

    rows = slice(None, args.sample_limit) if args.sample_limit else slice(None)
    columns = slice(None, args.subcarrier_limit) if args.subcarrier_limit else slice(None)
    # PicoScenes 全行列の view を残すと、limit 後も数百 MB の backing array が
    # RISC Zero の proving 中に保持される。計測対象だけを所有する配列へコピーする。
    if args.sample_limit or args.subcarrier_limit:
        matrix = np.array(matrix[rows, columns], copy=True, order="C")
    else:
        matrix = np.ascontiguousarray(matrix)
    subset_seconds = time.perf_counter() - subset_started
    gc.collect()
    metadata.update(
        {
            "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
            "dtype": str(matrix.dtype),
            "matrix_bytes": int(matrix.nbytes),
            "csi_read_seconds": csi_read_seconds,
            "source_hash_seconds": source_hash_seconds,
            "subset_copy_seconds": subset_seconds,
            "load_seconds_excluded": csi_read_seconds,
            "sample_limit": args.sample_limit,
            "subcarrier_limit": args.subcarrier_limit,
        }
    )
    return matrix, metadata


async def run_python_circom_once(
    matrix: Any,
    *,
    zkp_root: Path,
    verbose: bool,
) -> dict[str, Any]:
    from app.services.breathing_certificate_service import BreathingCertificateService
    from app.services.breathing_pipeline import (
        collect_pipeline_timings,
        run_breathing_pipeline_from_matrix,
    )

    gc.collect()
    total_started = time.perf_counter()
    with contextlib.ExitStack() as stack:
        if not verbose:
            null_output = stack.enter_context(open(os.devnull, "w"))
            stack.enter_context(contextlib.redirect_stdout(null_output))
        try:
            started = time.perf_counter()

            def run_pipeline_with_timings() -> tuple[dict[str, Any], list[dict[str, Any]]]:
                with collect_pipeline_timings() as collected:
                    result = run_breathing_pipeline_from_matrix(
                        matrix,
                        include_zkvm_input=False,
                    )
                return result, collected

            pipeline_result, pipeline_process_timings = await asyncio.to_thread(
                run_pipeline_with_timings
            )
            python_seconds = time.perf_counter() - started

            service_started = time.perf_counter()
            service = await asyncio.to_thread(
                BreathingCertificateService,
                zkp_dir=str(zkp_root),
                auto_compile=False,
            )
            service_init_seconds = time.perf_counter() - service_started
            certificate = pipeline_result["certificate_input"]
            circuit_input_prepare_start = time.perf_counter()
            circuit_input = service._prepare_input(
                certificate["vmdInput"],
                certificate["modes"],
                certificate["sel"],
            )
            circuit_input_prepare_seconds = (
                time.perf_counter() - circuit_input_prepare_start
            )

            started = time.perf_counter()
            witness_file = await service._generate_witness(circuit_input)
            witness_seconds = time.perf_counter() - started

            started = time.perf_counter()
            proof, public_signals = await service._generate_groth16_proof(witness_file)
            prove_seconds = time.perf_counter() - started

            started = time.perf_counter()
            is_valid = await service.verify_proof(proof, public_signals)
            verify_seconds = time.perf_counter() - started
        except Exception:
            raise

    total_seconds = time.perf_counter() - total_started
    if not is_valid:
        raise RuntimeError("generated Circom proof failed local verification")
    return {
        "method": "python_circom",
        "python_analysis_seconds": python_seconds,
        "python_analysis_unattributed_seconds": max(
            0.0,
            python_seconds
            - sum(float(item["seconds"]) for item in pipeline_process_timings),
        ),
        "python_process_timings": pipeline_process_timings,
        "circom_service_init_seconds": service_init_seconds,
        "circom_input_prepare_seconds": circuit_input_prepare_seconds,
        "circom_witness_seconds": witness_seconds,
        "circom_prove_seconds": prove_seconds,
        "circom_verify_seconds": verify_seconds,
        "total_execution_seconds": total_seconds,
        "is_valid": bool(is_valid),
        "is_normal": bool(int(public_signals[0])) if public_signals else False,
        "breathing_rate_bpm": float(pipeline_result["breathing_rate_bpm"]),
        "certificate_diagnostics": certificate.get("diagnostics", {}),
    }


async def run_zkvm_once(
    matrix: Any,
    *,
    binary: Path,
) -> dict[str, Any]:
    from app.services.breathing_pipeline import prepare_zkvm_input

    gc.collect()
    total_started = time.perf_counter()
    started = time.perf_counter()
    pipeline_input = await asyncio.to_thread(prepare_zkvm_input, matrix)
    prepare_seconds = time.perf_counter() - started

    with tempfile.TemporaryDirectory(prefix="csi-zkvm-benchmark-") as temp_name:
        input_path = Path(temp_name) / "pipeline-input.json"
        started = time.perf_counter()
        input_path.write_text(
            json.dumps(pipeline_input, separators=(",", ":")),
            encoding="utf-8",
        )
        serialize_seconds = time.perf_counter() - started
        input_size_bytes = input_path.stat().st_size

        started = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "prove",
            str(input_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.communicate()
            raise
        prove_verify_seconds = time.perf_counter() - started

    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        if process.returncode < 0:
            signal_number = -process.returncode
            suffix = " (SIGKILL; possible out-of-memory)" if signal_number == 9 else ""
            raise RuntimeError(
                f"zkVM host terminated by signal {signal_number}{suffix}: {detail}"
            )
        raise RuntimeError(f"zkVM host failed (exit={process.returncode}): {detail}")
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("zkVM host returned invalid JSON") from exc
    if not result.get("isValid"):
        raise RuntimeError("zkVM host did not locally verify its receipt")

    return {
        "method": "zkvm",
        "zkvm_input_prepare_seconds": prepare_seconds,
        "zkvm_input_serialize_seconds": serialize_seconds,
        "zkvm_prove_verify_seconds": prove_verify_seconds,
        "total_execution_seconds": time.perf_counter() - total_started,
        "input_json_size_bytes": input_size_bytes,
        "receipt_base64_bytes": len(result.get("receipt", "")),
        "is_valid": bool(result["isValid"]),
        "is_normal": bool(result.get("isNormal")),
        "journal": result.get("journal", {}),
    }


async def run_execution_method(
    method: str,
    *,
    matrix: Any,
    args: argparse.Namespace,
) -> dict[str, Any]:
    print(f"[execution] {method}", flush=True)
    started_at = utc_now()
    started = time.perf_counter()
    try:
        if method == "python_circom":
            result = await run_python_circom_once(
                matrix,
                zkp_root=args.zkp_root,
                verbose=args.verbose,
            )
        else:
            result = await run_zkvm_once(
                matrix,
                binary=args.zkvm_binary,
            )
        return {"status": "completed", "started_at": started_at, **result}
    except Exception as exc:
        if not args.continue_on_error:
            raise
        return {
            "status": "failed",
            "started_at": started_at,
            "method": method,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_before_failure_seconds": time.perf_counter() - started,
        }


async def execution(args: argparse.Namespace) -> dict[str, Any]:
    install_backend_path(args.backend_root)
    if args.method in ("both", "zkvm") and not args.zkvm_binary.is_file():
        raise FileNotFoundError(f"zkVM binary not found: {args.zkvm_binary}")

    matrix, input_metadata = load_execution_matrix(args)
    element_count = int(matrix.shape[0] * matrix.shape[1])
    if (
        args.method in ("both", "zkvm")
        and element_count > args.max_zkvm_elements
        and not args.allow_large_zkvm_input
    ):
        raise ValueError(
            f"zkVM input has {element_count:,} elements; safety limit is "
            f"{args.max_zkvm_elements:,}. Use --sample-limit/--subcarrier-limit or "
            "--allow-large-zkvm-input."
        )

    versions = {
        "snarkjs": command_version(
            [
                resolve_executable(
                    "snarkjs",
                    args.zkp_root / "node_modules" / ".bin" / "snarkjs",
                ),
                "--version",
            ]
        ),
        "zkvm_binary_sha256": (
            file_sha256(args.zkvm_binary) if args.zkvm_binary.is_file() else None
        ),
    }
    methods = ["python_circom", "zkvm"] if args.method == "both" else [args.method]
    runs: list[dict[str, Any]] = []

    for warmup_index in range(args.warmups):
        order = methods if warmup_index % 2 == 0 else list(reversed(methods))
        for method in order:
            print(f"[warmup {warmup_index + 1}/{args.warmups}] {method}", flush=True)
            await run_execution_method(method, matrix=matrix, args=args)

    started_at = utc_now()
    for run_index in range(args.runs):
        order = methods if run_index % 2 == 0 else list(reversed(methods))
        for method in order:
            result = await run_execution_method(method, matrix=matrix, args=args)
            result["run_index"] = run_index
            runs.append(result)

    completed = [run for run in runs if run["status"] == "completed"]
    summaries = {
        method: summarize_runs([run for run in completed if run["method"] == method])
        for method in methods
        if any(run["method"] == method for run in completed)
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "execution",
        "started_at": started_at,
        "finished_at": utc_now(),
        "definition": {
            "shared_input": "同一の複素 CSI 行列。PicoScenes parse/load は両方式の計測外。",
            "python_circom": (
                "Python 5-1解析 + certificate witness生成 + Groth16証明生成 + ローカル検証。"
            ),
            "zkvm": (
                "CSI行列の固定小数点入力化 + JSON化 + RISC Zero hostの証明生成・"
                "ローカルreceipt検証。"
            ),
        },
        "environment": environment_metadata(),
        "versions": versions,
        "input": input_metadata,
        "settings": {
            "methods": methods,
            "runs": args.runs,
            "warmups": args.warmups,
            "alternating_order": True,
        },
        "runs": runs,
        "summary": summaries,
    }
    output = args.output or default_output("execution")
    write_timed_json(output, payload)
    print(f"[result] {output}")
    for method, summary in summaries.items():
        total = summary.get("total_execution_seconds", {})
        if total:
            print(f"[summary] {method}: median={total['median']:.3f}s n={int(total['count'])}")
    return payload


def add_common_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, help="結果 JSON の保存先")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    execution_parser = subparsers.add_parser("execution", help="証明実行時間を計測")
    add_common_output(execution_parser)
    execution_parser.add_argument(
        "--method",
        choices=("both", "python_circom", "zkvm"),
        default="both",
    )
    execution_parser.add_argument("--runs", type=int, default=1)
    execution_parser.add_argument("--warmups", type=int, default=0)
    execution_parser.add_argument(
        "--csi-file",
        type=Path,
        required=True,
        help="計測に使う PicoScenes .csi ファイル",
    )
    execution_parser.add_argument("--sample-limit", type=int)
    execution_parser.add_argument("--subcarrier-limit", type=int)
    execution_parser.add_argument("--backend-root", type=Path, default=DEFAULT_BACKEND_ROOT)
    execution_parser.add_argument("--zkp-root", type=Path, default=DEFAULT_ZKP_ROOT)
    execution_parser.add_argument("--zkvm-binary", type=Path, default=DEFAULT_ZKVM_BINARY)
    execution_parser.add_argument("--max-zkvm-elements", type=int, default=2_000_000)
    execution_parser.add_argument("--allow-large-zkvm-input", action="store_true")
    execution_parser.set_defaults(continue_on_error=True)
    execution_parser.add_argument(
        "--fail-fast",
        dest="continue_on_error",
        action="store_false",
        help="最初の方式が失敗した時点で終了し、結果JSONを作らない",
    )
    execution_parser.add_argument("--verbose", action="store_true")

    circom_parser = subparsers.add_parser("build-circom", help="Circom build/setup時間を計測")
    add_common_output(circom_parser)
    circom_parser.add_argument("--zkp-root", type=Path, default=REPO_ROOT / "zkp")
    circom_parser.add_argument(
        "--ptau",
        type=Path,
        default=REPO_ROOT / "zkp" / "keys" / "powersOfTau28_hez_final_19.ptau",
    )
    circom_parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="指定時は一時成果物を削除せずこのディレクトリへ保存",
    )

    zkvm_parser = subparsers.add_parser("build-zkvm", help="zkVM Docker build時間を計測")
    add_common_output(zkvm_parser)
    zkvm_parser.add_argument("--no-cache", action="store_true")
    zkvm_parser.add_argument("--platform", default="linux/amd64")
    zkvm_parser.add_argument("--image-tag", default="csi-zkvm-benchmark:latest")

    args = parser.parse_args(argv)
    if getattr(args, "runs", 1) < 1:
        parser.error("--runs must be >= 1")
    if getattr(args, "warmups", 0) < 0:
        parser.error("--warmups must be >= 0")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "execution":
        asyncio.run(execution(args))
    elif args.command == "build-circom":
        build_circom(args)
    elif args.command == "build-zkvm":
        build_zkvm(args)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
