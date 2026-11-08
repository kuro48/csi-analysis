"""Deterministic, spectrum-free motion sensitivity ranking before the ZK circuit.

Scores are heuristics, not probabilities or evidence of human movement. Selection
is outside the proof boundary. Only NumPy is required on the edge device.
"""
from __future__ import annotations

from typing import Any
import numpy as np

VERSION = "motion-quality-v1"
MAX_ANALYSIS_ROWS = 1024
SHORTLIST_SIZE = 64
MAD_SCALE = 1.4826
MIN_RELATIVE_LEVEL = 0.01  # Amplitude relative to median nonzero channel level (-40 dB power).


def timestamp_rows(timestamps_ns: np.ndarray, sample_count: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Return original row indices and quantized relative times, matching circuit preparation."""
    raw = np.asarray(timestamps_ns)
    if raw.ndim != 1 or raw.size < sample_count or raw.dtype.kind not in "iu":
        raise ValueError(f"need at least {sample_count} integer timestamps")
    if raw.dtype.kind == "u" and raw.max() > np.iinfo(np.int64).max:
        raise ValueError("timestamps exceed signed 64-bit range")
    timestamps = raw.astype(np.int64, copy=False)
    order = np.argsort(timestamps, kind="stable")
    ordered = timestamps[order]
    span = int(ordered[-1]) - int(ordered[0])
    if span >= (2**24) * 1_000_000:
        raise ValueError("capture exceeds the 24-bit millisecond circuit range")
    relative_ms = np.rint((ordered - ordered[0]).astype(np.float64) / 1_000_000).astype(np.int64)
    keep = np.concatenate(([True], np.diff(relative_ms) > 0))
    unique = order[keep]
    if unique.size < sample_count:
        raise ValueError(f"capture needs at least {sample_count} unique millisecond timestamps")
    return unique, relative_ms[keep]


def capture_rows(timestamps_ns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unique, _ = timestamp_rows(timestamps_ns)
    proof = unique[np.rint(np.linspace(0, unique.size - 1, 64)).astype(np.int64)]
    # Fixed-seed stratification prevents regular subsampling from producing an
    # artificial periodic signal; all candidates use exactly the same rows.
    count = min(unique.size, MAX_ANALYSIS_ROWS)
    if count == unique.size:
        analysis = unique
    else:
        edges = np.linspace(0, unique.size, count + 1, dtype=np.int64)
        rng = np.random.default_rng(0)
        positions = rng.integers(edges[:-1], edges[1:])
        analysis = unique[positions]
    return analysis, proof


def _quantization_eligible(csi: np.ndarray) -> np.ndarray:
    """Exclude channels whose power becomes constant at the circuit's 12-bit scale."""
    finite = np.all(np.isfinite(csi.real) & np.isfinite(csi.imag), axis=0)
    maxima = np.max(np.maximum(np.abs(csi.real), np.abs(csi.imag)), axis=0)
    good = finite & (maxima > 0)
    # This is a per-channel preliminary check; the shared-scale check is performed
    # again on the actual selected set before returning circuit inputs.
    scale = np.divide(1800.0, maxima, out=np.zeros_like(maxima), where=good)
    i = np.rint(np.where(finite[None, :], csi.real, 0) * scale)
    q = np.rint(np.where(finite[None, :], csi.imag, 0) * scale)
    power = i * i + q * q
    return good & (np.ptp(power, axis=0) > 0)


def rank_subcarriers(
    csi: np.ndarray,
    timestamps_ns: np.ndarray,
    proof_csi: np.ndarray,
    count: int = 8,
) -> tuple[list[int], dict[str, Any]]:
    """Rank all supplied columns using robust amplitude changes and local residual noise.

    Complexity O(T*S + S*log(S) + T*64*K), with T<=1024 at the ingestion boundary. There
    is no all-subcarrier correlation matrix and no per-subcarrier Lomb scan.
    """
    values = np.asarray(csi, dtype=np.complex128)
    times = np.asarray(timestamps_ns)
    if values.ndim != 2 or values.shape[0] < 8 or values.shape[1] < count:
        raise ValueError(f"need at least 8 observations and {count} distinct subcarriers")
    if times.ndim != 1 or times.size != values.shape[0] or np.any(np.diff(times) <= 0):
        raise ValueError("analysis timestamps must be strictly increasing and aligned")
    if np.shape(proof_csi) != (64, values.shape[1]):
        raise ValueError("proof sample matrix must have shape [64, candidates]")
    finite = np.all(np.isfinite(values.real) & np.isfinite(values.imag), axis=0)
    amplitude = np.abs(np.where(finite[None, :], values, 0))
    level = np.median(amplitude, axis=0)
    nonzero_levels = level[finite & (level > 0)]
    if nonzero_levels.size == 0:
        raise ValueError("no finite, nonzero subcarriers")
    level_floor = float(np.median(nonzero_levels)) * MIN_RELATIVE_LEVEL
    usable = finite & (level >= level_floor) & (level > 0) & _quantization_eligible(np.asarray(proof_csi))
    normalized = np.divide(amplitude, level, out=np.zeros_like(amplitude), where=level > 0) - 1.0
    median = np.median(normalized, axis=0)
    centered = normalized - median
    mad = MAD_SCALE * np.median(np.abs(centered), axis=0)
    clip = np.maximum(6.0 * mad, 1e-12)
    outliers = np.mean(np.abs(centered) > clip, axis=0)
    clipped = np.clip(centered, -clip, clip)

    # Linear drift is not enough to claim a dynamic response. Actual I/Q sent to
    # the circuit is NOT detrended, clipped, interpolated, or otherwise modified.
    seconds = (times - times[0]).astype(np.float64) / 1e9
    x = seconds - seconds.mean()
    detrended = clipped - clipped.mean(axis=0)
    detrended -= x[:, None] * ((x @ detrended) / float(x @ x))[None, :]
    variance = np.mean(detrended**2, axis=0)

    # Linear prediction at the actual irregular timestamps. For independent
    # white noise the residual variance is sigma^2*(1+w^2+(1-w)^2).
    w = (seconds[1:-1] - seconds[:-2]) / (seconds[2:] - seconds[:-2])
    residual = detrended[1:-1] - ((1 - w[:, None]) * detrended[:-2] + w[:, None] * detrended[2:])
    residual /= np.sqrt(1 + w**2 + (1 - w) ** 2)[:, None]
    residual -= np.median(residual, axis=0)
    noise = (MAD_SCALE * np.median(np.abs(residual), axis=0)) ** 2
    signal = np.maximum(variance - noise, 0)
    quality = np.divide(signal, variance, out=np.zeros_like(signal), where=variance > 1e-18)
    score = signal * quality * (1 - outliers) ** 2
    usable &= (variance > 1e-16) & np.isfinite(score)
    score = np.where(usable, score, 0)
    valid = np.flatnonzero(usable)
    if valid.size < count:
        raise ValueError(f"only {valid.size} usable dynamic subcarriers; need {count}")
    # Primary score, then variance, then original array index. No frequency/BPM
    # band appears in the ranking; abnormal motion is not discarded for being abnormal.
    ranking = sorted(valid.tolist(), key=lambda j: (-float(score[j]), -float(variance[j]), j))
    shortlist = ranking[: max(count, SHORTLIST_SIZE)]
    signals = detrended[:, shortlist]
    norms = np.linalg.norm(signals, axis=0)
    unit = np.divide(signals, norms, out=np.zeros_like(signals), where=norms > 0)
    max_corr = np.zeros(len(shortlist))
    remaining = np.ones(len(shortlist), dtype=bool)
    selected: list[int] = []
    utilities: list[float] = []
    for _ in range(count):
        utility = np.asarray([score[j] for j in shortlist]) * (1 - 0.25 * max_corr**2)
        choices = np.flatnonzero(remaining)
        # Stable argmax preserves ranking order for exact ties / zero-score fallback.
        best = int(choices[np.argmax(utility[choices])])
        selected.append(shortlist[best])
        utilities.append(float(utility[best]))
        remaining[best] = False
        max_corr = np.maximum(max_corr, np.clip(np.abs(unit.T @ unit[:, best]), 0, 1))
    metadata = {
        "method": VERSION,
        "proof_scope": "selection_not_proven",
        "candidate_count": int(values.shape[1]),
        "analysis_rows": int(values.shape[0]),
        "usable_count": int(valid.size),
        "low_quality_fallback": bool(any(score[j] <= 0 for j in selected)),
        "score_formula": "max(var-noise,0)^2/var * (1-outlier_fraction)^2",
        "diversity_weight": 0.25,
        "selected": [
            {
                "index": int(j),
                "score": float(score[j]),
                "utility": utility,
                "relative_variance": float(variance[j]),
                "noise_variance": float(noise[j]),
                "outlier_fraction": float(outliers[j]),
            }
            for j, utility in zip(selected, utilities)
        ],
    }
    return selected, metadata


def select_capture(csi: np.ndarray, timestamps_ns: np.ndarray, method: str = "motion-quality"):
    values = np.asarray(csi)
    if values.ndim != 2 or values.shape[0] != np.size(timestamps_ns) or values.shape[1] < 8:
        raise ValueError("CSI must have aligned timestamps and at least 8 distinct columns")
    analysis, proof = capture_rows(timestamps_ns)
    if method == "uniform":
        selected = np.rint(np.linspace(0, values.shape[1] - 1, 8)).astype(int).tolist()
        details = {"method": "uniform-v1", "proof_scope": "selection_not_proven"}
    elif method == "motion-quality":
        selected, details = rank_subcarriers(values[analysis], np.asarray(timestamps_ns)[analysis], values[proof])
    else:
        raise ValueError("unsupported selection method")
    return (
        values[np.ix_(proof, selected)].astype(np.complex128),
        np.asarray(timestamps_ns)[proof],
        {
            "selected_subcarrier_indices": selected,
            "selection": details,
            "original_input_frames": int(values.shape[0]),
            "selection_analysis_limit": MAX_ANALYSIS_ROWS,
        },
    )
