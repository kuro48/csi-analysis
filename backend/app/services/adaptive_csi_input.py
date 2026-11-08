"""Format ALL CSI columns for Circom. No subcarrier scoring or selection here."""
import hashlib
import secrets
from pathlib import Path

import numpy as np

FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def canonicalize_all_columns(matrix, timestamps_ns, capacity=4004):
    matrix = np.asarray(matrix)
    timestamps = np.asarray(timestamps_ns, dtype=np.int64)
    if matrix.ndim != 2 or timestamps.ndim != 1 or len(matrix) != len(timestamps) or len(matrix) == 0:
        raise ValueError("adaptive_invalid_shape")
    count = matrix.shape[1]
    if not 1 <= count <= capacity:
        raise ValueError("adaptive_candidate_capacity_exceeded")
    if not np.all(np.isfinite(matrix.real)) or not np.all(np.isfinite(matrix.imag)):
        raise ValueError("adaptive_nonfinite_csi")
    order = np.argsort(timestamps, kind="stable")
    ordered_ns = timestamps[order]
    # Subtract in integer arithmetic before converting to milliseconds.
    relative_ms = np.rint((ordered_ns - ordered_ns[0]).astype(np.float64) / 1_000_000).astype(np.int64)
    keep = np.concatenate(([True], np.diff(relative_ms) > 0))
    rows = order[keep]
    times = relative_ms[keep]
    if len(times) < 64:
        raise ValueError("adaptive_insufficient_timestamps")
    selected_times = np.rint(np.linspace(0, len(times) - 1, 64)).astype(np.int64)
    samples = matrix[rows[selected_times], :]  # All columns, unchanged order.
    times = times[selected_times]
    if times[-1] >= 2**24 or np.any(np.diff(times) <= 0):
        raise ValueError("adaptive_invalid_timestamps")
    peak = float(max(np.max(np.abs(samples.real)), np.max(np.abs(samples.imag))))
    if peak == 0:
        raise ValueError("adaptive_zero_capture")
    scale = 1800.0 / peak
    encoded_i = np.rint(samples.real * scale).astype(np.int64) + 2048
    encoded_q = np.rint(samples.imag * scale).astype(np.int64) + 2048
    if count < capacity:
        encoded_i = np.pad(encoded_i, ((0, 0), (0, capacity - count)), constant_values=2048)
        encoded_q = np.pad(encoded_q, ((0, 0), (0, capacity - count)), constant_values=2048)
    return {
        "csiI": encoded_i.tolist(),
        "csiQ": encoded_q.tolist(),
        "timestampsMs": times.tolist(),
        "candidateCount": count,
        "commitmentNonce": str(secrets.randbelow(FIELD - 1) + 1),
    }, {
        "inputFrames": len(matrix),
        "uniqueMillisecondFrames": int(len(rows)),
        "sampleCount": 64,
        "candidateCount": count,
        "capacity": capacity,
        "columnSelection": "all-columns-in-parser-order",
        "relativeDurationMs": int(times[-1]),
        "captureStartUnixNs": str(ordered_ns[0]),
        "sharedIqScale": scale,
        "sourceRows": rows[selected_times].tolist(),
    }


def prepare_capture(path, capacity=4004):
    from app.services.breathing_pipeline import load_csi_matrix_with_timestamps

    try:
        matrix, timestamps = load_csi_matrix_with_timestamps(str(path))
    except ValueError as exc:
        raise ValueError("adaptive_invalid_capture") from exc
    data, metadata = canonicalize_all_columns(matrix, timestamps, capacity)
    with Path(path).open("rb") as source:
        metadata["sourceSha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    return data, metadata
