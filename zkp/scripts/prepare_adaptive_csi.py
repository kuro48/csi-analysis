#!/usr/bin/env python3
"""PicoScenes -> full-pool Circom input. Selection is exclusively in Circom."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.adaptive_csi_input import prepare_capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--capacity", type=int, default=4004)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    if not 1 <= args.capacity <= 4096:
        parser.error("capacity must be 1..4096")
    os.umask(0o077)
    data, metadata = prepare_capture(args.source, args.capacity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(",", ":")))
    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({k: metadata[k] for k in ["inputFrames", "candidateCount", "capacity", "relativeDurationMs"]}))


if __name__ == "__main__":
    main()
