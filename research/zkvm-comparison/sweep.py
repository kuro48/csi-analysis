#!/usr/bin/env python3
"""実 CSI を使った再開可能な zkVM 規模スイープと SVG グラフ生成。"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import gc
import hashlib
import html
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_BACKEND_ROOT = Path("/app") if Path("/app/app").is_dir() else REPO_ROOT / "backend"
DEFAULT_ZKP_ROOT = Path("/zkp") if Path("/zkp/circuits").is_dir() else REPO_ROOT / "zkp"
DEFAULT_ZKVM_BINARY = (
    Path("/opt/csi-zkvm/csi-zkvm-host")
    if Path("/opt/csi-zkvm/csi-zkvm-host").is_file()
    else REPO_ROOT / "zkvm" / "target" / "release" / "csi-zkvm-host"
)
DEFAULT_STAGES = (
    "validate_commitment",
    "select_subcarriers",
    "bandpass",
    "pca",
    "vmd",
    "full",
)
ISOLATED_STAGES = DEFAULT_STAGES[:-1]
DEFAULT_SIZES = "64x3,128x4,256x8,512x16,1024x32,2048x32,3000x32"
MEMORY_SAMPLE_INTERVAL_SECONDS = 0.1
COLORS = (
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#ea580c",
    "#0891b2",
    "#4b5563",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


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


def parse_sizes(raw: str) -> list[tuple[int, int]]:
    sizes: list[tuple[int, int]] = []
    for item in raw.split(","):
        parts = item.strip().lower().split("x")
        if len(parts) != 2:
            raise ValueError(f"invalid size {item!r}; expected SAMPLEsxSUBCARRIERS")
        samples, subcarriers = (int(value) for value in parts)
        if samples < 64 or subcarriers < 3:
            raise ValueError(f"size must be at least 64x3: {item}")
        pair = (samples, subcarriers)
        if pair not in sizes:
            sizes.append(pair)
    if not sizes:
        raise ValueError("at least one size is required")
    return sizes


def record_key(record: dict[str, Any]) -> tuple[int, int, str]:
    return (
        int(record["samples"]),
        int(record["subcarriers"]),
        str(record["stage"]),
    )


def load_or_create_result(
    output: Path,
    *,
    source: Path,
    source_sha256: str,
    binary: Path,
    sizes: list[tuple[int, int]],
    stages: Sequence[str],
    profile_mode: str,
) -> dict[str, Any]:
    if output.is_file():
        payload = json.loads(output.read_text(encoding="utf-8"))
        if payload["input"]["source_sha256"] != source_sha256:
            raise ValueError("existing result belongs to a different CSI file")
        if payload["zkvm"]["binary_sha256"] != file_sha256(binary):
            raise ValueError("existing result belongs to a different zkVM binary")
        existing_mode = payload.get("plan", {}).get("profile_mode", "combined")
        if existing_mode != profile_mode:
            raise ValueError(
                f"existing result uses profile mode {existing_mode!r}, "
                f"not {profile_mode!r}"
            )
        return payload

    memory_limit = Path("/sys/fs/cgroup/memory.max")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "zkvm_scale_sweep",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "running",
        "input": {
            "source": str(source),
            "source_size_bytes": source.stat().st_size,
            "source_sha256": source_sha256,
        },
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "cgroup_memory_limit": (
                memory_limit.read_text(encoding="utf-8").strip()
                if memory_limit.is_file()
                else None
            ),
        },
        "zkvm": {
            "binary": str(binary),
            "binary_sha256": file_sha256(binary),
            "timeout": None,
        },
        "plan": {
            "sizes": [
                {"samples": samples, "subcarriers": subcarriers}
                for samples, subcarriers in sizes
            ],
            "stages": list(stages),
            "profile_mode": profile_mode,
        },
        "shape_preparation": [],
        "records": [],
    }
    atomic_write_json(output, payload)
    return payload


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
    raise ValueError("zkVM profiler did not emit a JSON object")


def read_process_memory(pid: int) -> dict[str, int]:
    status_path = Path(f"/proc/{pid}/status")
    try:
        lines = status_path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return {}
    values: dict[str, int] = {}
    field_names = {
        "VmRSS": "rss_bytes",
        "VmHWM": "peak_rss_bytes",
        "VmSize": "virtual_memory_bytes",
        "VmPeak": "peak_virtual_memory_bytes",
    }
    for line in lines:
        name, separator, raw = line.partition(":")
        if not separator or name not in field_names:
            continue
        parts = raw.split()
        if not parts:
            continue
        multiplier = 1024 if len(parts) > 1 and parts[1].lower() == "kb" else 1
        values[field_names[name]] = int(parts[0]) * multiplier
    return values


def read_cgroup_memory_current() -> int | None:
    path = Path("/sys/fs/cgroup/memory.current")
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def communicate_with_memory_sampling(
    process: subprocess.Popen[str],
) -> tuple[str, str, dict[str, int | float | None]]:
    cgroup_before = read_cgroup_memory_current()
    process_peak_rss = 0
    process_peak_virtual = 0
    cgroup_peak = cgroup_before or 0

    def sample() -> None:
        nonlocal process_peak_rss, process_peak_virtual, cgroup_peak
        memory = read_process_memory(process.pid)
        process_peak_rss = max(
            process_peak_rss,
            memory.get("rss_bytes", 0),
            memory.get("peak_rss_bytes", 0),
        )
        process_peak_virtual = max(
            process_peak_virtual,
            memory.get("virtual_memory_bytes", 0),
            memory.get("peak_virtual_memory_bytes", 0),
        )
        current = read_cgroup_memory_current()
        if current is not None:
            cgroup_peak = max(cgroup_peak, current)

    sample()
    while True:
        try:
            stdout, stderr = process.communicate(
                timeout=MEMORY_SAMPLE_INTERVAL_SECONDS
            )
            sample()
            break
        except subprocess.TimeoutExpired:
            sample()

    return (
        stdout,
        stderr,
        {
            "process_peak_rss_bytes": process_peak_rss or None,
            "process_peak_virtual_memory_bytes": process_peak_virtual or None,
            "cgroup_memory_before_bytes": cgroup_before,
            "cgroup_memory_peak_during_bytes": cgroup_peak or None,
            "cgroup_memory_delta_peak_bytes": (
                max(0, cgroup_peak - cgroup_before)
                if cgroup_before is not None and cgroup_peak
                else None
            ),
            "memory_sample_interval_seconds": MEMORY_SAMPLE_INTERVAL_SECONDS,
        },
    )


def run_profile_stage(
    binary: Path,
    stage: str,
    input_path: Path,
    *,
    samples: int,
    subcarriers: int,
    profile_mode: str = "combined",
) -> dict[str, Any]:
    command_name = "profile-isolated" if profile_mode == "isolated" else "profile-stage"
    command = [str(binary), command_name, stage, str(input_path)]
    started_at = utc_now()
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr, memory = communicate_with_memory_sampling(process)
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.communicate()
        raise
    elapsed = time.perf_counter() - started
    base = {
        "samples": samples,
        "subcarriers": subcarriers,
        "input_elements": samples * subcarriers,
        "stage": stage,
        "profile_mode": profile_mode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "outer_wall_seconds": elapsed,
        "command": command,
        "memory": memory,
    }
    if process.returncode != 0:
        signal_number = -process.returncode if process.returncode < 0 else None
        return {
            **base,
            "status": "failed",
            "returncode": process.returncode,
            "signal": signal_number,
            "possible_oom": signal_number == 9,
            "stderr": stderr[-8000:],
            "stdout": stdout[-8000:],
        }
    return {
        **base,
        "status": "completed",
        "profile": parse_json_stdout(stdout),
        "stderr": stderr[-8000:],
    }


async def run_python_circom(
    matrix: Any,
    *,
    samples: int,
    subcarriers: int,
    zkp_root: Path,
) -> dict[str, Any]:
    from benchmark import run_python_circom_once

    started_at = utc_now()
    started = time.perf_counter()
    try:
        result = await run_python_circom_once(matrix, zkp_root=zkp_root, verbose=False)
        return {
            "samples": samples,
            "subcarriers": subcarriers,
            "input_elements": samples * subcarriers,
            "stage": "python_circom",
            "status": "completed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "outer_wall_seconds": time.perf_counter() - started,
            "profile": result,
        }
    except Exception as exc:
        return {
            "samples": samples,
            "subcarriers": subcarriers,
            "input_elements": samples * subcarriers,
            "stage": "python_circom",
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "outer_wall_seconds": time.perf_counter() - started,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def completed_keys(payload: dict[str, Any]) -> set[tuple[int, int, str]]:
    return {
        record_key(record)
        for record in payload["records"]
        if record.get("status") == "completed"
    }


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    row = {
        "samples": record["samples"],
        "subcarriers": record["subcarriers"],
        "input_elements": record["input_elements"],
        "stage": record["stage"],
        "profile_mode": record.get("profile_mode"),
        "status": record["status"],
        "outer_wall_seconds": record.get("outer_wall_seconds"),
        "process_peak_rss_bytes": record.get("memory", {}).get(
            "process_peak_rss_bytes"
        ),
        "process_peak_virtual_memory_bytes": record.get("memory", {}).get(
            "process_peak_virtual_memory_bytes"
        ),
        "cgroup_memory_before_bytes": record.get("memory", {}).get(
            "cgroup_memory_before_bytes"
        ),
        "cgroup_memory_peak_during_bytes": record.get("memory", {}).get(
            "cgroup_memory_peak_during_bytes"
        ),
        "cgroup_memory_delta_peak_bytes": record.get("memory", {}).get(
            "cgroup_memory_delta_peak_bytes"
        ),
    }
    profile = record.get("profile", {})
    if record["stage"] == "python_circom":
        row.update(
            {
                "execution_seconds": profile.get("python_analysis_seconds"),
                "proving_seconds": profile.get("circom_prove_seconds"),
                "verification_seconds": profile.get("circom_verify_seconds"),
                "total_execution_seconds": profile.get("total_execution_seconds"),
            }
        )
        return row

    stage_cycles = profile.get("journal", {}).get("stage_cycles", [])
    isolated_cycles = (
        stage_cycles[0].get("cycles")
        if len(stage_cycles) == 1
        else sum(item.get("cycles", 0) for item in stage_cycles)
    )
    row.update(
        {
            "function_cycles": isolated_cycles,
            "input_file_read_seconds": profile.get("input_file_read_seconds"),
            "input_json_decode_seconds": profile.get("input_json_decode_seconds"),
            "request_serialize_seconds": profile.get("request_serialize_seconds"),
            "host_prepare_seconds": profile.get(
                "host_prepare_seconds",
                profile.get("host_dependency_prepare_seconds"),
            ),
            "execution_env_build_seconds": profile.get("execution_env_build_seconds"),
            "execution_seconds": profile.get("execution_seconds"),
            "execution_user_cycles": profile.get("execution_user_cycles"),
            "execution_journal_decode_seconds": profile.get(
                "execution_journal_decode_seconds"
            ),
            "proving_env_build_seconds": profile.get("proving_env_build_seconds"),
            "proving_seconds": profile.get("proving_seconds"),
            "proving_peak_rss_bytes": profile.get("proving_memory", {}).get(
                "peak_rss_bytes"
            ),
            "proving_peak_virtual_memory_bytes": profile.get(
                "proving_memory", {}
            ).get("peak_virtual_memory_bytes"),
            "proving_cgroup_memory_peak_bytes": profile.get(
                "proving_memory", {}
            ).get("cgroup_memory_peak_bytes"),
            "proving_cgroup_memory_delta_peak_bytes": profile.get(
                "proving_memory", {}
            ).get("cgroup_memory_delta_peak_bytes"),
            "verification_seconds": profile.get("verification_seconds"),
            "proof_journal_decode_seconds": profile.get("proof_journal_decode_seconds"),
            "receipt_serialize_seconds": profile.get("receipt_serialize_seconds"),
            "output_json_serialize_seconds": profile.get(
                "output_json_serialize_seconds"
            ),
            "total_host_seconds": profile.get("total_host_seconds"),
            "guest_profiled_cycles": profile.get("guest_profiled_cycles"),
            "guest_unattributed_cycles": profile.get("guest_unattributed_cycles"),
            "proof_total_cycles": profile.get("proof_stats", {}).get("total_cycles"),
            "proof_user_cycles": profile.get("proof_stats", {}).get("user_cycles"),
            "proof_segments": profile.get("proof_stats", {}).get("segments"),
            "request_bytes": profile.get("request_bytes"),
            "request_input_elements": profile.get("request_input_elements"),
            "receipt_bytes": profile.get("receipt_bytes"),
            "total_execution_seconds": (
                float(profile.get("execution_seconds", 0))
                + float(profile.get("proving_seconds", 0))
                + float(profile.get("verification_seconds", 0))
            ),
        }
    )
    return row


def write_csv(payload: dict[str, Any], path: Path) -> None:
    rows = [flatten_record(record) for record in payload["records"]]
    fields = [
        "samples",
        "subcarriers",
        "input_elements",
        "stage",
        "profile_mode",
        "status",
        "function_cycles",
        "input_file_read_seconds",
        "input_json_decode_seconds",
        "request_serialize_seconds",
        "host_prepare_seconds",
        "execution_env_build_seconds",
        "execution_seconds",
        "execution_user_cycles",
        "execution_journal_decode_seconds",
        "proving_env_build_seconds",
        "proving_seconds",
        "proving_peak_rss_bytes",
        "proving_peak_virtual_memory_bytes",
        "proving_cgroup_memory_peak_bytes",
        "proving_cgroup_memory_delta_peak_bytes",
        "verification_seconds",
        "proof_journal_decode_seconds",
        "receipt_serialize_seconds",
        "output_json_serialize_seconds",
        "total_host_seconds",
        "guest_profiled_cycles",
        "guest_unattributed_cycles",
        "total_execution_seconds",
        "proof_total_cycles",
        "proof_user_cycles",
        "proof_segments",
        "request_bytes",
        "request_input_elements",
        "receipt_bytes",
        "outer_wall_seconds",
        "process_peak_rss_bytes",
        "process_peak_virtual_memory_bytes",
        "cgroup_memory_before_bytes",
        "cgroup_memory_peak_during_bytes",
        "cgroup_memory_delta_peak_bytes",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detailed_process_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in payload["records"]:
        if record.get("status") != "completed":
            continue
        if (
            record.get("stage") != "full"
            and record.get("profile_mode") != "isolated"
        ):
            continue
        for process in record.get("profile", {}).get("journal", {}).get(
            "process_cycles", []
        ):
            rows.append(
                {
                    "samples": record["samples"],
                    "subcarriers": record["subcarriers"],
                    "input_elements": record["input_elements"],
                    "stage": process["process"],
                    "status": "completed",
                    "calls": process["calls"],
                    "inclusive_cycles": process["inclusive_cycles"],
                    "exclusive_cycles": process["exclusive_cycles"],
                    "function_cycles": process["inclusive_cycles"],
                }
            )
    return rows


def write_process_csv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    fields = [
        "samples",
        "subcarriers",
        "input_elements",
        "stage",
        "calls",
        "inclusive_cycles",
        "exclusive_cycles",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def system_phase_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    phase_fields = (
        "input_file_read_seconds",
        "input_json_decode_seconds",
        "request_serialize_seconds",
        "host_prepare_seconds",
        "execution_env_build_seconds",
        "execution_seconds",
        "execution_journal_decode_seconds",
        "proving_env_build_seconds",
        "proving_seconds",
        "verification_seconds",
        "proof_journal_decode_seconds",
        "receipt_serialize_seconds",
        "output_json_serialize_seconds",
    )
    for record in payload["records"]:
        if record.get("status") != "completed":
            continue
        if (
            record.get("stage") != "full"
            and record.get("profile_mode") != "isolated"
        ):
            continue
        profile = record["profile"]
        for phase in phase_fields:
            value = profile.get(phase)
            if isinstance(value, (int, float)) and value > 0:
                phase_name = phase.removesuffix("_seconds")
                if record.get("profile_mode") == "isolated":
                    phase_name = f'{record["stage"]}:{phase_name}'
                rows.append(
                    {
                        "samples": record["samples"],
                        "subcarriers": record["subcarriers"],
                        "input_elements": record["input_elements"],
                        "stage": phase_name,
                        "status": "completed",
                        "phase_seconds": value,
                    }
                )
        host_dependency_prepare = profile.get("host_dependency_prepare_seconds")
        if (
            isinstance(host_dependency_prepare, (int, float))
            and host_dependency_prepare > 0
        ):
            rows.append(
                {
                    "samples": record["samples"],
                    "subcarriers": record["subcarriers"],
                    "input_elements": record["input_elements"],
                    "stage": f'{record["stage"]}:host_dependency_prepare',
                    "status": "completed",
                    "phase_seconds": host_dependency_prepare,
                }
            )

    for preparation in payload.get("shape_preparation", []):
        for phase in (
            "subset_copy_seconds",
            "zkvm_quantize_commitment_seconds",
            "input_json_serialize_seconds",
            "input_json_write_seconds",
        ):
            value = preparation.get(phase)
            if isinstance(value, (int, float)) and value > 0:
                rows.append(
                    {
                        "samples": preparation["samples"],
                        "subcarriers": preparation["subcarriers"],
                        "input_elements": preparation["input_elements"],
                        "stage": phase.removesuffix("_seconds"),
                        "status": "completed",
                        "phase_seconds": value,
                    }
                )
    for record in payload["records"]:
        if (
            record.get("status") != "completed"
            or record.get("stage") != "python_circom"
        ):
            continue
        profile = record["profile"]
        for timing in profile.get("python_process_timings", []):
            value = timing.get("seconds")
            if isinstance(value, (int, float)) and value > 0:
                rows.append(
                    {
                        "samples": record["samples"],
                        "subcarriers": record["subcarriers"],
                        "input_elements": record["input_elements"],
                        "stage": f'python:{timing["process"]}',
                        "status": "completed",
                        "phase_seconds": value,
                    }
                )
        for phase in (
            "python_analysis_unattributed_seconds",
            "circom_service_init_seconds",
            "circom_input_prepare_seconds",
            "circom_witness_seconds",
            "circom_prove_seconds",
            "circom_verify_seconds",
        ):
            value = profile.get(phase)
            if isinstance(value, (int, float)) and value > 0:
                rows.append(
                    {
                        "samples": record["samples"],
                        "subcarriers": record["subcarriers"],
                        "input_elements": record["input_elements"],
                        "stage": phase.removesuffix("_seconds"),
                        "status": "completed",
                        "phase_seconds": value,
                    }
                )
    return rows


def write_phase_csv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    fields = [
        "samples",
        "subcarriers",
        "input_elements",
        "stage",
        "phase_seconds",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def svg_line_chart(
    rows: Sequence[dict[str, Any]],
    *,
    value_key: str,
    title: str,
    y_label: str,
    output: Path,
) -> None:
    usable = [
        row
        for row in rows
        if row.get("status") == "completed"
        and isinstance(row.get(value_key), (int, float))
        and float(row[value_key]) > 0
    ]
    if not usable:
        return

    stages = sorted({str(row["stage"]) for row in usable})
    width = 1100
    height = max(680, 120 + 22 * len(stages))
    left, right, top, bottom = 100, 250, 70, 90
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_values = [math.log10(float(row["input_elements"])) for row in usable]
    y_values = [math.log10(float(row[value_key])) for row in usable]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    if x_min == x_max:
        x_min -= 0.5
        x_max += 0.5
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5
    x_margin = (x_max - x_min) * 0.05
    y_margin = (y_max - y_min) * 0.08
    x_min, x_max = x_min - x_margin, x_max + x_margin
    y_min, y_max = y_min - y_margin, y_max + y_margin

    def x_position(value: float) -> float:
        return left + (math.log10(value) - x_min) / (x_max - x_min) * plot_width

    def y_position(value: float) -> float:
        return top + (y_max - math.log10(value)) / (y_max - y_min) * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" '
        f'font-family="sans-serif" font-size="22">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#111827"/>',
    ]
    for tick in range(6):
        ratio = tick / 5
        x_log = x_min + (x_max - x_min) * ratio
        x = left + plot_width * ratio
        value = 10**x_log
        lines.extend(
            [
                f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" '
                'stroke="#e5e7eb"/>',
                f'<text x="{x:.1f}" y="{top + plot_height + 25}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="12">{value:.2g}</text>',
            ]
        )
        y_log = y_min + (y_max - y_min) * ratio
        y = top + plot_height * (1 - ratio)
        y_value = 10**y_log
        lines.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
                'stroke="#e5e7eb"/>',
                f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" '
                f'font-family="sans-serif" font-size="12">{y_value:.2g}</text>',
            ]
        )

    lines.extend(
        [
            f'<text x="{left + plot_width / 2}" y="{height - 28}" text-anchor="middle" '
            'font-family="sans-serif" font-size="15">input elements (samples × subcarriers, log)</text>',
            f'<text x="24" y="{top + plot_height / 2}" text-anchor="middle" '
            f'transform="rotate(-90 24 {top + plot_height / 2})" '
            f'font-family="sans-serif" font-size="15">{html.escape(y_label)} (log)</text>',
        ]
    )

    for index, stage in enumerate(stages):
        color = COLORS[index % len(COLORS)]
        stage_rows = sorted(
            (row for row in usable if row["stage"] == stage),
            key=lambda row: row["input_elements"],
        )
        points = " ".join(
            f'{x_position(float(row["input_elements"])):.1f},{y_position(float(row[value_key])):.1f}'
            for row in stage_rows
        )
        if len(stage_rows) > 1:
            lines.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" '
                'stroke-width="2.5"/>'
            )
        for row in stage_rows:
            x = x_position(float(row["input_elements"]))
            y = y_position(float(row[value_key]))
            label = f'{row["samples"]}x{row["subcarriers"]}'
            lines.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}">'
                f"<title>{html.escape(stage)} {html.escape(label)}: "
                f'{float(row[value_key]):.6g}</title></circle>'
            )
        legend_y = top + 22 * index
        lines.extend(
            [
                f'<line x1="{left + plot_width + 24}" y1="{legend_y}" '
                f'x2="{left + plot_width + 54}" y2="{legend_y}" stroke="{color}" '
                'stroke-width="3"/>',
                f'<text x="{left + plot_width + 62}" y="{legend_y + 4}" '
                f'font-family="sans-serif" font-size="13">{html.escape(stage)}</text>',
            ]
        )
    lines.append("</svg>")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_artifacts(payload: dict[str, Any], output: Path) -> None:
    rows = [flatten_record(record) for record in payload["records"]]
    process_rows = detailed_process_rows(payload)
    phase_rows = system_phase_rows(payload)
    write_csv(payload, output.with_suffix(".csv"))
    write_process_csv(
        process_rows,
        output.with_name(output.stem + "-processes.csv"),
    )
    write_phase_csv(
        phase_rows,
        output.with_name(output.stem + "-system-phases.csv"),
    )
    svg_line_chart(
        rows,
        value_key="proving_seconds",
        title="Proof generation time by input scale",
        y_label="proving seconds",
        output=output.with_name(output.stem + "-proving-seconds.svg"),
    )
    svg_line_chart(
        rows,
        value_key="execution_seconds",
        title="Guest execution time by input scale",
        y_label="execution seconds",
        output=output.with_name(output.stem + "-execution-seconds.svg"),
    )
    svg_line_chart(
        rows,
        value_key="proving_peak_rss_bytes",
        title="Peak prover RSS during isolated proof generation",
        y_label="peak RSS bytes",
        output=output.with_name(output.stem + "-peak-memory.svg"),
    )
    svg_line_chart(
        process_rows,
        value_key="function_cycles",
        title="Detailed internal process cycles by input scale",
        y_label="guest process inclusive cycles",
        output=output.with_name(output.stem + "-function-cycles.svg"),
    )
    svg_line_chart(
        phase_rows,
        value_key="phase_seconds",
        title="End-to-end system phase time by input scale (full profile)",
        y_label="phase seconds",
        output=output.with_name(output.stem + "-system-phases.svg"),
    )


def write_measured_results(payload: dict[str, Any], output: Path) -> float:
    """Write the result set and record the primary output duration in JSON."""
    started = time.perf_counter()
    atomic_write_json(output, payload)
    write_artifacts(payload, output)
    elapsed = time.perf_counter() - started
    timing = payload.setdefault("timings", {})
    timing["result_output_seconds"] = elapsed
    timing["result_output_measurements"] = int(
        timing.get("result_output_measurements", 0)
    ) + 1
    timing["result_output_seconds_total"] = float(
        timing.get("result_output_seconds_total", 0.0)
    ) + elapsed
    timing["result_output_metadata_rewrite_excluded"] = True
    # One small metadata rewrite is necessary because elapsed is only known
    # after the primary JSON/CSV/SVG output has completed.
    atomic_write_json(output, payload)
    return elapsed


async def run(args: argparse.Namespace) -> dict[str, Any]:
    backend_root = str(args.backend_root.resolve())
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from app.services.breathing_pipeline import load_csi_matrix, prepare_zkvm_input

    if not args.csi_file.is_file() or args.csi_file.suffix.lower() != ".csi":
        raise FileNotFoundError(f"valid .csi file not found: {args.csi_file}")
    if not args.zkvm_binary.is_file():
        raise FileNotFoundError(f"zkVM profiler binary not found: {args.zkvm_binary}")

    sizes = parse_sizes(args.sizes)
    raw_stages = args.stages
    if (
        args.profile_mode == "isolated"
        and raw_stages == ",".join(DEFAULT_STAGES)
    ):
        raw_stages = ",".join(ISOLATED_STAGES)
    stages = [item.strip() for item in raw_stages.split(",") if item.strip()]
    unknown = sorted(set(stages) - set(DEFAULT_STAGES))
    if unknown:
        raise ValueError(f"unknown stages: {', '.join(unknown)}")
    if args.profile_mode == "isolated":
        unsupported = sorted(set(stages) - set(ISOLATED_STAGES))
        if unsupported:
            raise ValueError(
                "isolated profile mode does not support stages: "
                + ", ".join(unsupported)
            )
    planned_stages = [*stages]
    if not args.skip_python_circom:
        planned_stages.append("python_circom")

    source_hash_start = time.perf_counter()
    source_hash = file_sha256(args.csi_file)
    source_hash_seconds = time.perf_counter() - source_hash_start
    payload = load_or_create_result(
        args.output,
        source=args.csi_file,
        source_sha256=source_hash,
        binary=args.zkvm_binary,
        sizes=sizes,
        stages=planned_stages,
        profile_mode=args.profile_mode,
    )
    payload.setdefault("shape_preparation", [])
    payload.setdefault("timings", {})
    payload["input"]["source_hash_seconds"] = source_hash_seconds

    load_started = time.perf_counter()
    matrix = load_csi_matrix(str(args.csi_file))
    parse_load_seconds = time.perf_counter() - load_started
    max_samples = max(samples for samples, _ in sizes)
    max_subcarriers = max(subcarriers for _, subcarriers in sizes)
    if max_samples > matrix.shape[0] or max_subcarriers > matrix.shape[1]:
        raise ValueError(
            f"requested max {max_samples}x{max_subcarriers}, "
            f"but CSI matrix is {matrix.shape[0]}x{matrix.shape[1]}"
        )
    max_subset_copy_start = time.perf_counter()
    matrix = matrix[:max_samples, :max_subcarriers].copy(order="C")
    max_subset_copy_seconds = time.perf_counter() - max_subset_copy_start
    gc.collect()
    payload["input"]["matrix_shape"] = [int(matrix.shape[0]), int(matrix.shape[1])]
    payload["input"]["parse_load_seconds_excluded"] = parse_load_seconds
    payload["input"]["max_subset_copy_seconds"] = max_subset_copy_seconds
    payload["timings"]["csi_read_seconds"] = parse_load_seconds
    atomic_write_json(args.output, payload)

    done = completed_keys(payload)
    for samples, subcarriers in sizes:
        subset_copy_start = time.perf_counter()
        subset = matrix[:samples, :subcarriers].copy(order="C")
        subset_copy_seconds = time.perf_counter() - subset_copy_start
        with tempfile.TemporaryDirectory(prefix=f"csi-zkvm-sweep-{samples}x{subcarriers}-") as temp:
            input_path = Path(temp) / "pipeline-input.json"
            quantize_start = time.perf_counter()
            pipeline_input = prepare_zkvm_input(subset)
            zkvm_quantize_commitment_seconds = time.perf_counter() - quantize_start
            json_serialize_start = time.perf_counter()
            serialized_input = json.dumps(pipeline_input, separators=(",", ":"))
            input_json_serialize_seconds = time.perf_counter() - json_serialize_start
            json_write_start = time.perf_counter()
            input_path.write_text(serialized_input, encoding="utf-8")
            input_json_write_seconds = time.perf_counter() - json_write_start
            preparation = {
                "samples": samples,
                "subcarriers": subcarriers,
                "input_elements": samples * subcarriers,
                "subset_copy_seconds": subset_copy_seconds,
                "zkvm_quantize_commitment_seconds": zkvm_quantize_commitment_seconds,
                "input_json_serialize_seconds": input_json_serialize_seconds,
                "input_json_write_seconds": input_json_write_seconds,
                "input_json_bytes": len(serialized_input.encode("utf-8")),
                "measured_at": utc_now(),
            }
            payload["shape_preparation"] = [
                entry
                for entry in payload["shape_preparation"]
                if (entry["samples"], entry["subcarriers"]) != (samples, subcarriers)
            ]
            payload["shape_preparation"].append(preparation)
            payload["updated_at"] = utc_now()
            atomic_write_json(args.output, payload)
            del pipeline_input
            del serialized_input
            gc.collect()

            for stage in stages:
                key = (samples, subcarriers, stage)
                if key in done:
                    print(f"[skip] {samples}x{subcarriers} {stage}", flush=True)
                    continue
                print(f"[profile] {samples}x{subcarriers} {stage}", flush=True)
                record = run_profile_stage(
                    args.zkvm_binary,
                    stage,
                    input_path,
                    samples=samples,
                    subcarriers=subcarriers,
                    profile_mode=args.profile_mode,
                )
                payload["records"].append(record)
                payload["updated_at"] = utc_now()
                write_measured_results(payload, args.output)
                if record["status"] == "completed":
                    done.add(key)
                elif args.fail_fast:
                    raise RuntimeError(f"profile failed: {samples}x{subcarriers} {stage}")

            python_key = (samples, subcarriers, "python_circom")
            if not args.skip_python_circom and python_key not in done:
                print(f"[profile] {samples}x{subcarriers} python_circom", flush=True)
                record = await run_python_circom(
                    subset,
                    samples=samples,
                    subcarriers=subcarriers,
                    zkp_root=args.zkp_root,
                )
                payload["records"].append(record)
                payload["updated_at"] = utc_now()
                write_measured_results(payload, args.output)
                if record["status"] == "completed":
                    done.add(python_key)
                elif args.fail_fast:
                    raise RuntimeError(f"Python+Circom failed: {samples}x{subcarriers}")
        del subset
        gc.collect()

    payload["status"] = (
        "completed"
        if all(
            (samples, subcarriers, stage) in done
            for samples, subcarriers in sizes
            for stage in planned_stages
        )
        else "completed_with_failures"
    )
    payload["updated_at"] = utc_now()
    write_measured_results(payload, args.output)
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csi-file", type=Path, required=True)
    parser.add_argument("--sizes", default=DEFAULT_SIZES)
    parser.add_argument("--stages", default=",".join(DEFAULT_STAGES))
    parser.add_argument(
        "--profile-mode",
        choices=("combined", "isolated"),
        default="combined",
        help=(
            "combined: 共有profile guest、isolated: 工程ごとに別ELFを使い、"
            "proofのみを個別計測"
        ),
    )
    parser.add_argument("--skip-python-circom", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--backend-root", type=Path, default=DEFAULT_BACKEND_ROOT)
    parser.add_argument("--zkp-root", type=Path, default=DEFAULT_ZKP_ROOT)
    parser.add_argument("--zkvm-binary", type=Path, default=DEFAULT_ZKVM_BINARY)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/results/scale-sweep.json")
        if Path("/results").is_dir()
        else SCRIPT_DIR / "results" / "scale-sweep.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
