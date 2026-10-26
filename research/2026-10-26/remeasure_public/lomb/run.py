#!/usr/bin/env python3
"""Each compared proof exposes and binds its own intermediate values. No diagnostic artifacts imported."""

from __future__ import annotations
import argparse, csv, hashlib, json, math, os, re, secrets, shutil, struct, subprocess, time, uuid
from pathlib import Path
from schema import FIELD, NORMAL, fields, source, names, decode, validate, trace

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
ROOT = HERE.parents[3]
COUNTS = [1, 2, 4, 8, 16, 32]
REP = "csi_20260526_034004_w0"


def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read(p):
    return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact(p):
    return {"path": str(p.relative_to(HERE)), "sha256": sha(p)}


def command(args, log, timeout=1800, env=None, allow_failure=False):
    start = time.perf_counter()
    with log.open("w") as f:
        result = subprocess.run([str(x) for x in args], stdout=f, stderr=subprocess.STDOUT, timeout=timeout, env=env)
    result_data = {"seconds": time.perf_counter() - start, "returncode": result.returncode}
    if result.returncode and not allow_failure:
        raise RuntimeError(f"{log.name} exit={result.returncode}")
    return result_data


def update_index():
    plan = read(HERE / "plan.json")
    runs = []
    for p in plan["runs"]:
        m = read(HERE / p["manifest_path"])
        runs.append(
            {
                k: m.get(k)
                for k in ["run_id", "config_id", "subcarriers", "window_id", "repeat_id", "status", "verified"]
            }
            | {"manifest_path": p["manifest_path"]}
        )
    dump(HERE / "index.json", {"campaign_id": plan["campaign_id"], "root_path": str(HERE), "runs": runs})


def prepare():
    if (HERE / "plan.json").exists():
        return read(HERE / "plan.json")
    campaign = "ls-public-" + uuid.uuid4().hex[:12]
    original = ROOT / "zkp/circuits/csi_lomb_scargle_end_to_end.circom"
    basis = ROOT / "zkp/circuits/lomb_scargle_timestamp_basis.circom"
    dependencies = {
        str(p.relative_to(ROOT)): sha(p)
        for p in [original, basis, *sorted((ROOT / "zkp/node_modules/circomlib/circuits").rglob("*.circom"))]
    }
    old_rows = list(csv.DictReader((BASE / "lomb/accuracy.csv").open()))
    old = {(r["window_id"], int(r["subcarriers"])): r for r in old_rows}
    mappings = {r["window_id"]: r for r in read(BASE / "lomb/preprocessing.json")}
    windows = sorted(mappings)
    assert len(windows) == 8 and REP in windows
    plan = {
        "campaign_id": campaign,
        "representative_window": REP,
        "subcarrier_counts": COUNTS,
        "runs": [],
        "source_dependencies_sha256": dependencies,
        "old_accuracy_sha256": sha(BASE / "lomb/accuracy.csv"),
        "input_policy": "byte-identical original normal comparison input, including nonce; never diagnostic input",
        "reuse_policy": "No diagnostic proof, public, decoded, trace, key, R1CS or WASM is reused.",
    }
    for count in COUNTS:
        directory = HERE / "configs" / f"sc{count}"
        directory.mkdir(parents=True, exist_ok=True)
        generated = directory / "circuit.circom"
        generated.write_text(source(original.read_text(), count))
        fs = fields(count)
        total = sum(f["count"] for f in fs)
        schema = {
            "field_modulus": str(FIELD),
            "subcarriers": count,
            "fields": fs,
            "n_outputs": total - 64,
            "n_public_inputs": 64,
            "n_public_total": total,
            "array_order": "row-major; final index fastest",
            "integer_encoding": "decimal strings",
            "signed_decode": "subtract field modulus only for signed fields > p/2",
            "source_sha256": sha(generated),
        }
        dump(directory / "source_schema.json", schema)
        normal = read(BASE / "lomb/build" / f"sc{count}" / "compile.json")
        dump(
            directory / "status.json",
            {
                "config_id": f"sc{count}",
                "status": "prepared_no_compute",
                "predicted_constraints": normal["constraints"] + 64 * count,
                "prediction_note": "Not measured; based on previous8SC public alias delta512. Actual compilation/header will override.",
                "predicted_public_signals": total,
            },
        )
        cases = [(w, 0) for w in windows] + [(REP, 1), (REP, 2)]
        for window, repeat in cases:
            run_id = f"{campaign}-sc{count}-{window}-r{repeat}"
            d = HERE / "runs" / run_id
            d.mkdir(parents=True)
            origin = BASE / "lomb/inputs" / f"{window}_sc{count}.json"
            shutil.copyfile(origin, d / "input.json")
            assert sha(origin) == sha(d / "input.json")
            expected = {k: int(old[(window, count)][k]) for k in NORMAL[1:]}
            dump(d / "expected_normal_outputs.json", expected)
            manifest = {
                "run_id": run_id,
                "campaign_id": campaign,
                "config_id": f"sc{count}",
                "subcarriers": count,
                "window_id": window,
                "repeat_id": repeat,
                "is_representative": window == REP,
                "status": "prepared_no_compute",
                "verified": False,
                "input_origin": str(origin.relative_to(ROOT)),
                "input_origin_sha256": sha(origin),
                "physical_tone_mapping": mappings[window]["subcarrier_indices"][:count],
                "artifacts": {
                    "input": artifact(d / "input.json"),
                    "source": artifact(generated),
                    "source_schema": artifact(directory / "source_schema.json"),
                    "expected_normal_outputs": artifact(d / "expected_normal_outputs.json"),
                },
                "timings": {},
                "decoded_from": None,
            }
            dump(d / "manifest.json", manifest)
            plan["runs"].append(
                {
                    "run_id": run_id,
                    "config_id": f"sc{count}",
                    "manifest_path": str((d / "manifest.json").relative_to(HERE)),
                }
            )
    dump(HERE / "plan.json", plan)
    update_index()
    return plan


