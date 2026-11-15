#!/usr/bin/env python3
"""Bounded edge-only accuracy sweep; does not claim new circuit proofs."""

import argparse
import contextlib
import csv
import hashlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path

ROUNDS = (4, 8, 16, 32, 64)
CASES = (("A", "csi_20261005_115619.csi", 18),
         ("B", "csi_20261005_115523.csi", 20),
         ("C", "csi_20260907_185130.csi", 12))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def at_rounds(reference, waveform, rounds):
    """Reuse the exact deployed algorithm, changing only its loop bound.

    This script is single-threaded. Restore the module constant even on error;
    neither the deployed file nor its R=4 WASM/zkey is modified or reused as R>4.
    """
    if type(rounds) is not int or not 1 <= rounds <= 64:
        raise ValueError("rounds must be an integer in 1..64")
    original = reference.R
    try:
        reference.R = rounds
        result = reference.vmd_approx(waveform)
        return {key: result[key] for key in
                ("bpm", "peak_bin", "selected_mode", "is_normal", "centers")}
    finally:
        reference.R = original


def inspect_all_series(worker, converter, source):
    """Check every modal-width series under the existing 64-time-point encoding."""
    import numpy as np

    with contextlib.redirect_stdout(io.StringIO()):
        csi, stamps = worker.bp.load_csi_matrix_with_timestamps(str(source))
    original = converter.SUBCARRIERS
    try:
        converter.SUBCARRIERS = int(csi.shape[1])
        inputs, metadata = converter.canonicalize(csi, stamps)
    finally:
        converter.SUBCARRIERS = original
    i = np.asarray(inputs["csiI"], dtype=np.int64) - 2048
    q = np.asarray(inputs["csiQ"], dtype=np.int64) - 2048
    power = i * i + q * q
    constant = np.flatnonzero(np.all(power == power[0], axis=0)).tolist()
    return dict(series=int(csi.shape[1]), time_samples=len(i),
                discarded_series=0, constant_power_series=constant,
                existing_nonzero_constraint_satisfied=not constant,
                scope="All modal-width series; 64 time samples; conversion outside circuit; no proof generated",
                encoded_range=[metadata["encoded_min"], metadata["encoded_max"]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--ls-package", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    worker = module("sweep_worker", args.package / "worker.py")
    converter = module("all_series_converter", args.ls_package / "bin/prepare_input.py")
    report = dict(rounds=ROUNDS, ground_truth_source="user-provided BPM; acquisition/synchronization unverified",
                  proof_generated=False, proof_seconds=None,
                  fixed=dict(samples=128, fs_hz=2, modes=3, amplitude_limit=100),
                  protocol="One shared waveform per case; one warmup and three timed runs per round count. Only R changes.",
                  source_hashes={str(path): digest(path) for path in
                                 (Path(__file__), args.package / "worker.py",
                                  args.package / "vendor/vmd_approx_reference.py",
                                  args.package / "vendor/breathing_pipeline.py",
                                  args.ls_package / "bin/prepare_input.py")}, cases={})
    rows = []
    for label, filename, truth in CASES:
        source = args.data / filename
        before = digest(source)
        print(f"START {label}: all-series readiness and VMD iteration sweep", flush=True)
        readiness = inspect_all_series(worker, converter, source)
        pc, _, metadata = worker.prepare(source)
        waveform = worker.bp.prepare_vmd_approx_input(pc)["waveform"]
        baseline = worker.reference.vmd_approx(waveform)
        assert at_rounds(worker.reference, waveform, 4) == {
            key: baseline[key] for key in ("bpm", "peak_bin", "selected_mode", "is_normal", "centers")}
        case = dict(file=filename, ground_truth_bpm=truth, source_sha256=before,
                    metadata=metadata, lomb_all_series_readiness=readiness,
                    full_float_vmd=worker.measurements(lambda: worker.float_vmd(pc, 100)),
                    compact_float_vmd=worker.measurements(
                        lambda: worker.float_vmd(worker.np.asarray(waveform, dtype=float), 2)), sweep={})
        for rounds in ROUNDS:
            measured = worker.measurements(lambda: at_rounds(worker.reference, waveform, rounds))
            case["sweep"][str(rounds)] = measured
            result = measured["result"]
            row = dict(case=label, truth_bpm=truth, rounds=rounds, bpm=result["bpm"],
                       absolute_error_bpm=abs(result["bpm"] - truth),
                       calculation_seconds=measured["median_seconds"], proof_seconds=None)
            rows.append(row)
            print(json.dumps(row), flush=True)
        if digest(source) != before:
            raise RuntimeError("Source CSI changed during experiment")
        case["source_unchanged"] = True
        report["cases"][label] = case
        (args.output / "summary.json").write_text(json.dumps(report, indent=2))
    with (args.output / "comparison.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    cells = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.values()) + "</tr>"
                    for row in rows)
    headings = "".join(f"<th>{name}</th>" for name in rows[0])
    (args.output / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>VMD iteration sweep</title>'
        '<style>body{font:18px sans-serif;margin:40px}td,th{padding:10px;border:1px solid #ccc}'
        'table{border-collapse:collapse}</style><h1>近似VMD：反復回数と精度</h1>'
        '<p>128点・2 Hz・3成分・整数精度を固定。正解値は利用者提供の18 / 20 / 12 BPM。</p>'
        '<p>Python参照計算のみ。証明生成時間は未測定（None）。反復回数別の回路検証は未実施。</p>'
        f'<table><tr>{headings}</tr>{cells}</table>')


if __name__ == "__main__":
    main()
