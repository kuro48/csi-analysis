#!/usr/bin/env python3
"""Generate fresh full-pool proofs for paired Fabric/EVM comparisons."""
import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


async def run(args):
    os.environ["ADAPTIVE_ARTIFACT_MANIFEST"] = str(args.artifacts.resolve())
    from app.services.adaptive_observation import generate_adaptive_bundle

    manifest = json.loads(args.artifacts.read_text())
    key_bytes = Path(manifest["files"]["verificationKey"]).read_bytes()
    bank = {
        "inputKind": "csi-adaptive-full-pool",
        "proofGenerationScope": "artifact checks + witness + Groth16 prove + local verify; preprocessing separate",
        "verificationKeyHash": "0x" + hashlib.sha256(key_bytes).hexdigest(),
        "publicSignalCount": 70,
        "isNormalIndex": 1,
        "debugMode": args.debug,
        "sourceFile": args.source.name,
        "samples": [],
    }
    for index in range(args.count):
        bundle = await generate_adaptive_bundle({"raw_path": str(args.source.resolve())})
        bank["samples"].append({**bundle, "proofGenerationMs": bundle["metrics"]["totalProverMs"]})
        bank["preprocessingMs"] = bundle["metrics"]["preparationMs"]
        args.output.write_text(json.dumps(bank, indent=2) + "\n")
        print(f"Generated {index + 1}/{args.count} fresh full-pool proofs", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("count must be 1..100")
    if args.output.exists():
        parser.error("Choose a new output file; existing proofs may already be recorded")
    os.umask(0o077)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
