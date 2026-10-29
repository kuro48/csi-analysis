"""Preserve small independently verifiable proof records; optionally prune own large files."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    records = []
    for directory in sorted((HERE / "build").glob("sc*"), key=lambda p: int(p.name[2:])):
        metrics = directory / "proof_metrics.json"
        if not metrics.exists():
            continue
        if json.loads(metrics.read_text())["proof_status"] != "verified":
            continue
        output = HERE / "evidence" / directory.name
        output.mkdir(parents=True, exist_ok=True)
        patterns = [
            "proof[0-9].json",
            "public[0-9].json",
            "verification_key.json",
            "proof_metrics.json",
            "compile.json",
            "*.log",
        ]
        for pattern in patterns:
            for path in directory.glob(pattern):
                destination = output / path.name
                shutil.copy2(path, destination)
                records.append(
                    {
                        "path": str(destination.relative_to(HERE)),
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    }
                )
    if args.prune:
        if any(not (HERE / "evidence" / f"sc{n}" / "proof_metrics.json").exists() for n in [1, 2, 4, 8, 16, 32]):
            raise RuntimeError("Refusing to prune before all six sizes have verified evidence")
        for directory in (HERE / "build").glob("sc*"):
            for pattern in ["*.zkey", "*.r1cs", "*.sym", "*.wtns"]:
                for path in directory.glob(pattern):
                    path.unlink()
    (HERE / "evidence_manifest.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
