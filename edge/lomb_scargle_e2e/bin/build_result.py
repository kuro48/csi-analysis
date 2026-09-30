#!/usr/bin/env python3
"""Build the upload-safe result JSON from proof and public signals."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def bpm(bin_index: int) -> float:
    return 60.0 * (127 + 29 * bin_index) / 2540.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    proof = json.loads(args.proof.read_text())
    signals = json.loads(args.public.read_text())
    if len(signals) != 69:
        raise SystemExit(f"expected 69 public signals, got {len(signals)}")
    commitment = str(signals[0])
    is_normal = bool(int(signals[1]))
    selected_subcarrier = int(signals[2])
    estimated_bin = int(signals[3])
    global_bin = int(signals[4])
    timestamps_ms = [int(value) for value in signals[5:]]

    result = {
        "schema": "csi-lomb-scargle-e2e-proof/v1",
        "circuit": "csi_lomb_scargle_end_to_end",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "proof": proof,
        "publicSignals": signals,
        "result": {
            "csiCommitment": commitment,
            "isNormal": is_normal,
            "selectedSubcarrier": selected_subcarrier,
            "estimatedFrequencyBin": estimated_bin,
            "estimatedFrequencyHz": (127 + 29 * estimated_bin) / 2540.0,
            "estimatedBpm": bpm(estimated_bin),
            "globalPeakFrequencyBin": global_bin,
            "globalPeakFrequencyHz": (127 + 29 * global_bin) / 2540.0,
            "globalPeakBpm": bpm(global_bin),
            "timestampsMs": timestamps_ms,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
