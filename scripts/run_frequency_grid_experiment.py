"""Serialize compilation, proving and local-ledger measurements; resume from receipts."""
import argparse
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from evaluate_frequency_grid import COUNTS, ROOT, pin, read, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / ".local/frequency-grid")
    parser.add_argument("--wait-compiler-pid", type=int)
    args = parser.parse_args()
    work = args.work.resolve()
    pin(work)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")

    def state(n, k, stage, status):
        value = dict(
            sampleCount=n,
            frequencyGridCount=k,
            stage=stage,
            status=status,
            updatedAt=datetime.now(timezone.utc).isoformat(),
        )
        save(work / "pipeline-state.json", value)
        print(value, flush=True)

    def run(n, k, stage, command, receipt, log_path=None):
        if receipt.exists():
            state(n, k, stage, "existing_receipt")
            return
        pin(work)
        state(n, k, stage, "running")
        started = time.perf_counter()
        try:
            if log_path:
                with log_path.open("w") as log:
                    subprocess.run(
                        list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True
                    )
            else:
                subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)
            if not receipt.exists():
                raise RuntimeError(f"No receipt for {stage}")
        except Exception:
            state(n, k, stage, "failed")
            raise
        save(work / f"n{n}k{k}" / f"{stage}-wall.json", {"seconds": time.perf_counter() - started})
        state(n, k, stage, "complete")

    if args.wait_compiler_pid:
        state(64, 64, "compile", "waiting_for_existing_compiler")
        while True:
            try:
                os.kill(args.wait_compiler_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(10)
        if "Everything went okay" not in (work / "n64k64/compile.log").read_text():
            raise RuntimeError("Initial compiler failed")

    for n in COUNTS:
        target = work / f"n{n}k32"
        target.mkdir(exist_ok=True)
        run(
            n,
            32,
            "evaluate",
            [
                ROOT / ".venv/bin/python",
                "scripts/evaluate_frequency_grid.py",
                "evaluate",
                "--work",
                work,
                "--samples",
                n,
                "--grid",
                32,
            ],
            target / "evaluation.json",
        )
    for n in COUNTS:
        for k in (64, 128):
            target = work / f"n{n}k{k}"
            build = target / "build"
            build.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(work).free < 18 * 1024**3:
                raise RuntimeError("Need at least 18 GiB free for the next profile; preserve earlier evidence")
            run(
                n,
                k,
                "compile",
                [
                    "/usr/bin/time",
                    "-l",
                    "circom",
                    ROOT / f"zkp/experiments/frequency-grid/n{n}k{k}.circom",
                    "--r1cs",
                    "--wasm",
                    "--O1",
                    "-l",
                    "zkp/circuits",
                    "-l",
                    "zkp/node_modules",
                    "-o",
                    build,
                ],
                build / f"n{n}k{k}_js/n{n}k{k}.wasm",
                target / "compile.log",
            )
            if "Everything went okay" not in (target / "compile.log").read_text():
                raise RuntimeError("Incomplete compiler log")
            for stage, receipt in [
                ("evaluate", target / "evaluation.json"),
                ("setup", target / "artifacts.json"),
                ("prove", target / "csi_20260519_114943/prove-metrics.json"),
            ]:
                run(
                    n,
                    k,
                    stage,
                    [
                        ROOT / ".venv/bin/python",
                        "scripts/evaluate_frequency_grid.py",
                        stage,
                        "--work",
                        work,
                        "--samples",
                        n,
                        "--grid",
                        k,
                    ],
                    receipt,
                )
            for stage, receipt in [
                ("deploy", target / "fabric/deployed.json"),
                ("measure", target / "ledger-measurements.json"),
            ]:
                run(n, k, stage, ["node", "scripts/sample_count_ledgers.mjs", stage, work, n, k], receipt)
    state(None, None, "all", "complete")


if __name__ == "__main__":
    main()
