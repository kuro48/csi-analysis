#!/usr/bin/env python3
"""Reverify saved proofs and reject a changed public verdict; preserve original data."""

import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

ROOT = Path("/home/infonetworking/csi-zkp")
PACKAGE = ROOT / "packages/lomb_scargle_e2e"
CLI = PACKAGE / "vendor/runtime/node_modules/snarkjs/build/cli.cjs"
VK = PACKAGE / "artifacts/verification_key.json"
RESULTS = ROOT / "results"
rows = []
for name in ("real_20261005_115619.json", "real_20261005_115523.json", "real_20260907_185130.json"):
    path = RESULTS / name
    data = json.loads(path.read_text())
    signals = data["publicSignals"]
    result = data["result"]
    assert len(signals) == 69
    assert result["csiCommitment"] == str(signals[0])
    assert int(result["isNormal"]) == int(signals[1])
    assert result["selectedSubcarrier"] == int(signals[2])
    assert result["estimatedFrequencyBin"] == int(signals[3])
    assert result["globalPeakFrequencyBin"] == int(signals[4])
    assert result["timestampsMs"] == [int(x) for x in signals[5:]]
    assert math.isclose(result["estimatedBpm"], 60 * (127 + 29 * int(signals[3])) / 2540)
    assert math.isclose(result["globalPeakBpm"], 60 * (127 + 29 * int(signals[4])) / 2540)
    forbidden = {"csiI", "csiQ", "commitmentNonce", "witness", "inputScale", "scale"}

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert not forbidden.intersection(keys(data))
    verified = subprocess.run([str(PACKAGE / "bin/verify.sh"), str(path)], capture_output=True, text=True)
    print(f"REVERIFY {name}: exit={verified.returncode}")
    print(verified.stdout, end="")
    assert verified.returncode == 0 and "OK!" in verified.stdout
    rows.append(dict(file=name, proof_verified=True, public_signals=len(signals),
                     isNormal=result["isNormal"], estimatedBpm=result["estimatedBpm"],
                     globalPeakBpm=result["globalPeakBpm"], bytes=path.stat().st_size,
                     sha256=hashlib.sha256(path.read_bytes()).hexdigest(), private_input_keys_absent=True))

original = json.loads((RESULTS / "real_20261005_115619.json").read_text())
changed = list(original["publicSignals"])
changed[1] = str(1 - int(changed[1]))
with tempfile.TemporaryDirectory(prefix="csi-zkp-negative-") as temporary:
    directory = Path(temporary)
    (directory / "proof.json").write_text(json.dumps(original["proof"]))
    (directory / "public.json").write_text(json.dumps(changed))
    rejected = subprocess.run(["node", str(CLI), "groth16", "verify", str(VK),
                               str(directory / "public.json"), str(directory / "proof.json")],
                              capture_output=True, text=True)
    print(f"TAMPERED VERDICT: exit={rejected.returncode}")
    print(rejected.stdout + rejected.stderr, end="")
    assert rejected.returncode != 0 and "Invalid proof" in rejected.stdout + rejected.stderr

inventory = json.loads((RESULTS / "csi_inventory.json").read_text())
for capture in inventory:
    path = Path(capture["path"])
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    assert h.hexdigest() == capture["sha256"], f"Source changed: {path}"
    print(f"SOURCE UNCHANGED: {path.name}")
summary = dict(real_proofs=rows, changed_verdict_rejected=True, sources_unchanged=True,
               accuracy_evaluated=False,
               limitation="Existing 64x8 circuit: BPM, subcarrier index, commitment and timestamps remain public.")
(RESULTS / "validation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
