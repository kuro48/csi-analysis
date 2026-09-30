#!/usr/bin/env python3
"""Convert PicoScenes CSI or NPZ data into the private circuit input.

The conversion is deterministic except for the private commitment nonce:
1. keep frames having the modal CSI width and a systemns timestamp;
2. select eight evenly spaced subcarriers;
3. sort by timestamp and deduplicate after millisecond quantization;
4. select 64 observations uniformly across the capture;
5. apply one shared I/Q scale and encode signed values with offset 2048.
"""

from __future__ import annotations

import argparse
import json
import secrets
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SAMPLES = 64
SUBCARRIERS = 8
CSI_OFFSET = 2048
SIGNED_MIN = -2048
SIGNED_MAX = 2047
TARGET_ABS = 1800.0
BN254_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
BATCH_FRAMES = 32


def _timestamp_ns(frame: dict[str, Any]) -> int | None:
    basic = frame.get("RxSBasic")
    if not isinstance(basic, dict) or "systemns" not in basic:
        return None
    value = np.asarray(basic["systemns"]).reshape(-1)
    if value.size == 0:
        return None
    try:
        return int(value[0])
    except (TypeError, ValueError, OverflowError):
        return None


def _frame_batches(path: Path, batch_size: int = BATCH_FRAMES) -> Iterable[tuple[int, int]]:
    size = path.stat().st_size
    position = 0
    batch_start = 0
    batch_count = 0
    with path.open("rb") as source:
        while position < size:
            source.seek(position)
            header = source.read(4)
            if len(header) != 4:
                raise ValueError(f"invalid PicoScenes frame header at byte {position}")
            frame_size = int.from_bytes(header, "little", signed=False) + 4
            if frame_size <= 4 or position + frame_size > size:
                raise ValueError(f"invalid PicoScenes frame size at byte {position}: {frame_size}")
            if batch_count == 0:
                batch_start = position
            batch_count += 1
            position += frame_size
            if batch_count == batch_size:
                yield batch_start, batch_count
                batch_count = 0
    if batch_count:
        yield batch_start, batch_count


def _new_parser():
    try:
        from picoscenes import Picoscenes
    except ImportError as exc:
        raise RuntimeError(
            "PicoScenes input requires the picoscenes package. "
            "Install the version pinned by backend/requirements.txt."
        ) from exc
    with tempfile.NamedTemporaryFile(suffix=".csi") as empty:
        return Picoscenes(empty.name, False)


