#!/usr/bin/env python3
"""Run the three-method benchmark for every capture in a CSV manifest."""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.hybrid_experiment_service import HybridExperimentService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, help="CSV columns: file_path,dataset_id,ground_truth_bpm")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        raise ValueError("--repeat must be at least 1")
    service = HybridExperimentService(results_dir=str(args.results_dir) if args.results_dir else None)
    with args.manifest.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    failures = 0
    for row in rows:
        path = Path(row["file_path"]).expanduser().resolve()
        truth = float(row["ground_truth_bpm"]) if row.get("ground_truth_bpm") else None
        for repetition in range(args.repeat):
            try:
                result = await service.run(
                    str(path),
                    ground_truth_bpm=truth,
                    dataset_id=row.get("dataset_id") or None,
                    source_filename=path.name,
                )
                statuses = {item["method"]: item["status"] for item in result["methods"]}
                print(
                    json.dumps({"dataset_id": result["dataset_id"], "repetition": repetition + 1, "statuses": statuses})
                )
            except Exception as exc:
                failures += 1
                print(f"FAILED {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
