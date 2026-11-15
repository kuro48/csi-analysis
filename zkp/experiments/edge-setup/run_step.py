#!/usr/bin/env python3
"""Execute one recorded deployment step; preserve commands, stdout and exit status."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent.parent
RUN = ROOT / "2026-10-19"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15",
       "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=yes", "infonetworking@100.111.253.60"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step")
    args = parser.parse_args()
    steps = json.loads((ROOT / "steps.json").read_text())
    step = next(item for item in steps if item["id"] == args.step)
    now = dt.datetime.now().astimezone()
    label = f"{step['id']}-{now.strftime('%Y%m%dT%H%M%S%f')}"
    records = RUN / "records"
    records.mkdir(parents=True, exist_ok=True)
    log_path = records / f"{label}.txt"
    record = dict(step, started_at=now.isoformat(), log=log_path.name, status="running")
    stdin = None
    if "script" in step:
        script = ROOT / step["script"]
        record["script_text"] = script.read_text()
        command = SSH + ["bash", "-se"] if step.get("remote", True) else ["bash", "-se"]
        stdin = script.open()
    else:
        command = step["command"]
    record["executed_argv"] = command
    metadata = records / f"{label}.json"
    metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    started = time.monotonic()
    exit_code = 1
    try:
        with log_path.open("w") as log:
            header = f"STEP {step['id']} | {step['title']}\nSTART {now.isoformat()}\n{step['purpose']}\n\n"
            print(header, end="", flush=True)
            log.write(header)
            log.flush()
            env = dict(os.environ, NO_COLOR="1", PYTHONUNBUFFERED="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
            with subprocess.Popen(command, cwd=REPO, stdin=stdin, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors="replace", env=env) as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)
                exit_code = process.wait()
            elapsed = time.monotonic() - started
            footer = f"\nEND exit_code={exit_code} elapsed_seconds={elapsed:.3f}\n"
            log.write(footer)
            print(footer, end="", flush=True)
    finally:
        if stdin:
            stdin.close()
        record.update(exit_code=exit_code, elapsed_seconds=round(time.monotonic() - started, 3),
                      ended_at=dt.datetime.now().astimezone().isoformat(),
                      status="passed" if exit_code == 0 else "failed")
        metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
