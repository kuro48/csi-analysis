"""Shared synthetic controls and legacy 8-column selection sensitivity."""

import numpy as np
from reference import prepare, estimate_integer
from run import HERE, COUNTS, write_csv, dump


def run():
    rows = []
    for path in sorted((HERE.parent / "common/synthetic").glob("*.npz")):
        d = np.load(path)
        payload, meta, _, _ = prepare(d["csi_complex"], d["timestamps_ns"])
        target = float(d["target_bpm"])
        for count in COUNTS:
            inp = {
                **payload,
                "csiI": [r[:count] for r in payload["csiI"]],
                "csiQ": [r[:count] for r in payload["csiQ"]],
            }
            result = estimate_integer(inp)
            rows.append(
                {
                    "case": path.stem,
                    "subcarriers": count,
                    "ground_truth_bpm": target,
                    **result,
                    "absolute_error_bpm": abs(result["bpm"] - target),
                }
            )
    write_csv(HERE / "shared_synthetic_accuracy.csv", rows)
    summary = []
    for count in COUNTS:
        subset = [r for r in rows if r["subcarriers"] == count]
        summary.append(
            {
                "subcarriers": count,
                "n_cases": len(subset),
                "mae_bpm": float(np.mean([r["absolute_error_bpm"] for r in subset])),
            }
        )
    dump(HERE / "shared_synthetic_summary.json", summary)
    write_csv(HERE / "shared_synthetic_summary.csv", summary)
    rows = []
    for path in sorted((HERE.parent / "common/windows").glob("csi_*.npz")):
        d = np.load(path)
        # Reproduce existing edge selection across flattened antenna/tones.
        indices = np.rint(np.linspace(0, d["csi_complex"].shape[1] - 1, 8)).astype(int)
        raw = d["csi_complex"][:, indices]
        inp, meta, _, _ = prepare(raw, d["timestamps_ns"], 8)
        # prepare reorders the eight columns; retain source index mapping.
        inverse = np.argsort(meta["subcarrier_indices"])
        inp["csiI"] = np.asarray(inp["csiI"])[:, inverse].tolist()
        inp["csiQ"] = np.asarray(inp["csiQ"])[:, inverse].tolist()
        actual_indices = indices
        result = estimate_integer(inp)
        rows.append(
            {
                "window_id": path.stem,
                "selection": "legacy_flattened_eight_even_spaced",
                "source_indices": actual_indices.tolist(),
                **result,
            }
        )
    write_csv(HERE / "legacy8_sensitivity.csv", rows)


if __name__ == "__main__":
    run()
