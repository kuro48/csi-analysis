#!/usr/bin/env python3
"""Generate paired benchmark fixtures from existing CSI; private input never leaves this process.
Run from repo root: .venv/bin/python fabric/benchmark/csi-fixtures.py file.csi output.json --debug --count 6
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.breathing_pipeline import (
    load_csi_matrix_with_timestamps,
    run_breathing_pipeline,
    run_breathing_pipeline_from_matrix,
)
from app.services.observation_worker import validate_capture_timing


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csi", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument(
        "--vkey",
        type=Path,
        default=ROOT / "backend/contracts/build/onchain/csi_breathing_certificate.vkey.json",
    )
    args = parser.parse_args()
    if not 2 <= args.count <= 100:
        parser.error("count must be 2..100")
    start = time.perf_counter()
    if args.debug:
        analysis = run_breathing_pipeline(str(args.csi))
    else:
        matrix, timestamps = load_csi_matrix_with_timestamps(str(args.csi))
        validate_capture_timing(matrix, timestamps)
        analysis = run_breathing_pipeline_from_matrix(matrix[:6000])
    preprocessing_ms = (time.perf_counter() - start) * 1000
    cert = analysis["certificate_input"]
    service = BreathingCertificateService(auto_compile=False)
    if json.loads(args.vkey.read_text()) != json.loads(
        (service.keys_dir / "csi_breathing_certificate_verification_key.json").read_text()
    ):
        raise ValueError("Verification key mismatch")
    samples = []
    for i in range(args.count):
        start = time.perf_counter()
        result = await service.generate_proof(vmd_input=cert["vmdInput"], modes=cert["modes"], sel=cert["sel"])
        samples.append(
            {
                "proof": result["proof"],
                "publicSignals": result["publicSignals"],
                "proofGenerationMs": (time.perf_counter() - start) * 1000,
            }
        )
        print(f"Generated CSI proof {i + 1}/{args.count}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "version": 1,
                "proofGenerationScope": "existing Python service including witness, prove, local verification and subprocess overhead",
                "inputKind": "captured-csi-debug" if args.debug else "captured-csi",
                "debugMode": args.debug,
                "preprocessingMs": preprocessing_ms,
                "verificationKeyHash": "0x" + hashlib.sha256(args.vkey.read_bytes()).hexdigest(),
                "samples": samples,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
