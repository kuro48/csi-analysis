#!/usr/bin/env python3
"""Reproducible Raw CSI SC-count sweep; use --circuits for actual WASM runs."""

from __future__ import annotations
import argparse, csv, hashlib, json, platform, re, secrets, subprocess, time
from pathlib import Path
import numpy as np
from reference import prepare, estimate_integer, estimate_float, basis

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
COUNTS = [1, 2, 4, 8, 16, 32]
KEYS = ["isNormal", "selectedSubcarrier", "estimatedFrequencyBin", "globalPeakFrequencyBin"]


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def command(args, log, timeout=1800):
    begin = time.perf_counter()
    with log.open("w") as f:
        result = subprocess.run([str(x) for x in args], stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    elapsed = time.perf_counter() - begin
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {log}")
    return elapsed


def compile_circuit(count):
    directory = HERE / "build" / f"sc{count}"
    directory.mkdir(parents=True, exist_ok=True)
    source = ROOT / "zkp/circuits/csi_lomb_scargle_end_to_end.circom"
    original = source.read_text()
    marker = "    64,\n    8,\n    32,"
    if original.count(marker) != 1:
        raise ValueError("Existing circuit main parameters changed; inspect before generating sweep")
    generated = original.replace(marker, f"    64,\n    {count},\n    32,")
    (directory / "circuit.circom").write_text(generated)
    seconds = command(
        [
            ROOT / "zkp/node_modules/.bin/circom2",
            directory / "circuit.circom",
            "--O2",
            "--r1cs",
            "--wasm",
            "--sym",
            "-o",
            directory,
            "-l",
            ROOT / "zkp/node_modules",
            "-l",
            ROOT / "zkp/circuits",
        ],
        directory / "compile.log",
    )
    log = (directory / "compile.log").read_text()
    nonlinear = int(re.search(r"non-linear constraints: (\d+)", log)[1])
    linear = int(re.search(r"\nlinear constraints: (\d+)", log)[1])
    result = {
        "subcarriers": count,
        "compile_seconds": seconds,
        "nonlinear_constraints": nonlinear,
        "linear_constraints": linear,
        "constraints": nonlinear + linear,
        "compiler": "circom2 2.2.3",
        "optimization": "O2",
        "source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
    }
    dump(directory / "compile.json", result)
    return result


def witness(count, input_path, output_path="-"):
    directory = HERE / "build" / f"sc{count}" / "circuit_js"
    begin = time.perf_counter()
    proc = subprocess.run(
        [
            "node",
            str(HERE / "witness_runner.js"),
            str(directory / "circuit.wasm"),
            str(directory / "witness_calculator.js"),
            str(input_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr[-2000:])
    result = json.loads(proc.stdout)
    result["witness_process_seconds"] = time.perf_counter() - begin
    return result


def run_accuracy(circuits=False):
    windows = sorted((HERE.parent / "common/windows").glob("csi_*.npz"))
    if not windows:
        raise RuntimeError("No common Raw CSI windows yet")
    rows = []
    metadata = []
    errors = []
    manifest = json.loads((HERE.parent / "common/manifest.json").read_text())
    entries = {entry["window_id"]: entry for entry in manifest["files"] if "window_id" in entry}
    (HERE / "inputs").mkdir(exist_ok=True)
    for window in windows:
        started = time.perf_counter()
        data = np.load(window)
        entry = entries[window.stem]
        csi_meta = entry["csi_metadata_by_width"][str(entry["modal_width"])]
        tones = int(csi_meta["numTones"])
        # PicoScenes CSIArray is ColumnMajor [tones,Tx,Rx]: first block is Tx0/Rx0.
        payload, meta, all_csi, times = prepare(data["csi_complex"][:, :tones], data["timestamps_ns"])
        meta.update(
            {
                "antenna_pair": "Tx0/Rx0",
                "physical_num_tones": tones,
                "flattened_csi_width": int(data["csi_complex"].shape[1]),
            }
        )
        prep_seconds = time.perf_counter() - started
        trig = basis(payload["timestampsMs"])
        all_reference = estimate_float(all_csi, times)
        max_reference = estimate_float(all_csi[:, meta["subcarrier_indices"]], times)
        metadata.append(
            {
                "window_id": window.stem,
                **meta,
                "preparation_seconds": prep_seconds,
                "all_sc_reference": all_reference,
                "max_sc_reference": max_reference,
            }
        )
        for count in COUNTS:
            sub = {
                **payload,
                "csiI": [r[:count] for r in payload["csiI"]],
                "csiQ": [r[:count] for r in payload["csiQ"]],
            }
            input_path = HERE / "inputs" / f"{window.stem}_sc{count}.json"
            dump(input_path, sub)
            row = {
                "window_id": window.stem,
                "subcarriers": count,
                "data_kind": "real_csi",
                "physiological_ground_truth_available": False,
                "preparation_seconds": prep_seconds,
            }
            try:
                start = time.perf_counter()
                integer = estimate_integer(sub, trig)
                row["integer_reference_seconds"] = time.perf_counter() - start
                float_ref = estimate_float(all_csi[:, meta["subcarrier_indices"][:count]], times)
                row.update(integer)
                row["selected_physical_tone"] = meta["subcarrier_indices"][integer["selectedSubcarrier"]]
                row["float_all_sc_selected_physical_tone"] = all_reference["selectedSubcarrier"]
                row.update(
                    {
                        "float_same_sc_bpm": float_ref["bpm"],
                        "float_32sc_bpm": max_reference["bpm"],
                        "float_all_sc_bpm": all_reference["bpm"],
                        "absolute_difference_same_sc_bpm": abs(integer["bpm"] - float_ref["bpm"]),
                        "absolute_difference_32sc_bpm": abs(integer["bpm"] - max_reference["bpm"]),
                        "absolute_difference_all_sc_bpm": abs(integer["bpm"] - all_reference["bpm"]),
                        "same_sc_bin_agreement": integer["estimatedFrequencyBin"] == float_ref["estimatedFrequencyBin"],
                        "same_sc_subcarrier_agreement": integer["selectedSubcarrier"]
                        == float_ref["selectedSubcarrier"],
                    }
                )
                if circuits:
                    actual = witness(count, input_path)
                    row.update({k: v for k, v in actual.items() if k.endswith("seconds") or k == "max_rss_kib"})
                    row["witness_reference_match"] = all(actual[k] == integer[k] for k in KEYS)
                    if not row["witness_reference_match"]:
                        raise AssertionError(f"witness mismatch: {actual} vs {integer}")
                row["status"] = "ok"
            except Exception as exc:
                row["status"] = "error"
                row["error"] = str(exc)
                errors.append(row)
            rows.append(row)
            write_csv(HERE / "accuracy.csv", rows)
            print(window.stem, count, row["status"], flush=True)
    dump(HERE / "preprocessing.json", metadata)
    dump(HERE / "errors.json", errors)
    summary = []
    for count in COUNTS:
        selected = [r for r in rows if r["subcarriers"] == count and r["status"] == "ok"]
        result = {"subcarriers": count, "valid_windows": len(selected), "failed_windows": len(windows) - len(selected)}
        for field in [
            "absolute_difference_same_sc_bpm",
            "absolute_difference_32sc_bpm",
            "absolute_difference_all_sc_bpm",
            "same_sc_bin_agreement",
            "same_sc_subcarrier_agreement",
            "witness_seconds",
            "witness_process_seconds",
            "witness_reference_match",
        ]:
            values = [r[field] for r in selected if field in r]
            if values:
                result[field + "_mean"] = float(np.mean(values))
        summary.append(result)
    dump(HERE / "accuracy_summary.json", summary)
    write_csv(HERE / "accuracy_summary.csv", summary)
    if errors:
        raise RuntimeError(f"{len(errors)} accuracy/witness cases failed; inspect errors.json")
    return rows


def prove(count, repeats=3, ptau=None):
    directory = HERE / "build" / f"sc{count}"
    compile_info = json.loads((directory / "compile.json").read_text())
    record = {**compile_info, "proof_repeats": repeats}
    if ptau is None:
        if compile_info["constraints"] + 70 >= 2**19:
            record["proof_status"] = "not_run_ptau19_capacity"
            return record
        ptau = ROOT / "zkp/keys/powersOfTau28_hez_final_19.ptau"
    record["ptau_path"] = str(ptau)
    snark = ROOT / "zkp/node_modules/.bin/snarkjs"
    record["setup_seconds"] = command(
        [snark, "groth16", "setup", directory / "circuit.r1cs", ptau, directory / "initial.zkey"],
        directory / "setup.log",
    )
    record["contribution_seconds"] = command(
        [
            snark,
            "zkey",
            "contribute",
            directory / "initial.zkey",
            directory / "benchmark.zkey",
            "--name=2026-10-26 local research benchmark",
            "-e=" + secrets.token_hex(32),
        ],
        directory / "contribute.log",
    )
    (directory / "initial.zkey").unlink()
    record["key_status"] = "local benchmark: existing phase2 ptau plus fresh random circuit contribution"
    command(
        [snark, "zkey", "export", "verificationkey", directory / "benchmark.zkey", directory / "verification_key.json"],
        directory / "vkey.log",
    )
    inputs = sorted((HERE / "inputs").glob(f"csi_*_sc{count}.json"))
    info = witness(count, inputs[0], directory / "witness.wtns")
    record["proof_input"] = inputs[0].name
    record["witness_seconds"] = info["witness_seconds"]
    record["constraint_check_seconds"] = command(
        [snark, "wtns", "check", directory / "circuit.r1cs", directory / "witness.wtns"],
        directory / "witness_check.log",
    )
    measured = []
    for repetition in range(repeats):
        prove_s = command(
            [
                snark,
                "groth16",
                "prove",
                directory / "benchmark.zkey",
                directory / "witness.wtns",
                directory / f"proof{repetition}.json",
                directory / f"public{repetition}.json",
            ],
            directory / f"prove{repetition}.log",
        )
        verify_s = command(
            [
                snark,
                "groth16",
                "verify",
                directory / "verification_key.json",
                directory / f"public{repetition}.json",
                directory / f"proof{repetition}.json",
            ],
            directory / f"verify{repetition}.log",
        )
        verified = "OK!" in (directory / f"verify{repetition}.log").read_text()
        measured.append(
            {"repetition": repetition, "prove_seconds": prove_s, "verify_seconds": verify_s, "verified": verified}
        )
        if not verified:
            raise AssertionError("Proof did not verify")
    record.update(
        {
            "proof_status": "verified",
            "prove_seconds_median": float(np.median([x["prove_seconds"] for x in measured])),
            "prove_seconds_min": min(x["prove_seconds"] for x in measured),
            "prove_seconds_max": max(x["prove_seconds"] for x in measured),
            "verify_seconds_median": float(np.median([x["verify_seconds"] for x in measured])),
            "measurements": measured,
        }
    )
    dump(directory / "proof_metrics.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--accuracy", action="store_true")
    parser.add_argument("--circuits", action="store_true")
    parser.add_argument("--prove", action="store_true")
    parser.add_argument("--counts", default="1,2,4,8,16,32")
    parser.add_argument("--ptau", type=Path)
    args = parser.parse_args()
    counts = [int(v) for v in args.counts.split(",")]
    dump(
        HERE / "environment.json",
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "machine": platform.machine(),
            "timing_notes": "Wall-clock, shared developer machine. Other agents perform data processing and VMD. Compile/prove within LS sequential; not isolated CPU measurements.",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
    )
    if args.compile:
        rows = []
        for count in counts:
            rows.append(compile_circuit(count))
            dump(HERE / "compile_summary.json", rows)
            write_csv(HERE / "compile_summary.csv", rows)
            print(rows[-1], flush=True)
    if args.accuracy:
        run_accuracy(args.circuits)
    if args.prove:
        rows = json.loads((HERE / "proof_summary.json").read_text()) if (HERE / "proof_summary.json").exists() else []
        for count in counts:
            rows = [r for r in rows if r["subcarriers"] != count]
            rows.append(prove(count, ptau=args.ptau))
            rows.sort(key=lambda r: r["subcarriers"])
            dump(HERE / "proof_summary.json", rows)
            write_csv(HERE / "proof_summary.csv", [{k: v for k, v in r.items() if k != "measurements"} for r in rows])
            print(rows[-1], flush=True)


if __name__ == "__main__":
    main()
