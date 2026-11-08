#!/usr/bin/env python3
"""Convert PicoScenes CSI or NPZ data into the private circuit input.

The conversion is deterministic except for the private commitment nonce.
All subcarriers are scored on at most 1024 representative observations. Only
8 original I/Q columns and 64 original timestamps enter the existing circuit.
Selection statistics and physical/array indices remain local metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from select_subcarriers import capture_rows, rank_subcarriers, select_capture


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


def load_picoscenes(path: Path, selection: str = "motion-quality") -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    parser = _new_parser()
    widths: Counter[int] = Counter()
    references = defaultdict(list)
    layout = {}
    ordinal = 0
    for offset, count in _frame_batches(path):
        parser.seek(str(path), offset, count)
        for frame in parser.raw:
            csi = frame.get("CSI")
            timestamp = _timestamp_ns(frame)
            if csi is not None and csi.get("CSI") is not None and timestamp is not None:
                width = np.asarray(csi["CSI"]).size
                widths[width] += 1
                references[width].append((ordinal, timestamp))
                if width not in layout:
                    layout[width] = {key: int(csi[key]) for key in ("numTones", "numRx", "numTx") if key in csi}
            ordinal += 1
        parser.raw.clear()
    if not widths:
        raise ValueError("no CSI/systemns frame pairs found")
    width, frame_count = widths.most_common(1)[0]
    if width < SUBCARRIERS:
        raise ValueError("capture needs at least 8 distinct CSI columns")
    refs = references[width]
    timestamps = np.asarray([entry[1] for entry in refs], dtype=np.int64)
    analysis, proof = capture_rows(timestamps)
    selected_rows = np.union1d(analysis, proof) if selection == "motion-quality" else proof
    wanted = {refs[int(row)][0]: index for index, row in enumerate(selected_rows)}
    # Keep at most 1024+64 full-width rows. The parser also holds only a 32-frame batch.
    selected = np.empty((len(selected_rows), width), dtype=np.complex128)
    seen = set()
    ordinal = 0
    for offset, count in _frame_batches(path):
        parser.seek(str(path), offset, count)
        for frame in parser.raw:
            if ordinal in wanted:
                values = np.asarray(frame["CSI"]["CSI"]).reshape(-1)
                if values.size != width or _timestamp_ns(frame) != timestamps[selected_rows[wanted[ordinal]]]:
                    raise ValueError("CSI source changed during preparation")
                selected[wanted[ordinal]] = values
                seen.add(ordinal)
            ordinal += 1
        parser.raw.clear()
    if len(seen) != len(wanted):
        raise ValueError("CSI source changed during preparation")
    positions = {int(row): index for index, row in enumerate(selected_rows)}
    proof_positions = [positions[int(row)] for row in proof]
    if selection == "motion-quality":
        analysis_positions = [positions[int(row)] for row in analysis]
        columns, details = rank_subcarriers(
            selected[analysis_positions], timestamps[analysis], selected[proof_positions]
        )
    elif selection == "uniform":
        columns = np.rint(np.linspace(0, width - 1, SUBCARRIERS)).astype(int).tolist()
        details = {"method": "uniform-v1", "proof_scope": "selection_not_proven"}
    else:
        raise ValueError("unsupported selection method")
    return (
        selected[np.ix_(proof_positions, columns)],
        timestamps[proof],
        {
            "source_format": "picoscenes",
            "modal_csi_width": int(width),
            "modal_frame_count": int(frame_count),
            "original_input_frames": int(frame_count),
            "buffered_full_width_frames": int(len(selected_rows)),
            "selected_subcarrier_indices": columns,
            "index_semantics": "flattened_CSI_array_column_not_RF_frequency",
            "csi_layout": layout[width],
            "selection": details,
        },
    )


def load_npz(path: Path, selection: str = "motion-quality") -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path) as data:
        if "csi" not in data:
            raise ValueError("NPZ must contain a 2-D complex array named 'csi'")
        csi = np.asarray(data["csi"])
        if csi.ndim != 2:
            raise ValueError("NPZ csi must have shape [samples, subcarriers]")
        if "timestamps_ns" in data:
            timestamps = np.asarray(data["timestamps_ns"])
        elif "timestamps_ms" in data:
            milliseconds = np.asarray(data["timestamps_ms"])
            if milliseconds.dtype.kind not in "iu" or milliseconds.ndim != 1:
                raise ValueError("timestamps_ms must be a one-dimensional integer array")
            bound = np.iinfo(np.int64).max // 1_000_000
            if np.any(milliseconds > bound) or (milliseconds.dtype.kind == "i" and np.any(milliseconds < -bound)):
                raise ValueError("timestamps_ms exceed signed 64-bit nanosecond range")
            timestamps = milliseconds.astype(np.int64) * 1_000_000
        else:
            raise ValueError("NPZ must contain timestamps_ns or timestamps_ms")
    if csi.shape[0] != timestamps.size:
        raise ValueError("CSI rows and timestamps must have the same length")
    selected, selected_times, metadata = select_capture(csi, timestamps, selection)
    return (
        selected,
        selected_times,
        {
            "source_format": "npz",
            "modal_csi_width": int(csi.shape[1]),
            "modal_frame_count": int(csi.shape[0]),
            "index_semantics": "CSI_array_column",
            **metadata,
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
    power = signed_i * signed_i + signed_q * signed_q
    if np.any(np.ptp(power, axis=0) == 0):
        raise ValueError(
            "selected channel power is constant after shared I/Q quantization; circuit requires dynamic channels"
        )
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
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--selection", choices=("motion-quality", "uniform"), default="motion-quality")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        raise SystemExit(f"input file not found: {source}")
    if source.suffix.lower() == ".csi":
        csi, timestamps, source_metadata = load_picoscenes(source, args.selection)
    elif source.suffix.lower() == ".npz":
        csi, timestamps, source_metadata = load_npz(source, args.selection)
    else:
        raise SystemExit("supported inputs are .csi and .npz")

    circuit_input, conversion_metadata = canonicalize(csi, timestamps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(circuit_input, separators=(",", ":")))
    os.chmod(args.output, 0o600)
    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(
            json.dumps({**source_metadata, **conversion_metadata}, ensure_ascii=False, indent=2) + "\n"
        )
        os.chmod(args.metadata, 0o600)


if __name__ == "__main__":
    main()
