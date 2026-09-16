"""Deterministic integer reference for the input-only approximate VMD circuit."""

import math
from typing import Dict, List

N, FS, K, R, TRIG = 128, 2, 3, 4, 1000
BINS = 63  # bins 1..63; DC is intentionally omitted


def _div0(n: int, d: int) -> int:
    return (abs(n) // d) * (-1 if n < 0 else 1)


def vmd_approx(waveform: List[int]) -> Dict[str, object]:
    if len(waveform) != N or any(type(x) is not int or abs(x) > 100 for x in waveform):
        raise ValueError("waveform must contain 128 signed samples in [-100,100]")
    cs = [[round(TRIG * math.cos(2 * math.pi * (j + 1) * t / N)) for t in range(N)] for j in range(BINS)]
    sn = [[round(TRIG * math.sin(2 * math.pi * (j + 1) * t / N)) for t in range(N)] for j in range(BINS)]
    f = [
        (sum(x * cs[j][t] for t, x in enumerate(waveform)), sum(x * sn[j][t] for t, x in enumerate(waveform)))
        for j in range(BINS)
    ]
    u = [[(0, 0) for _ in range(BINS)] for _ in range(K)]
    centers = [8, 24, 48]
    for _ in range(R):
        old = [row[:] for row in u]
        for k in range(K):
            for j in range(BINS):
                rr = f[j][0] - sum((u[i][j][0] if i < k else old[i][j][0]) for i in range(K) if i != k)
                ii = f[j][1] - sum((u[i][j][1] if i < k else old[i][j][1]) for i in range(K) if i != k)
                d = 1 + (j + 1 - centers[k]) ** 2
                u[k][j] = (_div0(rr, d), _div0(ii, d))
            energy = [a * a + b * b for a, b in u[k]]
            total = sum(energy)
            centers[k] = _div0(sum((j + 1) * e for j, e in enumerate(energy)), total) if total else centers[k]
    totals = [sum(a * a + b * b for a, b in row) for row in u]
    peaks = [max(range(BINS), key=lambda j: u[k][j][0] ** 2 + u[k][j][1] ** 2) + 1 for k in range(K)]
    selected = (
        max(range(K), key=lambda k: u[k][peaks[k] - 1][0] ** 2 + u[k][peaks[k] - 1][1] ** 2) if any(totals) else 0
    )
    peak = peaks[selected] if any(totals) else 0
    return {
        "spectra": u,
        "centers": centers,
        "selected_mode": selected,
        "peak_bin": peak,
        "is_normal": bool(any(totals) and 7 <= peak <= 23),
        "bpm": peak * FS * 60 / N,
    }


if __name__ == "__main__":
    expected = {0.25: 16, 0.5: 32, 0.8: 51}
    for hz in (0.25, 0.5, 0.8):
        result = vmd_approx([round(80 * math.sin(2 * math.pi * hz * t / FS)) for t in range(N)])
        assert result["peak_bin"] == expected[hz], (hz, result["peak_bin"])
        print(hz, result["peak_bin"], result["bpm"], result["centers"])
