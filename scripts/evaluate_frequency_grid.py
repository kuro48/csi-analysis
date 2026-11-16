"""Real CSI factorial experiment: samples 64/96/128 x frequency bins 32/64/128.

Reuse byte-identical private CSI inputs from the sample-count experiment. The
32-bin rows reuse its measured circuits/proofs; all six new profiles are run.
"""
import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from evaluate_sample_counts import (
    CAPACITY,
    COUNTS,
    REPRESENTATIVE,
    ROOT,
    read,
    save,
    selected_input,
)
from evaluate_subcarrier_selection import sha256, unique_rows
from frequency_grid_reference import (
    basis,
    estimate_float,
    estimate_integer,
    frequencies,
)

GRIDS = (32, 64, 128)
DENSE = np.linspace(127 / 2540, 1026 / 2540, 2048)
SOURCE_FILES = [
    "scripts/evaluate_frequency_grid.py",
    "scripts/frequency_grid_reference.py",
    "scripts/sample_count_witness.cjs",
    "scripts/sample_count_ledgers.mjs",
    "zkp/circuits/csi_motion_selector.circom",
    "zkp/circuits/lomb_scargle_adaptive_grid.circom",
    "zkp/circuits/lomb_scargle_csi_core.circom",
    "zkp/circuits/lomb_scargle_csi_grid_core.circom",
    "zkp/circuits/lomb_scargle_timestamp_grid_basis.circom",
    "zkp/circuits/lomb_scargle_timestamp_basis.circom",
    "fabric/chaincode/lib/proof.js",
    "fabric/chaincode/lib/observations.js",
    "fabric/scripts/prepare-chaincode.mjs",
    "fabric/gateway.mjs",
] + [f"zkp/experiments/frequency-grid/n{n}k{k}.circom" for n in COUNTS for k in (64, 128)]


def pin(work):
    current = {name: sha256(ROOT / name) for name in SOURCE_FILES}
    path = work / "source-hashes.json"
    if path.exists():
        if read(path) != current:
            raise ValueError("Measured source changed; use a new workdir or explicitly revalidate affected stages")
    else:
        save(path, current)


def prepare(work, previous):
    from app.services.breathing_pipeline import load_csi_matrix_with_timestamps

    if (work / "datasets.json").exists():
        raise ValueError("Preserve existing prepared references")
    pin(work)
    base = read(previous / "datasets.json")
    spectral = read(previous / "spectral-reference.json")
    assert base["realOnly"] and spectral["realOnly"]
    old = {row["name"]: row for row in spectral["results"]}
    results = []
    for dataset in base["datasets"]:
        if "excluded" in dataset:
            results.append(dataset)
            continue
        name = dataset["name"]
        source = ROOT / "sampledata" / f"{name}.csi"
        assert sha256(source) == dataset["sourceSha256"] == old[name]["sourceSha256"]
        print(f"Prepare fixed-grid references: {name}", flush=True)
        matrix, timestamps = load_csi_matrix_with_timestamps(str(source))
        rows = unique_rows(timestamps)
        scaled = matrix[rows] * dataset["sharedIqScale"]
        times_ms = np.rint((timestamps[rows] - timestamps[rows[0]]).astype(float) / 1e6).astype(np.int64)
        full_column = dataset["fullPython"]["selectedSubcarrier"]
        full = estimate_float(scaled[:, [full_column]], times_ms / 1000, DENSE)
        full["selectedSubcarrier"] = full_column
        sensitivity = estimate_float(scaled[:, [full_column]], times_ms / 1000, np.linspace(DENSE[0], DENSE[-1], 4096))
        sensitivity["selectedSubcarrier"] = full_column
        entry = {key: value for key, value in dataset.items() if key not in ("variants", "fullPython")}
        entry.update(
            fullDensePython=full,
            full4096Python=sensitivity,
            previousSpectralPython=old[name]["fullSpectralPython"],
            variants={},
        )
        for n in COUNTS:
            old_input = previous / "inputs" / f"{name}-n{n}.json"
            assert sha256(old_input) == dataset["variants"][str(n)]["inputSha256"]
            dest = work / "inputs" / old_input.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(old_input, dest)
            dest.chmod(0o600)
            data = read(dest)
            column = dataset["variants"][str(n)]["integerPython"]["selectedSubcarrier"]
            selected = selected_input(data, column)
            iq = (
                np.asarray(selected["csiI"], dtype=float)
                - 2048
                + 1j * (np.asarray(selected["csiQ"], dtype=float) - 2048)
            )
            same_dense = estimate_float(iq, np.asarray(data["timestampsMs"]) / 1000, DENSE)
            same_dense["selectedSubcarrier"] = column
            full_same = estimate_float(scaled[:, [column]], times_ms / 1000, DENSE)
            full_same["selectedSubcarrier"] = column
            for k in GRIDS:
                integer = estimate_integer(selected, k)
                integer["selectedSubcarrier"] = column
                floating = estimate_float(iq, np.asarray(data["timestampsMs"]) / 1000, frequencies(k))
                floating["selectedSubcarrier"] = column
                if k == 32:
                    assert integer == dataset["variants"][str(n)]["integerPython"]
                entry["variants"][f"n{n}k{k}"] = {
                    "sampleCount": n,
                    "frequencyGridCount": k,
                    "inputSha256": sha256(dest),
                    "integerPython": integer,
                    "floatSameGrid": floating,
                    "floatSamePointsDense": same_dense,
                    "floatFullSameColumnDense": full_same,
                }
        results.append(entry)
        save(work / "preparation-progress.json", results)
    save(
        work / "datasets.json",
        {
            "realOnly": True,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "previousWork": str(previous),
            "previousDatasetSha256": sha256(previous / "datasets.json"),
            "previousSpectralSha256": sha256(previous / "spectral-reference.json"),
            "sampleCounts": COUNTS,
            "frequencyGridCounts": GRIDS,
            "denseReferenceCount": len(DENSE),
            "denseReferenceHz": DENSE.tolist(),
            "normalBandHz": [0.1, 22 / 60],
            "datasets": results,
        },
    )


