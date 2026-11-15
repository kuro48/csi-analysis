#!/usr/bin/env python3
"""Validate and bundle the report; optionally deliver it to the research edge PC."""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "2026-10-19"
HOST = "infonetworking@100.111.253.60"
REMOTE = "/home/infonetworking/csi-zkp/reports"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deliver", action="store_true")
    args = parser.parse_args()
    steps = json.loads((ROOT / "steps.json").read_text())
    records = [json.loads(p.read_text()) for p in sorted((RUN / "records").glob("*.json"))]
    latest = {record["id"]: record for record in records}
    for step in steps:
        expected = "failed" if step["id"] in {"13", "27"} else "passed"
        assert latest[step["id"]]["status"] == expected, step["id"]
    validation = json.loads((RUN / "browser-validation.json").read_text())
    assert validation["passed"] and validation["step_count"] == len(steps)
    assert len(list((RUN / "screenshots").glob("step-*.png"))) == len(steps)
    assert (RUN / "report.pdf").read_bytes().startswith(b"%PDF-")
    assert len(json.loads((RUN / "performance.json").read_text())) == 4

    files = {}
    for folder in ("records", "evidence", "screenshots"):
        for item in sorted((RUN / folder).rglob("*")):
            if item.is_file():
                files[item.relative_to(RUN).as_posix()] = item
    for name in ("report.html", "report.pdf", "findings.json", "performance.json", "browser-validation.json"):
        files[name] = RUN / name
    for item in sorted(ROOT.iterdir()):
        if item.is_file() and item.suffix in {".py", ".sh", ".cjs", ".json"}:
            files["reproduce/" + item.name] = item
    for item in sorted((ROOT / "scripts").glob("*.sh")):
        files["reproduce/scripts/" + item.name] = item
    manifest = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    (RUN / "report-manifest.json").write_text(json.dumps(manifest, indent=2))
    archive = RUN / "report-bundle.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, path in files.items():
            bundle.write(path, name)
        bundle.write(RUN / "report-manifest.json", "report-manifest.json")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = {"created_at": dt.datetime.now().astimezone().isoformat(), "step_count": len(steps),
              "resolved_failures": ["13: old README manifest", "27: browser extraction stopped"],
              "archive": archive.name, "bytes": archive.stat().st_size, "sha256": digest,
              "contains_raw_csi": False, "commands": []}
    (RUN / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if not args.deliver:
        return
    remote_archive = REMOTE + "/environment-20261019.zip"
    destination = REMOTE + "/2026-10-19"
    commands = [
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", HOST,
         f"test ! -e {remote_archive} && test ! -e {destination}"],
        ["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", str(archive), f"{HOST}:{remote_archive}"],
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", HOST,
         f"set -eu; umask 077; echo '{digest}  {remote_archive}' | sha256sum --check -; "
         f"mkdir {destination}; /usr/bin/python3 -m zipfile -e {remote_archive} {destination}; "
         f"test -s {destination}/report.html; test -s {destination}/report.pdf; "
         f"printf 'Report delivered: %s\\n' {destination}"],
    ]
    for command in commands:
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        result["commands"].append({"argv": command, "exit_code": completed.returncode, "output": completed.stdout})
        (RUN / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(shlex.join(command), completed.stdout, sep="\n", flush=True)
        completed.check_returncode()
    result["remote_report"] = destination + "/report.html"
    result["delivered"] = True
    (RUN / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