def load_picoscenes(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    parser = _new_parser()
    widths: Counter[int] = Counter()
    for offset, count in _frame_batches(path):
        parser.seek(str(path), offset, count)
        for frame in parser.raw:
            csi = frame.get("CSI")
            if csi is None or csi.get("CSI") is None or _timestamp_ns(frame) is None:
                continue
            widths[np.asarray(csi["CSI"]).size] += 1
        parser.raw.clear()
    if not widths:
        raise ValueError("no CSI/systemns frame pairs found")

    width, frame_count = widths.most_common(1)[0]
    subcarrier_indices = np.rint(np.linspace(0, width - 1, SUBCARRIERS)).astype(np.int64)
    rows: list[np.ndarray] = []
    timestamps: list[int] = []
    for offset, count in _frame_batches(path):
        parser.seek(str(path), offset, count)
        for frame in parser.raw:
            csi = frame.get("CSI")
            timestamp = _timestamp_ns(frame)
            if csi is None or csi.get("CSI") is None or timestamp is None:
                continue
            values = np.asarray(csi["CSI"]).reshape(-1)
            if values.size == width:
                rows.append(values[subcarrier_indices].astype(np.complex128, copy=False))
                timestamps.append(timestamp)
        parser.raw.clear()

    return (
        np.asarray(rows, dtype=np.complex128),
        np.asarray(timestamps, dtype=np.int64),
        {
            "source_format": "picoscenes",
            "modal_csi_width": int(width),
            "modal_frame_count": int(frame_count),
            "selected_subcarrier_indices": subcarrier_indices.tolist(),
        },
    )


def load_npz(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path) as data:
        if "csi" not in data:
            raise ValueError("NPZ must contain a 2-D complex array named 'csi'")
        csi = np.asarray(data["csi"])
        if csi.ndim != 2:
            raise ValueError("NPZ csi must have shape [samples, subcarriers]")
        if "timestamps_ns" in data:
            timestamps = np.asarray(data["timestamps_ns"], dtype=np.int64)
        elif "timestamps_ms" in data:
            timestamps = np.asarray(data["timestamps_ms"], dtype=np.int64) * 1_000_000
        else:
            raise ValueError("NPZ must contain timestamps_ns or timestamps_ms")
    if csi.shape[0] != timestamps.size:
        raise ValueError("CSI rows and timestamps must have the same length")
    indices = np.rint(np.linspace(0, csi.shape[1] - 1, SUBCARRIERS)).astype(np.int64)
    return (
        csi[:, indices].astype(np.complex128),
        timestamps,
        {
            "source_format": "npz",
            "modal_csi_width": int(csi.shape[1]),
            "modal_frame_count": int(csi.shape[0]),
            "selected_subcarrier_indices": indices.tolist(),
        },
    )


def canonicalize(csi: np.ndarray, timestamps_ns: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    if csi.shape[0] != timestamps_ns.size or csi.shape[1] != SUBCARRIERS:
        raise ValueError("internal CSI/timestamp shape mismatch")
    if not np.all(np.isfinite(csi.real)) or not np.all(np.isfinite(csi.imag)):
        raise ValueError("CSI contains non-finite values")

    order = np.argsort(timestamps_ns, kind="stable")
    sorted_csi = csi[order]
    sorted_ns = timestamps_ns[order]
    relative_ms = np.rint((sorted_ns - sorted_ns[0]).astype(np.float64) / 1_000_000.0).astype(np.int64)
    keep = np.concatenate(([True], np.diff(relative_ms) > 0))
    unique_csi = sorted_csi[keep]
    unique_ms = relative_ms[keep]
    if unique_ms.size < SAMPLES:
        raise ValueError(f"capture needs at least {SAMPLES} unique millisecond timestamps")

    selected_rows = np.rint(np.linspace(0, unique_ms.size - 1, SAMPLES)).astype(np.int64)
    sampled_csi = unique_csi[selected_rows]
    sampled_ms = unique_ms[selected_rows]
    sampled_ms = sampled_ms - sampled_ms[0]
    if sampled_ms[-1] >= 2**24:
        raise ValueError("selected capture duration exceeds the 24-bit millisecond circuit range")
    if np.any(np.diff(sampled_ms) <= 0):
        raise ValueError("selected timestamps are not strictly increasing")

    max_abs_component = float(max(np.max(np.abs(sampled_csi.real)), np.max(np.abs(sampled_csi.imag))))
    if max_abs_component <= 0:
        raise ValueError("CSI is identically zero")
    scale = TARGET_ABS / max_abs_component
    signed_i = np.clip(np.rint(sampled_csi.real * scale), SIGNED_MIN, SIGNED_MAX).astype(np.int64)
    signed_q = np.clip(np.rint(sampled_csi.imag * scale), SIGNED_MIN, SIGNED_MAX).astype(np.int64)

    encoded_i = signed_i + CSI_OFFSET
    encoded_q = signed_q + CSI_OFFSET
    nonce = secrets.randbelow(BN254_FIELD - 1) + 1
    circuit_input = {
        "csiI": encoded_i.tolist(),
        "csiQ": encoded_q.tolist(),
        "commitmentNonce": str(nonce),
        "timestampsMs": sampled_ms.tolist(),
    }
    metadata = {
        "input_frames": int(csi.shape[0]),
        "unique_millisecond_frames": int(unique_ms.size),
        "selected_samples": SAMPLES,
        "selected_subcarriers": SUBCARRIERS,
        "relative_duration_ms": int(sampled_ms[-1]),
        "shared_iq_scale": scale,
        "max_abs_component_before_scale": max_abs_component,
        "encoded_min": int(min(encoded_i.min(), encoded_q.min())),
        "encoded_max": int(max(encoded_i.max(), encoded_q.max())),
    }
    return circuit_input, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        raise SystemExit(f"input file not found: {source}")
    if source.suffix.lower() == ".csi":
        csi, timestamps, source_metadata = load_picoscenes(source)
    elif source.suffix.lower() == ".npz":
        csi, timestamps, source_metadata = load_npz(source)
    else:
        raise SystemExit("supported inputs are .csi and .npz")

    circuit_input, conversion_metadata = canonicalize(csi, timestamps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(circuit_input, separators=(",", ":")))
    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(
            json.dumps({**source_metadata, **conversion_metadata}, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
