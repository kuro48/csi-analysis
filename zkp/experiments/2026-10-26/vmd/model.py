"""Parameterized integer arithmetic matching the production VMD approximation."""
import math
import numpy as np

N = 128
BINS = np.arange(1, 64)
INITIAL_CENTERS = [8, 24, 48, 16, 32, 56, 40, 4]
COS = np.array([[round(1000 * math.cos(2 * math.pi * j * t / N)) for t in range(N)] for j in BINS], dtype=np.int64)
SIN = np.array([[round(1000 * math.sin(2 * math.pi * j * t / N)) for t in range(N)] for j in BINS], dtype=np.int64)


def decompose(waveform, modes=3, iterations=4, initial_centers=None):
    x = np.asarray(waveform)
    if x.shape != (128,) or not np.all(x == np.round(x)) or np.max(np.abs(x)) > 100:
        raise ValueError('Expected 128 integers in [-100,100]')
    if not 1 <= modes <= 8 or iterations < 1:
        raise ValueError('modes must be 1..8; iterations must be positive')
    f = np.stack((COS @ x.astype(np.int64), SIN @ x.astype(np.int64)), axis=1)
    u = np.zeros((modes, 63, 2), dtype=np.int64)
    centers = np.array(INITIAL_CENTERS[:modes] if initial_centers is None else initial_centers, dtype=np.int64)
    if len(centers) != modes or np.any(centers < 1) or np.any(centers > 63):
        raise ValueError("One center per mode, each in bins 1..63")
    for _ in range(iterations):
        for k in range(modes):
            residual = f - (u.sum(axis=0) - u[k])
            denominator = (1 + (BINS - centers[k]) ** 2)[:, None]
            u[k] = np.sign(residual) * (np.abs(residual) // denominator)
            if np.max(np.abs(u[k])) > 2 ** 26:
                raise OverflowError("Mode coefficients exceed the int64-safe experiment bound")
            energy = (u[k] ** 2).sum(axis=1)
            # Python integers avoid overflow for weighted sums and high K/R.
            total = sum(int(e) for e in energy)
            if total:
                centers[k] = sum(int(j) * int(e) for j, e in zip(BINS, energy)) // total
    power = (u ** 2).sum(axis=2)
    selected, j = np.unravel_index(np.argmax(power), power.shape)
    peak = int(j + 1) if power.max() else 0
    # Diagnostic alternative only: Python production mode selection priority.
    peaks = np.argmax(power, axis=1)
    ratios = power[np.arange(modes), peaks] / np.maximum(power.sum(axis=1), 1)
    eligible = np.flatnonzero((peaks + 1 >= 7) & (peaks + 1 <= 23))
    choice = int(eligible[np.argmax(ratios[eligible])]) if len(eligible) else int(np.argmax(ratios))
    return dict(peak_bin=peak, bpm=peak * 120 / 128, selected_mode=int(selected),
                is_normal=7 <= peak <= 23, centers=centers.tolist(),
                band_priority_bpm=float((peaks[choice] + 1) * 120 / 128) if power.max() else 0.0, spectra=u.tolist())
