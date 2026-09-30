#!/usr/bin/env python3
"""Create a deterministic normal-breathing input without external packages."""

import json
import math
import sys
from pathlib import Path


SAMPLES = 64
SUBCARRIERS = 8
OFFSET = 2048


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_self_test_input.py OUTPUT.json")
    times = [index * 0.94 + 0.035 * math.sin(index * 0.73) for index in range(SAMPLES)]
    frequencies = [0.25, 0.4, 0.395, 0.4, 0.395, 0.4, 0.395, 0.4]
    csi_i = []
    csi_q = []
    for time in times:
        i_row = []
        q_row = []
        for sc, frequency in enumerate(frequencies):
            amplitude = 150 if sc == 0 else 80
            raw_i = round(900 + amplitude * math.sin(2 * math.pi * frequency * time + sc * 0.37))
            raw_q = round(40 * math.sin(2 * math.pi * frequency * time + sc * 0.21))
            i_row.append(raw_i + OFFSET)
            q_row.append(raw_q + OFFSET)
        csi_i.append(i_row)
        csi_q.append(q_row)
    payload = {
        "csiI": csi_i,
        "csiQ": csi_q,
        "commitmentNonce": "12345678901234567890",
        "timestampsMs": [round((time - times[0]) * 1000) for time in times],
    }
    Path(sys.argv[1]).write_text(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
