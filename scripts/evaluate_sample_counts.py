"""Real CSI only: compare 64/96/128 points against same-method Python references.

Commands checkpoint preparation, circuit execution, setup, and actual proving.
Ledger recording and verification are measured by sample_count_ledgers.mjs.
"""
import argparse
import importlib.util
import json
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from evaluate_subcarrier_selection import (
    exact_scores,
    float_scores,
    rank,
    sha256,
    unique_rows,
    winner,
)

ROOT = Path(__file__).resolve().parents[1]
COUNTS = (64, 96, 128)
CAPACITY = 4004
REPRESENTATIVE = "csi_20260519_114943"
FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617
REFERENCE = ROOT / "zkp/experiments/2026-10-26/lomb/reference.py"
spec = importlib.util.spec_from_file_location("sample_count_lomb_reference", REFERENCE)
lomb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lomb)


def save(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    if private:
        path.chmod(0o600)


def read(path):
    return json.loads(path.read_text())


def selected_input(data, column):
    return {
        "csiI": [[row[column]] for row in data["csiI"]],
        "csiQ": [[row[column]] for row in data["csiQ"]],
        "timestampsMs": data["timestampsMs"],
    }


def prepare(work, captures):
    from app.services.breathing_pipeline import load_csi_matrix_with_timestamps

    if (work / "datasets.json").exists():
        raise ValueError("Preparation already exists; use a new work directory")
    results = []
    for path in captures:
        print(f"Preparing real capture {path.name}", flush=True)
        result = {"name": path.stem, "sourceSha256": sha256(path)}
        try:
            matrix, timestamps = load_csi_matrix_with_timestamps(str(path))
            if not 1 <= matrix.shape[1] <= CAPACITY:
                raise ValueError("candidate_capacity_exceeded")
            if not np.all(np.isfinite(matrix)):
                raise ValueError("nonfinite_csi")
            rows = unique_rows(timestamps)
            matrix = matrix[rows]
            times = np.rint((timestamps[rows] - timestamps[rows[0]]).astype(float) / 1e6).astype(np.int64)
            if len(rows) < max(COUNTS) or times[-1] >= 2**24:
                raise ValueError("insufficient_unique_times_or_duration_overflow")
            peak = max(np.abs(matrix.real).max(), np.abs(matrix.imag).max())
            if peak <= 0:
                raise ValueError("zero_csi")
            scale = 1800.0 / float(peak)  # FIXED across N, using the full real capture.
            scaled = matrix * scale
            full_scores = float_scores(scaled)
            full_column = winner(full_scores)
            if full_column is None:
                raise ValueError("no_full_reference_candidate")
            full_estimate = lomb.estimate_float(scaled[:, [full_column]], times / 1000)
            full_estimate["selectedSubcarrier"] = full_column
            result.update(
                {
                    "candidateCount": matrix.shape[1],
                    "fullPointCount": len(rows),
                    "durationMs": int(times[-1]),
                    "sharedIqScale": scale,
                    "fullPython": full_estimate,
                    "variants": {},
                }
            )
            for n in COUNTS:
                chosen_rows = np.rint(np.linspace(0, len(rows) - 1, n)).astype(int)
                sampled = scaled[chosen_rows]
                iq_i = np.rint(sampled.real).astype(np.int64)
                iq_q = np.rint(sampled.imag).astype(np.int64)
                count = matrix.shape[1]
                data = {
                    "csiI": np.pad(iq_i + 2048, ((0, 0), (0, CAPACITY - count)), constant_values=2048).tolist(),
                    "csiQ": np.pad(iq_q + 2048, ((0, 0), (0, CAPACITY - count)), constant_values=2048).tolist(),
                    "timestampsMs": times[chosen_rows].tolist(),
                    "candidateCount": count,
                    "commitmentNonce": str(secrets.randbelow(FR - 1) + 1),
                }
                scores = exact_scores(data)
                column = winner(scores)
                if column is None:
                    raise ValueError(f"no_candidate_n{n}")
                integer_estimate = lomb.estimate_integer(selected_input(data, column))
                integer_estimate["selectedSubcarrier"] = column
                quantized = iq_i + 1j * iq_q
                float_column = winner(float_scores(quantized))
                same = lomb.estimate_float(quantized[:, [float_column]], times[chosen_rows] / 1000)
                same["selectedSubcarrier"] = float_column
                unquantized_column = winner(float_scores(sampled))
                unquantized = lomb.estimate_float(sampled[:, [unquantized_column]], times[chosen_rows] / 1000)
                unquantized["selectedSubcarrier"] = unquantized_column
                full_same_column = lomb.estimate_float(scaled[:, [column]], times / 1000)
                full_same_column["selectedSubcarrier"] = column
                filename = work / "inputs" / f"{path.stem}-n{n}.json"
                save(filename, data, private=True)
                result["variants"][str(n)] = {
                    "sampleCount": n,
                    "inputSha256": sha256(filename),
                    "sourceRows": rows[chosen_rows].tolist(),
                    "integerPython": integer_estimate,
                    "floatSamePoints": same,
                    "floatUnquantizedSamePoints": unquantized,
                    "floatFullSameColumn": full_same_column,
                    "fullReferenceRank": rank(full_scores, column),
                    "fullReferenceScoreRatio": float(full_scores[column] / full_scores[full_column]),
                }
            del matrix, scaled
        except ValueError as error:
            result = {"name": path.stem, "sourceSha256": result["sourceSha256"], "excluded": str(error)}
        results.append(result)
        save(work / "preparation-progress.json", results)
    save(
        work / "datasets.json",
        {
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "realOnly": True,
            "sampleCounts": COUNTS,
            "capacity": CAPACITY,
            "referenceSha256": sha256(REFERENCE),
            "scalePolicy": "one shared scale from all unique real frames, fixed across sample counts",
            "samplingPolicy": "rounded linspace in observation index; same first and last timestamps",
            "datasets": results,
        },
    )


def artifacts(work, n):
    if n == 64:
        existing = read(ROOT / ".local/circom-adaptive-4004/artifacts.json")
        return existing
    return read(work / f"n{n}" / "artifacts.json")


def wasm_path(work, n):
    if n == 64:
        return Path(artifacts(work, n)["files"]["wasm"])
    return work / f"n{n}" / "build" / f"n{n}_js" / f"n{n}.wasm"


def evaluate(work, n):
    datasets = read(work / "datasets.json")
    wasm = wasm_path(work, n)
    results = []
    for dataset in datasets["datasets"]:
        if "excluded" in dataset:
            continue
        name = dataset["name"]
        target = work / f"n{n}" / name
        target.mkdir(parents=True, exist_ok=True)
        input_path = work / "inputs" / f"{name}-n{n}.json"
        reference = dataset["variants"][str(n)]
        if sha256(input_path) != reference["inputSha256"]:
            raise ValueError("Input changed after reference computation")
        command = [
            "node",
            str(ROOT / "scripts/sample_count_witness.cjs"),
            str(wasm),
            str(input_path),
            str(target / "public.json"),
        ]
        if name == REPRESENTATIVE:
            command.append(str(target / "witness.wtns"))
        print(f"Witness n={n} {name}", flush=True)
        with (target / "witness.log").open("w") as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        execution = read(target / "public.json")
        signals = execution["publicSignals"]
        actual = {
            key: int(signals[index])
            for key, index in [
                ("isNormal", 1),
                ("selectedSubcarrier", 2),
                ("estimatedFrequencyBin", 3),
                ("globalPeakFrequencyBin", 4),
            ]
        }
        assert all(actual[key] == reference["integerPython"][key] for key in actual), (name, n, actual, reference)
        actual["global_bpm"] = float(lomb.FREQUENCIES[actual["globalPeakFrequencyBin"]] * 60)
        result = {
            "name": name,
            "sampleCount": n,
            "circuit": actual,
            "integerReferenceMatches": True,
            "witnessMs": execution["witnessMs"],
            "witnessBytes": execution["witnessBytes"],
            "python": reference,
            "fullPython": dataset["fullPython"],
            "differences": {},
        }
        for key, ref in [
            ("samePoints", reference["floatSamePoints"]),
            ("unquantizedSamePoints", reference["floatUnquantizedSamePoints"]),
            ("fullPoints", dataset["fullPython"]),
            ("fullPointsSameColumn", reference["floatFullSameColumn"]),
        ]:
            result["differences"][key] = {
                "selectedColumnMatches": actual["selectedSubcarrier"] == ref["selectedSubcarrier"],
                "isNormalMatches": actual["isNormal"] == ref["isNormal"],
                "globalBinMatches": actual["globalPeakFrequencyBin"] == ref["globalPeakFrequencyBin"],
                "globalBpmAbsoluteDifference": abs(actual["global_bpm"] - ref["global_bpm"]),
            }
        save(target / "evaluation.json", result)
        results.append(result)
    save(work / f"n{n}" / "evaluation.json", {"sampleCount": n, "wasmSha256": sha256(wasm), "results": results})


def setup(work, n):
    if n == 64:
        return
    target = work / f"n{n}"
    key = target / "proving_key.ark"
    vk = target / "verification_key.json"
    if key.exists() or vk.exists():
        raise ValueError("Refusing to overwrite an existing setup")
    native = ROOT / "zkp/native-prover/target/release/csi-native-prover"
    r1cs = target / "build" / f"n{n}.r1cs"
    started = time.perf_counter()
    with (target / "setup.log").open("w") as log:
        subprocess.run(
            ["/usr/bin/time", "-l", str(native), "setup", str(r1cs), str(key), str(vk)],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    files = {"prover": native, "r1cs": r1cs, "wasm": wasm_path(work, n), "provingKey": key, "verificationKey": vk}
    save(
        target / "artifacts.json",
        {
            "circuit": f"csi_lomb_scargle_adaptive_n{n}_c4004",
            "sampleCount": n,
            "capacity": 4004,
            "publicSignalCount": n + 6,
            "isNormalIndex": 1,
            "experiment": "sample-count-v1",
            "setup": "single-party-local-csprng-testnet-only",
            "setupSeconds": time.perf_counter() - started,
            "files": {k: str(v) for k, v in files.items()},
            "sha256": {k: sha256(v) for k, v in files.items()},
        },
    )


def prove(work, n):
    manifest = artifacts(work, n)
    for key, filename in manifest["files"].items():
        if sha256(filename) != manifest["sha256"][key]:
            raise ValueError(f"Artifact changed: {key}")
    target = work / f"n{n}" / REPRESENTATIVE
    output = target / "bundle.json"
    if output.exists():
        raise ValueError("Proof already exists; preserve timing evidence")
    started = time.perf_counter()
    with (target / "prove.log").open("w") as log:
        subprocess.run(
            [
                "/usr/bin/time",
                "-l",
                manifest["files"]["prover"],
                "prove",
                manifest["files"]["r1cs"],
                manifest["files"]["provingKey"],
                str(target / "witness.wtns"),
                str(output),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    seconds = time.perf_counter() - started
    bundle = read(output)
    assert bundle["publicSignals"] == read(target / "public.json")["publicSignals"]
    save(
        target / "prove-metrics.json",
        {
            "proveSeconds": seconds,
            "includes": "R1CS/witness/key loading, key group checks, all R1CS checks, Groth16 proving, native verification",
            "proofBytes": len(json.dumps(bundle["proof"]).encode()),
            "bundleBytes": output.stat().st_size,
            "publicSignalCount": len(bundle["publicSignals"]),
            "repetitions": 1,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "setup", "prove"])
    parser.add_argument("--work", type=Path, default=ROOT / ".local/sample-count")
    parser.add_argument("--samples", type=int, choices=COUNTS)
    parser.add_argument("captures", type=Path, nargs="*")
    args = parser.parse_args()
    args.work = args.work.resolve()
    if args.stage == "prepare":
        prepare(args.work, args.captures or sorted((ROOT / "sampledata").glob("*.csi")))
    else:
        if args.samples is None:
            parser.error("--samples is required")
        {"evaluate": evaluate, "setup": setup, "prove": prove}[args.stage](args.work, args.samples)


if __name__ == "__main__":
    main()
