#!/usr/bin/env python3
"""Known-frequency signal controls; not human respiration accuracy."""

import json, sys
import numpy as np
from reference import prepare, estimate_integer, basis
from run import HERE, COUNTS, dump, write_csv, witness, KEYS


def run(circuits=False):
    rows = []
    for bpm in [7.5, 10.0, 15.0, 20.0]:
        for seed in range(10):
            rng = np.random.default_rng(20261026 + seed)
            times = np.linspace(0, 47.8, 64) + rng.uniform(-0.05, 0.05, 64)
            times -= times[0]
            phase = rng.uniform(-np.pi, np.pi, 32)
            signal = 100 * np.sin(2 * np.pi * bpm / 60 * times[:, None] + phase)
            noise = rng.normal(size=(64, 32)) * rng.uniform(50, 250, 32)[None, :]
            csi = 900 + signal + noise + 1j * (50 + rng.normal(0, 15, (64, 32)))
            payload, meta, all_csi, t = prepare(csi, np.rint(times * 1e9).astype(np.int64))
            trig = basis(payload["timestampsMs"])
            for count in COUNTS:
                inp = {
                    **payload,
                    "csiI": [r[:count] for r in payload["csiI"]],
                    "csiQ": [r[:count] for r in payload["csiQ"]],
                }
                result = estimate_integer(inp, trig)
                row = {
                    "data_kind": "synthetic",
                    "seed": seed,
                    "ground_truth_bpm": bpm,
                    "subcarriers": count,
                    **result,
                    "absolute_error_bpm": abs(result["bpm"] - bpm),
                    "within_one_bpm": abs(result["bpm"] - bpm) <= 1,
                }
                if circuits and seed == 0 and bpm == 15:
                    path = HERE / "inputs" / f"control_bpm15_sc{count}.json"
                    dump(path, inp)
                    actual = witness(count, path)
                    row["witness_reference_match"] = all(actual[k] == result[k] for k in KEYS)
                    assert row["witness_reference_match"]
                rows.append(row)
    write_csv(HERE / "synthetic_accuracy.csv", rows)
    summary = []
    for count in COUNTS:
        selected = [r for r in rows if r["subcarriers"] == count]
        summary.append(
            {
                "subcarriers": count,
                "n_cases": len(selected),
                "mae_bpm": float(np.mean([r["absolute_error_bpm"] for r in selected])),
                "median_absolute_error_bpm": float(np.median([r["absolute_error_bpm"] for r in selected])),
                "within_one_bpm_rate": float(np.mean([r["within_one_bpm"] for r in selected])),
            }
        )
    dump(HERE / "synthetic_summary.json", summary)
    write_csv(HERE / "synthetic_summary.csv", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run("--circuits" in sys.argv)
