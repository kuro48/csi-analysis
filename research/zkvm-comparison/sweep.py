#!/usr/bin/env python3
"""実CSIで zkVM の各処理にかかった時間を1回ずつ計測する。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path("/app") if Path("/app/app").is_dir() else REPO_ROOT / "backend"
ZKVM_BINARY = (
    Path("/opt/csi-zkvm/csi-zkvm-host")
    if Path("/opt/csi-zkvm/csi-zkvm-host").is_file()
    else REPO_ROOT / "zkvm" / "target" / "release" / "csi-zkvm-host"
)
STAGES = (
    "validate_commitment",
    "select_subcarriers",
    "bandpass",
    "pca",
    "vmd",
    "full",
)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("zkVM profiler did not emit JSON")


def profile_stage(stage: str, input_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    process = subprocess.run(
        [str(ZKVM_BINARY), "profile-stage", stage, str(input_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    outer_seconds = time.perf_counter() - started
    if process.returncode != 0:
        return {
            "status": "failed",
            "outer_seconds": outer_seconds,
            "error": process.stderr.strip()[-4000:],
        }

    profile = parse_json_stdout(process.stdout)
    return {
        "status": "completed",
        "outer_seconds": outer_seconds,
        "guest_execution_seconds": profile.get("execution_seconds"),
        "prove_seconds": profile.get("proving_seconds"),
        "verify_seconds": profile.get("verification_seconds"),
    }


def measure(csi_file: Path, output: Path) -> dict[str, Any]:
    backend_root = str(BACKEND_ROOT.resolve())
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from app.services.breathing_pipeline import load_csi_matrix, prepare_zkvm_input

    if not csi_file.is_file() or csi_file.suffix.lower() != ".csi":
        raise FileNotFoundError(f"valid .csi file not found: {csi_file}")
    if not ZKVM_BINARY.is_file():
        raise FileNotFoundError(f"zkVM binary not found: {ZKVM_BINARY}")

    started = time.perf_counter()
    matrix = load_csi_matrix(str(csi_file))
    csi_read_seconds = time.perf_counter() - started

    started = time.perf_counter()
    pipeline_input = prepare_zkvm_input(matrix)
    input_prepare_seconds = time.perf_counter() - started

    with tempfile.TemporaryDirectory(prefix="csi-zkvm-stages-") as temp_name:
        input_path = Path(temp_name) / "input.json"
        started = time.perf_counter()
        input_path.write_text(
            json.dumps(pipeline_input, separators=(",", ":")),
            encoding="utf-8",
        )
        input_write_seconds = time.perf_counter() - started

        stages = {}
        for stage in STAGES:
            print(f"[measure] {stage}", flush=True)
            stages[stage] = profile_stage(stage, input_path)

    payload = {
        "status": (
            "completed"
            if all(result["status"] == "completed" for result in stages.values())
            else "completed_with_failures"
        ),
        "input": {
            "csi_file": str(csi_file.resolve()),
            "samples": int(matrix.shape[0]),
            "subcarriers": int(matrix.shape[1]),
        },
        "csi_read_seconds": csi_read_seconds,
        "input_prepare_seconds": input_prepare_seconds,
        "input_json_write_seconds": input_write_seconds,
        "stages": stages,
    }
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
    measure(args.csi_file, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