def evaluate(work, n, k):
    pin(work)
    dataset_info = read(work / "datasets.json")
    previous = Path(dataset_info["previousWork"])
    target = work / f"n{n}k{k}"
    target.mkdir(exist_ok=True)
    wasm = target / "build" / f"n{n}k{k}_js" / f"n{n}k{k}.wasm"
    results = []
    for dataset in dataset_info["datasets"]:
        if "excluded" in dataset:
            continue
        name = dataset["name"]
        reference = dataset["variants"][f"n{n}k{k}"]
        input_path = work / "inputs" / f"{name}-n{n}.json"
        assert sha256(input_path) == reference["inputSha256"]
        output = target / name
        output.mkdir(exist_ok=True)
        if k == 32:
            execution = read(previous / f"n{n}" / name / "public.json")
            # Hash the exact saved public vector reused for this baseline.
            save(output / "public.json", execution)
        else:
            command = [
                "node",
                str(ROOT / "scripts/sample_count_witness.cjs"),
                str(wasm),
                str(input_path),
                str(output / "public.json"),
            ]
            if name == REPRESENTATIVE:
                command.append(str(output / "witness.wtns"))
            print(f"Witness n{n}k{k}: {name}", flush=True)
            with (output / "witness.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            execution = read(output / "public.json")
        signals = execution["publicSignals"]
        actual = dict(
            zip(
                ["isNormal", "selectedSubcarrier", "estimatedFrequencyBin", "globalPeakFrequencyBin"],
                map(int, signals[1:5]),
            )
        )
        assert all(actual[key] == reference["integerPython"][key] for key in actual), (n, k, name, actual, reference)
        actual["global_bpm"] = float(frequencies(k)[actual["globalPeakFrequencyBin"]] * 60)
        actual["bpm"] = float(frequencies(k)[actual["estimatedFrequencyBin"]] * 60)
        diffs = {}
        for label, ref in [
            ("sameGrid", reference["floatSameGrid"]),
            ("samePointsDense", reference["floatSamePointsDense"]),
            ("fullSameColumnDense", reference["floatFullSameColumnDense"]),
            ("fullDense", dataset["fullDensePython"]),
        ]:
            diffs[label] = {
                "globalBpmAbsoluteDifference": abs(actual["global_bpm"] - ref["global_bpm"]),
                "normalBandBpmAbsoluteDifference": abs(actual["bpm"] - ref["bpm"]),
                "isNormalMatches": actual["isNormal"] == ref["isNormal"],
                "selectionMatches": actual["selectedSubcarrier"] == ref["selectedSubcarrier"],
            }
        spectral = dataset["previousSpectralPython"]
        diffs["previousSpectral"] = {
            "globalBpmAbsoluteDifference": abs(actual["global_bpm"] - spectral["globalBpm"]),
            "isNormalMatches": actual["isNormal"] == spectral["isNormal"],
            "selectionMatches": actual["selectedSubcarrier"] == spectral["selectedSubcarrier"],
        }
        results.append(
            {
                "name": name,
                "sampleCount": n,
                "frequencyGridCount": k,
                "circuit": actual,
                "integerReferenceMatches": True,
                "differences": diffs,
                "witnessMs": execution["witnessMs"],
                "witnessBytes": execution["witnessBytes"],
                "publicSha256": sha256(output / "public.json"),
            }
        )
    save(
        target / "evaluation.json",
        {
            "sampleCount": n,
            "frequencyGridCount": k,
            "baselineReused": k == 32,
            "wasmSha256": sha256(wasm) if k != 32 else read(previous / f"n{n}/evaluation.json")["wasmSha256"],
            "results": results,
        },
    )


def setup(work, n, k):
    pin(work)
    target = work / f"n{n}k{k}"
    files = {
        "prover": ROOT / "zkp/native-prover/target/release/csi-native-prover",
        "r1cs": target / "build" / f"n{n}k{k}.r1cs",
        "wasm": target / "build" / f"n{n}k{k}_js" / f"n{n}k{k}.wasm",
        "provingKey": target / "proving_key.ark",
        "verificationKey": target / "verification_key.json",
    }
    if files["provingKey"].exists() or files["verificationKey"].exists():
        raise ValueError("Refusing to overwrite setup")
    started = time.perf_counter()
    with (target / "setup.log").open("w") as log:
        subprocess.run(
            [
                "/usr/bin/time",
                "-l",
                str(files["prover"]),
                "setup",
                str(files["r1cs"]),
                str(files["provingKey"]),
                str(files["verificationKey"]),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    save(
        target / "artifacts.json",
        {
            "circuit": f"csi_lomb_scargle_adaptive_n{n}_k{k}_c4004",
            "sampleCount": n,
            "frequencyGridCount": k,
            "capacity": CAPACITY,
            "publicSignalCount": n + 6,
            "isNormalIndex": 1,
            "experiment": "frequency-grid-v1",
            "setup": "single-party-local-csprng-testnet-only",
            "setupSeconds": time.perf_counter() - started,
            "files": {key: str(v) for key, v in files.items()},
            "sha256": {key: sha256(v) for key, v in files.items()},
        },
    )


def prove(work, n, k):
    pin(work)
    target = work / f"n{n}k{k}"
    manifest = read(target / "artifacts.json")
    for key, value in manifest["files"].items():
        assert sha256(value) == manifest["sha256"][key]
    out = target / REPRESENTATIVE
    if (out / "bundle.json").exists():
        raise ValueError("Preserve existing proof")
    started = time.perf_counter()
    with (out / "prove.log").open("w") as log:
        subprocess.run(
            [
                "/usr/bin/time",
                "-l",
                manifest["files"]["prover"],
                "prove",
                manifest["files"]["r1cs"],
                manifest["files"]["provingKey"],
                str(out / "witness.wtns"),
                str(out / "bundle.json"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    elapsed = time.perf_counter() - started
    bundle = read(out / "bundle.json")
    assert bundle["publicSignals"] == read(out / "public.json")["publicSignals"]
    save(
        out / "prove-metrics.json",
        {
            "proveSeconds": elapsed,
            "repetitions": 1,
            "publicSignalCount": n + 6,
            "includes": "R1CS/witness/key loading, key group checks, all R1CS checks, Groth16 proving, native verification",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "setup", "prove"])
    parser.add_argument("--work", type=Path, default=ROOT / ".local/frequency-grid")
    parser.add_argument("--previous", type=Path, default=ROOT / ".local/sample-count")
    parser.add_argument("--samples", type=int, choices=COUNTS)
    parser.add_argument("--grid", type=int, choices=GRIDS)
    args = parser.parse_args()
    args.work = args.work.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.stage == "prepare":
        prepare(args.work, args.previous.resolve())
    else:
        if args.samples is None or args.grid is None:
            parser.error("--samples and --grid required")
        globals()[args.stage](args.work, args.samples, args.grid)


if __name__ == "__main__":
    main()
