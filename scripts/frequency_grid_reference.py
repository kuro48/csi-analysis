"""Frequency-grid experiment reference: fixed endpoints and physical 6--22/min band."""

from __future__ import annotations

import numpy as np


def grid_parameters(k):
    if k not in (32, 64, 128):
        raise ValueError("Unsupported circuit grid")
    return (2540, 127, 29) if k == 32 else (2540 * (k - 1), 127 * (k - 1), 899)


def frequencies(k):
    den, start, step = grid_parameters(k)
    return (start + step * np.arange(k)) / den


def band_bounds(k):
    den, start, step = grid_parameters(k)
    # Exact rational ceil/floor for 0.1 <= f <= 22/60 Hz.
    return ((den - 10 * start + 10 * step - 1) // (10 * step), (22 * den - 60 * start) // (60 * step))


def rounded(n: int, d: int) -> int:
    return (n + d // 2) // d


def sincos(t: int, multiplier: int, period: int) -> tuple[int, int]:
    quadrant, local = divmod(4 * ((t * multiplier) % period), period)
    angle = rounded(local * 15708, period)
    y = rounded(angle * angle, 10000)
    sh72 = 10000 - rounded(y * 10000, 720000)
    sh42 = 10000 - rounded(y * sh72, 420000)
    sh20 = 10000 - rounded(y * sh42, 200000)
    sh6 = 10000 - rounded(y * sh20, 60000)
    sine = rounded(rounded(angle * sh6, 10000), 10)
    ch56 = 10000 - rounded(y * 10000, 560000)
    ch30 = 10000 - rounded(y * ch56, 300000)
    ch12 = 10000 - rounded(y * ch30, 120000)
    cosine = rounded(10000 - rounded(y * ch12, 20000), 10)
    return ((cosine, sine), (-sine, cosine), (-cosine, -sine), (sine, -cosine))[quadrant]


def basis(timestamps_ms: list[int], k: int) -> tuple[np.ndarray, np.ndarray]:
    den, start, step = grid_parameters(k)
    c, s = np.zeros((k, len(timestamps_ms)), dtype=object), np.zeros((k, len(timestamps_ms)), dtype=object)
    for j, t in enumerate(timestamps_ms):
        dc, ds = sincos(int(t), step, den * 1000)
        for f in range(k):
            if f % 16 == 0:
                c[f, j], s[f, j] = sincos(int(t), start + step * f, den * 1000)
            else:
                c[f, j] = rounded(int(c[f - 1, j] * dc - s[f - 1, j] * ds), 1000)
                s[f, j] = rounded(int(s[f - 1, j] * dc + c[f - 1, j] * ds), 1000)
    return c, s


def estimate_integer(circuit_input: dict, k: int, trig=None) -> dict:
    c, s = basis(circuit_input["timestampsMs"], k) if trig is None else trig
    i = np.asarray(circuit_input["csiI"], dtype=object) - 2048
    q = np.asarray(circuit_input["csiQ"], dtype=object) - 2048
    mag = i * i + q * q
    y = len(i) * mag - mag.sum(axis=0)
    yy = (y * y).sum(axis=0)
    if any(v == 0 for v in yy):
        raise ValueError("zero signal norm: existing circuit rejects constant subcarrier")
    cc, ss, cs = (c * c).sum(axis=1), (s * s).sum(axis=1), (c * s).sum(axis=1)
    determinant = cc * ss - cs * cs
    cp, sp = c @ y, s @ y
    numerator = ss[:, None] * cp * cp - 2 * cs[:, None] * cp * sp + cc[:, None] * sp * sp
    denominator = determinant[:, None] * yy[None, :]

    def better(f, sc, old_f, old_sc):
        return numerator[f, sc] * denominator[old_f, old_sc] > numerator[old_f, old_sc] * denominator[f, sc]

    low, high = band_bounds(k)
    freq = frequencies(k)
    peaks, globals_ = [], []
    for sc in range(i.shape[1]):
        peak, global_ = low, 0
        for f in range(low + 1, high + 1):
            if better(f, sc, peak, sc):
                peak = f
        for f in range(1, k):
            if better(f, sc, global_, sc):
                global_ = f
        peaks.append(peak)
        globals_.append(global_)
    selected = 0
    for sc in range(1, i.shape[1]):
        if better(peaks[sc], sc, peaks[selected], selected):
            selected = sc
    return {
        "selectedSubcarrier": selected,
        "estimatedFrequencyBin": peaks[selected],
        "globalPeakFrequencyBin": globals_[selected],
        "isNormal": int(low <= globals_[selected] <= high),
        "bpm": float(freq[peaks[selected]] * 60),
        "global_bpm": float(freq[globals_[selected]] * 60),
    }


def estimate_float(csi: np.ndarray, times: np.ndarray, freq: np.ndarray) -> dict:
    """Same magnitude-squared estimator, exact sin/cos, caller-supplied grid."""
    y = np.abs(csi) ** 2
    y -= y.mean(axis=0)
    phase = 2 * np.pi * freq[:, None] * times[None, :]
    c, s = np.cos(phase), np.sin(phase)
    cc, ss, cs = (c * c).sum(axis=1), (s * s).sum(axis=1), (c * s).sum(axis=1)
    # Explicit reduction avoids spurious Accelerate BLAS floating exception flags.
    cp = np.einsum("fi,is->fs", c, y, optimize=False)
    sp = np.einsum("fi,is->fs", s, y, optimize=False)
    if not np.isfinite(cp).all() or not np.isfinite(sp).all():
        raise ValueError("non-finite Lomb–Scargle projection")
    denom = (cc * ss - cs * cs)[:, None] * (y * y).sum(axis=0)[None, :]
    score = np.divide(
        ss[:, None] * cp * cp - 2 * cs[:, None] * cp * sp + cc[:, None] * sp * sp,
        denom,
        out=np.zeros_like(cp),
        where=denom > 0,
    )
    band = np.flatnonzero((freq >= 0.1) & (freq <= 22 / 60))
    peaks = band[np.argmax(score[band], axis=0)]
    selected = int(np.argmax(score[peaks, np.arange(y.shape[1])]))
    peak = int(peaks[selected])
    global_ = int(np.argmax(score[:, selected]))
    return {
        "selectedSubcarrier": selected,
        "estimatedFrequencyBin": peak,
        "globalPeakFrequencyBin": global_,
        "isNormal": int(0.1 <= freq[global_] <= 22 / 60),
        "bpm": float(freq[peak] * 60),
        "global_bpm": float(freq[global_] * 60),
    }
