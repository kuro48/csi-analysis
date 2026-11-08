#!/usr/bin/env python3
"""Reproduce selection comparisons; private circuit inputs stay under --work-dir."""
from __future__ import annotations
import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge/lomb_scargle_e2e/bin"))
from prepare_input import canonicalize, load_picoscenes
from select_subcarriers import select_capture


def synthetic(seed: int, frequency: float = 0.25):
    rng = np.random.default_rng(seed)
    time_seconds = np.cumsum(rng.uniform(0.045, 0.075, 1000))
    stamps = np.rint(time_seconds * 1e9).astype(np.int64)
    amplitude = 1 + rng.normal(0, 0.002, (1000, 80))
    active = sorted(rng.choice([j for j in range(80) if j not in (0, 1, 2, 4)], size=8, replace=False).tolist())
    for j, column in enumerate(active):
        amplitude[:, column] = 1 + (0.12 + j * 0.008) * np.sin(2 * np.pi * frequency * time_seconds + j * 0.41)
    amplitude[:, 0] = 100
    amplitude[:, 1] = np.abs(1 + rng.normal(0, 0.35, 1000))
    amplitude[:, 2] = 1e-6 * (1 + 0.4 * np.sin(time_seconds))
    amplitude[:, 4] = 1
    amplitude[100, 4] = 100
    return amplitude * np.exp(1j * rng.normal(0, 0.04, amplitude.shape)), stamps, active


def public_witness(path: Path):
    with path.open("rb") as f:
        if f.read(4) != b"wtns":
            raise ValueError("invalid witness")
        _, sections = struct.unpack("<II", f.read(8))
        size = None
        for _ in range(sections):
            section, length = struct.unpack("<IQ", f.read(12))
            start = f.tell()
            if section == 1:
                size = struct.unpack("<I", f.read(4))[0]
            elif section == 2 and size:
                values = [int.from_bytes(f.read(size), "little") for _ in range(6)]
                return {
                    "isNormal": bool(values[2]),
                    "selectedSlot": values[3],
                    "estimatedBin": values[4],
                    "estimatedBpm": 60 * (127 + 29 * values[4]) / 2540,
                    "globalBin": values[5],
                }
            f.seek(start + length)
    raise ValueError("missing witness data")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csi", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".local/subcarrier-selection/comparison")
    parser.add_argument("--r1cs", type=Path)
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.work_dir, 0o700)
    rows = []
    for seed in range(args.seeds):
        csi, stamps, active = synthetic(seed)
        for method in ("uniform", "motion-quality"):
            started = time.perf_counter()
            selected, times, metadata = select_capture(csi, stamps, method)
            rows.append(
                {
                    "kind": "synthetic",
                    "seed": seed,
                    "method": method,
                    "selectionMs": (time.perf_counter() - started) * 1000,
                    "motionRecall": len(set(metadata["selected_subcarrier_indices"]) & set(active)) / 8,
                    "candidateCount": 80,
                    "selectedCount": 8,
                }
            )
            if seed == 0:
                payload, _ = canonicalize(selected, times)
                (args.work_dir / f"synthetic-{method}.json").write_text(json.dumps(payload))
    witness_cases = [f"synthetic-{m}" for m in ("uniform", "motion-quality")]
    if args.csi:
        for method in ("uniform", "motion-quality"):
            started = time.perf_counter()
            selected, times, metadata = load_picoscenes(args.csi, method)
            payload, conversion = canonicalize(selected, times)
            elapsed = (time.perf_counter() - started) * 1000
            (args.work_dir / f"real-{method}.json").write_text(json.dumps(payload))
            rows.append(
                {
                    "kind": "captured-csi-unlabelled",
                    "method": method,
                    "preparationMs": elapsed,
                    "candidateCount": metadata["modal_csi_width"],
                    "sourceFrames": metadata["modal_frame_count"],
                    "bufferedRows": metadata["buffered_full_width_frames"],
                    "selectedCount": 8,
                    "durationMs": conversion["relative_duration_ms"],
                    "lowQualityFallback": metadata["selection"].get("low_quality_fallback"),
                }
            )
            witness_cases.append(f"real-{method}")
    artifacts = ROOT / "edge/lomb_scargle_e2e/artifacts"
    witnesses = []
    for case in witness_cases:
        started = time.perf_counter()
        out = args.work_dir / (case + ".wtns")
        subprocess.run(
            [
                "node",
                str(artifacts / "generate_witness.js"),
                str(artifacts / "csi_lomb_scargle_end_to_end.wasm"),
                str(args.work_dir / (case + ".json")),
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        item = {"case": case, "witnessMs": (time.perf_counter() - started) * 1000, **public_witness(out)}
        if args.r1cs:
            check = subprocess.run(
                [
                    "node",
                    str(ROOT / "zkp/node_modules/snarkjs/build/cli.cjs"),
                    "wtns",
                    "check",
                    str(args.r1cs),
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            (args.work_dir / (case + "-constraints.log")).write_text(check.stdout + check.stderr)
            if check.returncode or "WITNESS IS CORRECT" not in check.stdout.upper():
                raise RuntimeError(f"constraint check failed: {case}")
            item["constraintsValid"] = True
        witnesses.append(item)
        print(case, item, flush=True)
    summary = {
        "method": "motion-quality-v1",
        "selectionProofScope": "outside_circuit",
        "circuitUnchanged": True,
        "constraints": 807453,
        "seeds": args.seeds,
        "syntheticGroundTruth": "eight randomly located amplitude-modulated columns among static/noisy/faded/impulsive channels",
        "realGroundTruth": None,
        "rows": rows,
        "witnessChecks": witnesses,
        "methods": {
            method: {
                "meanMotionRecall": float(
                    np.mean([r["motionRecall"] for r in rows if r["kind"] == "synthetic" and r["method"] == method])
                ),
                "medianSelectionMs": float(
                    np.median([r["selectionMs"] for r in rows if r["kind"] == "synthetic" and r["method"] == method])
                ),
            }
            for method in ("uniform", "motion-quality")
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
        names = ["Uniform", "Motion quality"]
        methods = ["uniform", "motion-quality"]
        axes[0].bar(
            names, [summary["methods"][m]["meanMotionRecall"] * 100 for m in methods], color=["#8aa196", "#256b4e"]
        )
        axes[0].set(
            ylabel="Known motion columns recovered (%)", ylim=(0, 105), title=f"Synthetic captures ({args.seeds} seeds)"
        )
        axes[1].bar(names, [summary["methods"][m]["medianSelectionMs"] for m in methods], color=["#8aa196", "#256b4e"])
        axes[1].set(ylabel="Selection time, median (ms)", title="80 candidates / 1,000 observations")
        fig.savefig(args.output.with_suffix(".png"), dpi=180)
        svg = args.output.with_suffix(".svg")
        fig.savefig(svg)
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
        plt.close(fig)
    except ImportError:
        print("matplotlib unavailable; JSON comparison saved")
    print(json.dumps(summary["methods"], indent=2))


if __name__ == "__main__":
    main()
