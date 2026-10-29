"""Integer-exact mirror of the E2E Circom estimator (no field wrap)."""

from __future__ import annotations
import numpy as np

FREQUENCIES = (127 + 29 * np.arange(32)) / 2540


def rounded(n: int, d: int) -> int:
    return (n + d // 2) // d


def sincos(t: int, multiplier: int) -> tuple[int, int]:
    period = 2540000
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


def basis(timestamps_ms: list[int]) -> tuple[np.ndarray, np.ndarray]:
    c, s = np.zeros((32, len(timestamps_ms)), dtype=object), np.zeros((32, len(timestamps_ms)), dtype=object)
    for j, t in enumerate(timestamps_ms):
        dc, ds = sincos(int(t), 29)
        for f in range(32):
            if f % 16 == 0:
                c[f, j], s[f, j] = sincos(int(t), 127 + 29 * f)
            else:
                c[f, j] = rounded(int(c[f - 1, j] * dc - s[f - 1, j] * ds), 1000)
                s[f, j] = rounded(int(s[f - 1, j] * dc + c[f - 1, j] * ds), 1000)
    return c, s


def estimate_integer(circuit_input: dict, trig=None) -> dict:
    c, s = basis(circuit_input["timestampsMs"]) if trig is None else trig
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

    peaks, globals_ = [], []
    for sc in range(i.shape[1]):
        peak, global_ = 5, 0
        for f in range(6, 28):
            if better(f, sc, peak, sc):
                peak = f
        for f in range(1, 32):
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
        "isNormal": int(5 <= globals_[selected] <= 27),
        "bpm": float(FREQUENCIES[peaks[selected]] * 60),
        "global_bpm": float(FREQUENCIES[globals_[selected]] * 60),
    }


def estimate_float(csi: np.ndarray, times: np.ndarray) -> dict:
    """Same 32 frequencies and magnitude-squared estimator, exact sin/cos."""
    y = np.abs(csi) ** 2
    y -= y.mean(axis=0)
    phase = 2 * np.pi * FREQUENCIES[:, None] * times[None, :]
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
    peaks = 5 + np.argmax(score[5:28], axis=0)
    selected = int(np.argmax(score[peaks, np.arange(y.shape[1])]))
    peak = int(peaks[selected])
    global_ = int(np.argmax(score[:, selected]))
    return {
        "selectedSubcarrier": selected,
        "estimatedFrequencyBin": peak,
        "globalPeakFrequencyBin": global_,
        "isNormal": int(5 <= global_ <= 27),
        "bpm": float(FREQUENCIES[peak] * 60),
        "global_bpm": float(FREQUENCIES[global_] * 60),
    }


def nested_indices(width: int, count: int = 32) -> np.ndarray:
    """Farthest-point prefix, deterministic, amplitude/GT-independent."""
    selected = [0]
    while len(selected) < min(count, width):
        distance = np.min(np.abs(np.arange(width)[:, None] - np.asarray(selected)[None, :]), axis=1)
        selected.append(int(np.argmax(distance)))
    return np.asarray(selected)


def prepare(csi: np.ndarray, timestamps_ns: np.ndarray, max_sc=32) -> tuple[dict, dict, np.ndarray, np.ndarray]:
    if not np.isfinite(csi).all():
        raise ValueError("CSI contains non-finite I/Q values")
    order = np.argsort(timestamps_ns, kind="stable")
    times = np.rint((timestamps_ns[order] - timestamps_ns[order][0]) / 1e6).astype(np.int64)
    keep = np.r_[True, np.diff(times) > 0]
    csi = csi[order][keep]
    times = times[keep]
    rows = np.rint(np.linspace(0, len(times) - 1, 64)).astype(int)
    if len(np.unique(rows)) < 64:
        raise ValueError("fewer than 64 unique millisecond samples")
    times = times[rows]
    times -= times[0]
    if times[-1] >= 2**24:
        raise ValueError("timestamp out of circuit range")
    indices = nested_indices(csi.shape[1], max_sc)
    sample = csi[rows][:, indices]
    max_abs = max(np.max(np.abs(sample.real)), np.max(np.abs(sample.imag)))
    if max_abs <= 0:
        raise ValueError("CSI is identically zero")
    scale = 1800 / max_abs
    si = np.rint(sample.real * scale).astype(np.int64)
    sq = np.rint(sample.imag * scale).astype(np.int64)
    # One shared scale for all SC sweep points, avoiding quantization confounding.
    payload = {
        "csiI": (si + 2048).tolist(),
        "csiQ": (sq + 2048).tolist(),
        "timestampsMs": times.tolist(),
        "commitmentNonce": "1",
    }
    meta = {
        "subcarrier_indices": indices.tolist(),
        "sample_rows_after_ms_dedup": rows.tolist(),
        "shared_iq_scale": float(scale),
        "duration_ms": int(times[-1]),
        "constant_subcarriers": np.where(np.ptp(si * si + sq * sq, axis=0) == 0)[0].tolist(),
    }
    return payload, meta, csi[rows], times / 1000
