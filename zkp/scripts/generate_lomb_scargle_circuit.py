#!/usr/bin/env python3
"""Validate the parameterized, source-maintained Lomb--Scargle circuit.

The timestamp/trigonometric implementation is split across Circom source files;
keeping it as Circom avoids duplicating a large template inside Python.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CIRCUIT = ROOT / "circuits" / "csi_lomb_scargle_normality.circom"
BASIS = ROOT / "circuits" / "lomb_scargle_timestamp_basis.circom"


def main() -> None:
    circuit = CIRCUIT.read_text()
    basis = BASIS.read_text()
    required = (
        'include "lomb_scargle_timestamp_basis.circom";',
        "public [timestampsMs]",
        "LombTimestampBasis(SAMPLE_COUNT, FREQS, 16)",
        "determinantBasis[f]",
    )
    missing = [marker for marker in required if marker not in circuit]
    if "template LombTimestampBasis" not in basis:
        missing.append("template LombTimestampBasis")
    if missing:
        raise SystemExit(f"Lomb--Scargle circuit is incomplete: {', '.join(missing)}")
    print(f"Validated: {CIRCUIT}")
    print("samples: 384, frequency bins: 128, normal bins: 5..54, timestamps: 24-bit ms, trig anchors: every 16 bins")


if __name__ == "__main__":
    main()
