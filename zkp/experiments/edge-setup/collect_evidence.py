#!/usr/bin/env python3
"""Retrieve only non-CSI environment/validation metadata for the local report."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
target = ROOT / "2026-10-19/evidence"
target.mkdir(parents=True, exist_ok=True)
for filename in ("environment.json", "python-freeze.txt", "csi_inventory.json", "validation_summary.json"):
    source = f"infonetworking@100.111.253.60:/home/infonetworking/csi-zkp/results/{filename}"
    subprocess.run(["scp", "-o", "BatchMode=yes", source, str(target / filename)], check=True)
    print(f"Retrieved metadata: {filename} ({(target / filename).stat().st_size} bytes)", flush=True)
print("No raw CSI, private input JSON or witness files transferred.")
