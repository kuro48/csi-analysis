#!/usr/bin/env python3
"""Inspect capture metadata on the edge; never export CSI values or witnesses."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path("/home/infonetworking/csi-zkp")
PACKAGE = ROOT / "packages/lomb_scargle_e2e"
spec = importlib.util.spec_from_file_location("edge_prepare", PACKAGE / "bin/prepare_input.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
paths = sorted(Path("/home/infonetworking/csi_data/main").glob("*.csi"))
paths.append(Path("/home/infonetworking/rx_2_260616_113124.csi"))
records = []
for path in paths:
    row = dict(file=path.name, path=str(path), bytes=path.stat().st_size)
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    row["sha256"] = h.hexdigest()
    try:
        csi, times, metadata = prepare.load_picoscenes(path)
        row.update(metadata)
        row["duration_seconds"] = float((times.max() - times.min()) / 1e9)
        row["selected_matrix_shape"] = list(csi.shape)
        # Describe dimensions from one decoded frame; do not print CSI samples.
        parser = prepare._new_parser()
        parser.seek(str(path), 0, 1)
        if parser.raw:
            block = parser.raw[0].get("CSI", {})
            row["first_frame_csi_shape"] = list(prepare.np.asarray(block.get("CSI")).shape)
            row["first_frame_metadata_fields"] = sorted(block.keys())
            for key in ("numTones", "numRx", "numTx", "numESS", "cbw", "deviceType"):
                if key in block:
                    value = prepare.np.asarray(block[key])
                    if value.size == 1:
                        row[key] = str(value.item())
        parser.raw.clear()
        prepared, _ = prepare.canonicalize(csi, times)
        row["circuit_shape"] = list(prepare.np.asarray(prepared["csiI"]).shape)
        row["canonicalization"] = "ok"
        del prepared, csi, times
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    records.append(row)
    print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)
(ROOT / "results/csi_inventory.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
if not any(row.get("canonicalization") == "ok" for row in records):
    raise SystemExit("No capture could be prepared for the existing circuit")
