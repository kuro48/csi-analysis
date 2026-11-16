"""Run memory-heavy experiment stages serially, with resumable stage receipts."""
import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / ".local/sample-count")
    parser.add_argument("--wait-compiler-pid", type=int)
    args = parser.parse_args()
    work = args.work.resolve()
    python = ROOT / ".venv/bin/python"
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")

    def state(n, stage, status):
        value = {
            "sampleCount": n,
            "stage": stage,
            "status": status,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        (work / "pipeline-state.json").write_text(json.dumps(value, indent=2) + "\n")
        print(json.dumps(value), flush=True)

    def run(n, stage, command, receipt):
        if receipt.exists():
            state(n, stage, "existing_receipt")
            return
        state(n, stage, "running")
        started = time.perf_counter()
        try:
            subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)
        except Exception:
            state(n, stage, "failed")
            raise
        if not receipt.exists():
            raise RuntimeError(f"Stage produced no receipt: {stage}")
        (work / f"n{n}" / f"{stage}-wall.json").write_text(
            json.dumps({"seconds": time.perf_counter() - started}) + "\n"
        )
        state(n, stage, "complete")

    if args.wait_compiler_pid:
        state(96, "compile", "waiting_for_existing_compiler")
        while True:
            try:
                os.kill(args.wait_compiler_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(10)
        if "Everything went okay" not in (work / "n96/compile.log").read_text():
            raise RuntimeError("The existing compiler did not complete successfully")

    for n in (96, 128, 64):
        target = work / f"n{n}"
        target.mkdir(parents=True, exist_ok=True)
        if n != 64:
            build = target / "build"
            build.mkdir(exist_ok=True)
            if not (build / f"n{n}_js/n{n}.wasm").exists():
                state(n, "compile", "running")
                with (target / "compile.log").open("w") as log:
                    subprocess.run(
                        [
                            "/usr/bin/time",
                            "-l",
                            "circom",
                            str(ROOT / f"zkp/experiments/sample-count/n{n}.circom"),
                            "--r1cs",
                            "--wasm",
                            "--O1",
                            "-l",
                            "zkp/circuits",
                            "-l",
                            "zkp/node_modules",
                            "-o",
                            str(build),
                        ],
                        cwd=ROOT,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                state(n, "compile", "complete")
        run(
            n,
            "evaluate",
            [python, "scripts/evaluate_sample_counts.py", "evaluate", "--work", work, "--samples", n],
            target / "evaluation.json",
        )
        if n != 64:
            run(
                n,
                "setup",
                [python, "scripts/evaluate_sample_counts.py", "setup", "--work", work, "--samples", n],
                target / "artifacts.json",
            )
        run(
            n,
            "prove",
            [python, "scripts/evaluate_sample_counts.py", "prove", "--work", work, "--samples", n],
            target / "csi_20260519_114943/prove-metrics.json",
        )
        run(
            n,
            "deploy",
            ["node", "scripts/sample_count_ledgers.mjs", "deploy", work, n],
            target / "fabric/deployed.json",
        )
        run(
            n,
            "measure",
            ["node", "scripts/sample_count_ledgers.mjs", "measure", work, n],
            target / "ledger-measurements.json",
        )
    state(None, "all", "complete")


if __name__ == "__main__":
    main()