def r1cs_header(path):
    with path.open("rb") as f:
        assert f.read(4) == b"r1cs"
        version, nsections = struct.unpack("<II", f.read(8))
        assert version == 1
        for _ in range(nsections):
            kind, length = struct.unpack("<IQ", f.read(12))
            if kind != 1:
                f.seek(length, 1)
                continue
            n8 = struct.unpack("<I", f.read(4))[0]
            prime = int.from_bytes(f.read(n8), "little")
            assert prime == FIELD
            wires, outputs, public_inputs, private_inputs = struct.unpack("<IIII", f.read(16))
            labels = struct.unpack("<Q", f.read(8))[0]
            constraints = struct.unpack("<I", f.read(4))[0]
            return {
                "wires": wires,
                "outputs": outputs,
                "public_inputs": public_inputs,
                "private_inputs": private_inputs,
                "labels": labels,
                "constraints": constraints,
            }
    raise ValueError("R1CS header missing")


def check_layout(sym, schema):
    required = {
        f"main.{n}": f["public_start_zero_based"] + j + 1
        for f in schema["fields"]
        for j, n in enumerate(names(f["name"], f["shape"]))
    }
    seen = {}
    with sym.open() as source_file:
        for line in source_file:
            _, w, _, name = line.strip().split(",", 3)
            if name in required:
                assert int(w) == required[name], name
                seen[name] = int(w)
    assert len(seen) == len(required)


def witness_public(path, total):
    with path.open("rb") as f:
        assert f.read(4) == b"wtns"
        version, nsections = struct.unpack("<II", f.read(8))
        assert version == 2
        for _ in range(nsections):
            kind, length = struct.unpack("<IQ", f.read(12))
            if kind == 1:
                n8 = struct.unpack("<I", f.read(4))[0]
                assert int.from_bytes(f.read(n8), "little") == FIELD
                f.seek(length - 4 - n8, 1)
            elif kind == 2:
                f.seek(n8, 1)
                return [str(int.from_bytes(f.read(n8), "little")) for _ in range(total)]
            else:
                f.seek(length, 1)
    raise ValueError("Witness section missing")


