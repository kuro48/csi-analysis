"""Additional real-data comparison against the previous independent spectral Python method.

Run after the serialized proving/ledger pipeline, so reference computation does
not compete with any timing measurements. No CSI is generated or interpolated.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from evaluate_sample_counts import COUNTS, ROOT, read, save
from evaluate_subcarrier_selection import (
    BAND,
    GRID,
    float_scores,
    periodograms,
    power_diagnostics,
    rank,
    sha256,
    spectral_scores,
    unique_rows,
    winner,
)


def estimate(spectra, column):
    if column is None:
        raise ValueError("No eligible spectral-reference candidate")
    if not np.isfinite(spectra).all():
        raise ValueError("Nonfinite spectral-reference computation")
    peak = int(np.argmax(spectra[:, column]))
    return {
        "selectedSubcarrier": column,
        "globalBpm": float(GRID[peak] * 60),
        "isNormal": int(BAND[peak]),
        "bandFit": float(spectra[BAND, column].max()),
        "globalFit": float(spectra[:, column].max()),
    }


def selection_diagnostics(matrix, column):
    result = power_diagnostics(matrix, column)
    power = np.abs(matrix[:, column]) ** 2
    n = len(power)
    total = float(power.sum())
    variation = float(n * np.sum(power * power) - total * total)
    roughness = float(np.sum(np.diff(power) ** 2))
    result.update(
        {
            "pointCount": n,
            "S": total,
            "V": variation,
            "D": roughness,
            "normalizedRoughness": n * roughness / variation if variation > 0 else None,
            "arithmetic": "floating-point diagnostic on the actual power samples",
        }
    )
    return result


def main():
    from app.services.breathing_pipeline import load_csi_matrix_with_timestamps

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / ".local/sample-count")
    args = parser.parse_args()
    work = args.work.resolve()
    datasets = read(work / "datasets.json")
    assert datasets["realOnly"] is True
    evaluations = {n: {e["name"]: e for e in read(work / f"n{n}/evaluation.json")["results"]} for n in COUNTS}
    results = []
    for dataset in datasets["datasets"]:
        if "excluded" in dataset:
            continue
        name = dataset["name"]
        source = ROOT / "sampledata" / f"{name}.csi"
        if sha256(source) != dataset["sourceSha256"]:
            raise ValueError(f"Real source changed: {name}")
        print(f"Independent spectral Python reference: {name}", flush=True)
        matrix, timestamps = load_csi_matrix_with_timestamps(str(source))
        rows = unique_rows(timestamps)
        full = matrix[rows] * dataset["sharedIqScale"]
        times = (timestamps[rows] - timestamps[rows[0]]).astype(float) / 1e9
        assert len(rows) == dataset["fullPointCount"] and full.shape[1] == dataset["candidateCount"]
        spectra = periodograms(times, full)
        scores = spectral_scores(spectra, float_scores(full) > 0)
        reference = estimate(spectra, winner(scores))
        entry = {"name": name, "sourceSha256": dataset["sourceSha256"], "fullSpectralPython": reference, "variants": {}}
        for n in COUNTS:
            circuit = evaluations[n][name]["circuit"]
            selected = circuit["selectedSubcarrier"]
            data_path = work / "inputs" / f"{name}-n{n}.json"
            assert sha256(data_path) == dataset["variants"][str(n)]["inputSha256"]
            data = read(data_path)
            count = dataset["candidateCount"]
            quantized = (
                np.asarray(data["csiI"], dtype=float)[:, :count]
                - 2048
                + 1j * (np.asarray(data["csiQ"], dtype=float)[:, :count] - 2048)
            )
            sampled_spectra = periodograms(np.asarray(data["timestampsMs"]) / 1000, quantized)
            sampled_scores = spectral_scores(sampled_spectra, float_scores(quantized) > 0)
            same_points = estimate(sampled_spectra, winner(sampled_scores))
            full_same_column = estimate(spectra, selected)
            differences = {}
            for label, ref in [
                ("fullPoints", reference),
                ("samePoints", same_points),
                ("fullPointsSameColumn", full_same_column),
            ]:
                differences[label] = {
                    "selectionMatches": selected == ref["selectedSubcarrier"],
                    "normalityMatches": circuit["isNormal"] == ref["isNormal"],
                    "absoluteDifferenceBpm": abs(circuit["global_bpm"] - ref["globalBpm"]),
                }
            entry["variants"][str(n)] = {
                "samePointsSpectralPython": same_points,
                "fullSpectrumOfCircuitChoice": full_same_column,
                "fullSpectralRankOfCircuitChoice": rank(scores, selected),
                "fullSpectralScoreRatio": float(scores[selected] / scores[reference["selectedSubcarrier"]]),
                "sampledChoiceDiagnostics": selection_diagnostics(quantized, selected),
                "fullChoiceDiagnostics": selection_diagnostics(full, selected),
                "differences": differences,
            }
        results.append(entry)
        save(work / "spectral-reference-progress.json", results)
        del matrix, full, spectra
    report = {
        "realOnly": True,
        "method": "Previous Python spectral selection: maximum floating-mean LS fit in breathing band, over eligible full-pool columns",
        "frequencyGridHz": GRID.tolist(),
        "frequencyGridCount": len(GRID),
        "bandHz": [float(GRID[BAND][0]), float(GRID[BAND][-1])],
        "fullTimestampPolicy": "original nanosecond timestamps expressed as relative seconds after millisecond deduplication",
        "note": "Different selector, floating-mean model and 355-frequency grid; reference difference, not ground-truth accuracy or an isolated fixed-point error",
        "results": results,
    }
    save(work / "spectral-reference.json", report)
    print(json.dumps({"realCaptures": len(results), "sampleCounts": COUNTS}))


if __name__ == "__main__":
    main()