def run_config(count, ptau, timeout, heap, prune_key=False):
    config = HERE / "configs" / f"sc{count}"
    build = HERE / "_build" / f"sc{count}"
    build.mkdir(parents=True, exist_ok=True)
    status = read(config / "status.json")
    if status.get("status") == "complete":
        raise RuntimeError("Completed config is immutable; create a new campaign directory")
    for rel, digest in read(HERE / "plan.json")["source_dependencies_sha256"].items():
        assert sha(ROOT / rel) == digest, rel
    schema = read(config / "source_schema.json")
    assert sha(config / "circuit.circom") == schema["source_sha256"]
    env = dict(os.environ)
    env["NODE_OPTIONS"] = f"--max-old-space-size={heap}"
    snark = ROOT / "zkp/node_modules/.bin/snarkjs"
    status.update(status="running", heap_limit_mib=heap, setup_timeout_seconds=timeout, ptau_path=str(ptau))
    dump(config / "status.json", status)
    stage = "compile"
    try:
        status["compile_seconds"] = command(
            [
                ROOT / "zkp/node_modules/.bin/circom2",
                config / "circuit.circom",
                "--O2",
                "--r1cs",
                "--wasm",
                "--sym",
                "-o",
                build,
                "-l",
                ROOT / "zkp/node_modules",
                "-l",
                ROOT / "zkp/circuits",
            ],
            config / "compile.log",
            timeout,
            env,
        )["seconds"]
        header = r1cs_header(build / "circuit.r1cs")
        assert header["outputs"] == schema["n_outputs"] and header["public_inputs"] == 64
        check_layout(build / "circuit.sym", schema)
        domain = 1 << (header["constraints"] + schema["n_public_total"]).bit_length()
        status.update(r1cs_header=header, domain_upper_bound=domain, layout_checked=True)
        assert domain <= 2**21, "ptau21 capacity exceeded including public signals"
        binaries = {"r1cs": artifact(build / "circuit.r1cs"), "wasm": artifact(build / "circuit_js/circuit.wasm")}
        dump(config / "compile.json", status | {"artifacts": binaries})
        stage = "setup"
        status["setup_seconds"] = command(
            [snark, "groth16", "setup", build / "circuit.r1cs", ptau, build / "initial.zkey"],
            config / "setup.log",
            timeout,
            env,
        )["seconds"]
        stage = "contribution"
        status["contribution_seconds"] = command(
            [
                snark,
                "zkey",
                "contribute",
                build / "initial.zkey",
                build / "final.zkey",
                "--name=per-comparison-public-stages",
                "-e=" + secrets.token_hex(32),
            ],
            config / "contribute.log",
            timeout,
            env,
        )["seconds"]
        (build / "initial.zkey").unlink()
        command(
            [snark, "zkey", "export", "verificationkey", build / "final.zkey", config / "verification_key.json"],
            config / "vkey.log",
            120,
            env,
        )
        status["verification_key"] = artifact(config / "verification_key.json")
        status["proving_key_sha256"] = sha(build / "final.zkey")
        stage = "proofs"
        dump(config / "status.json", status)
        cases = [p for p in read(HERE / "plan.json")["runs"] if p["config_id"] == f"sc{count}"]
        for case in cases:
            mpath = HERE / case["manifest_path"]
            m = read(mpath)
            d = mpath.parent
            assert m["artifacts"]["input"]["sha256"] == sha(d / "input.json")
            m["status"] = "running"
            dump(mpath, m)
            wt = build / f"{m['run_id']}.wtns"
            m["timings"]["witness_seconds"] = command(
                [
                    "node",
                    build / "circuit_js/generate_witness.js",
                    build / "circuit_js/circuit.wasm",
                    d / "input.json",
                    wt,
                ],
                d / "witness.log",
                300,
                env,
            )["seconds"]
            prefix = witness_public(wt, schema["n_public_total"])
            m["witness_sha256"] = sha(wt)
            m["timings"]["witness_constraint_check_seconds"] = command(
                [snark, "wtns", "check", build / "circuit.r1cs", wt], d / "constraint_check.log", 300, env
            )["seconds"]
            m["timings"]["prove_seconds"] = command(
                [snark, "groth16", "prove", build / "final.zkey", wt, d / "proof.json", d / "public.json"],
                d / "prove.log",
                timeout,
                env,
            )["seconds"]
            m["timings"]["verify_seconds"] = command(
                [snark, "groth16", "verify", config / "verification_key.json", d / "public.json", d / "proof.json"],
                d / "verify.log",
                300,
                env,
            )["seconds"]
            assert "OK!" in (d / "verify.log").read_text()
            assert read(d / "public.json") == prefix
            del prefix
            public = read(d / "public.json")
            decoded = decode(public, schema)
            validation = validate(decoded, read(d / "input.json"), read(d / "expected_normal_outputs.json"))
            tamper = next(f for f in schema["fields"] if f["name"] == "debugMagnitudeSquared")[
                "public_start_zero_based"
            ]
            modified = public.copy()
            modified[tamper] = str((int(modified[tamper]) + 1) % FIELD)
            dump(d / "public_tampered.json", modified)
            negative = command(
                [
                    snark,
                    "groth16",
                    "verify",
                    config / "verification_key.json",
                    d / "public_tampered.json",
                    d / "proof.json",
                ],
                d / "tamper.log",
                300,
                env,
                True,
            )
            assert negative["returncode"] != 0 and "invalid proof" in (d / "tamper.log").read_text().lower()
            m["timings"]["tamper_verify_seconds"] = negative["seconds"]
            m["artifacts"].update(
                binaries
                | {
                    "verification_key": artifact(config / "verification_key.json"),
                    "proof": artifact(d / "proof.json"),
                    "public": artifact(d / "public.json"),
                }
            )
            provenance = {
                "run_id": m["run_id"],
                "config_id": m["config_id"],
                "window_id": m["window_id"],
                "repeat_id": m["repeat_id"],
                "verified": True,
                "source": m["artifacts"]["source"],
                "source_schema": m["artifacts"]["source_schema"],
                "input": m["artifacts"]["input"],
                "verification_key": m["artifacts"]["verification_key"],
                "proof": m["artifacts"]["proof"],
                "public": m["artifacts"]["public"],
            }
            dump(
                d / "decoded_public.json",
                {"provenance": provenance, "decoded_from": m["artifacts"]["public"], "data": decoded},
            )
            dump(
                d / "trace.json",
                {
                    "provenance": provenance,
                    "decoded_from": m["artifacts"]["public"],
                    "data": trace(decoded, m["physical_tone_mapping"]),
                },
            )
            dump(
                d / "validation.json",
                validation
                | {
                    "verified": True,
                    "public_equals_actual_witness_prefix": True,
                    "intermediate_tamper_rejected": True,
                    "tampered_public_index": tamper,
                },
            )
            m["artifacts"].update(
                {
                    name: artifact(d / file)
                    for name, file in [
                        ("decoded_public", "decoded_public.json"),
                        ("trace", "trace.json"),
                        ("validation", "validation.json"),
                    ]
                }
            )
            m.update(status="verified", verified=True, decoded_from=m["artifacts"]["public"], witness_retained=False)
            dump(mpath, m)
            wt.unlink()
            update_index()
            aggregate()
            print(m["run_id"], "verified", flush=True)
        status["status"] = "complete"
        status["verified_runs"] = 10
        if prune_key:
            (build / "final.zkey").unlink()
            status["proving_key_retained"] = False
        else:
            status["proving_key_retained"] = True
    except Exception as error:
        timed = isinstance(error, subprocess.TimeoutExpired)
        log = config / f"{stage}.log"
        oom = log.exists() and "heap out of memory" in log.read_text(errors="replace")
        status.update(
            status=f"{stage}_timeout" if timed else (f"{stage}_heap_oom" if oom else f"{stage}_failed"),
            failed_stage=stage,
            error=str(error),
            setup_completed="setup_seconds" in status,
        )
        if stage == "setup":
            status["setup_seconds"] = None
            if (build / "initial.zkey").exists():
                status["invalid_partial_key_bytes_removed"] = (build / "initial.zkey").stat().st_size
                (build / "initial.zkey").unlink()
        for case in read(HERE / "plan.json")["runs"]:
            if case["config_id"] != f"sc{count}":
                continue
            p = HERE / case["manifest_path"]
            m = read(p)
            if not m["verified"]:
                m.update(status="not_completed", failure_status=status["status"], failure_reason=str(error))
                dump(p, m)
        dump(config / "status.json", status)
        update_index()
        aggregate()
        raise
    dump(config / "status.json", status)
    update_index()
    aggregate()


def aggregate():
    plan = read(HERE / "plan.json")
    rows = []
    summary = []
    for case in plan["runs"]:
        m = read(HERE / case["manifest_path"])
        rows.append(
            {k: m.get(k) for k in ["run_id", "subcarriers", "window_id", "repeat_id", "status", "verified"]}
            | m["timings"]
        )
    for count in COUNTS:
        ok = [r for r in rows if r["subcarriers"] == count and r["verified"]]
        reps = [r for r in ok if r["window_id"] == REP]
        first = [r for r in ok if r["repeat_id"] == 0]
        summary.append(
            {
                "subcarriers": count,
                "verified_runs": len(ok),
                "unique_raw_windows": len(first),
                "representative_window": REP,
                "representative_repeats": len(reps),
                "representative_prove_seconds_median": (
                    float(__import__("statistics").median(r["prove_seconds"] for r in reps)) if len(reps) == 3 else None
                ),
                "representative_verify_seconds_median": (
                    float(__import__("statistics").median(r["verify_seconds"] for r in reps))
                    if len(reps) == 3
                    else None
                ),
                "raw8_prove_seconds_mean": sum(r["prove_seconds"] for r in first) / 8 if len(first) == 8 else None,
                "status": read(HERE / "configs" / f"sc{count}" / "status.json")["status"],
            }
        )
    dump(HERE / "runs_summary.json", rows)
    dump(HERE / "config_summary.json", summary)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--counts", default="1,2,4")
    p.add_argument("--ptau", type=Path, default=BASE / ".cache/ppot_0080_21.ptau")
    p.add_argument("--setup-timeout", type=int, default=1800)
    p.add_argument("--heap-mib", type=int, default=8192)
    p.add_argument("--prune-key", action="store_true")
    a = p.parse_args()
    if a.prepare:
        prepare()
        aggregate()
    if a.execute:
        assert (HERE / "plan.json").exists(), "Run --prepare first"
        for count in map(int, a.counts.split(",")):
            run_config(count, a.ptau.resolve(), a.setup_timeout, a.heap_mib, a.prune_key)


if __name__ == "__main__":
    main()
