"""Regression checks using only existing real CSI experiment artifacts."""
from pathlib import Path

import numpy as np
import pytest
from evaluate_frequency_grid import COUNTS, GRIDS, ROOT, read, selected_input
from evaluate_sample_counts import lomb
from frequency_grid_reference import (
    band_bounds,
    basis,
    estimate_integer,
    frequencies,
    grid_parameters,
)

WORK = ROOT / ".local/frequency-grid"
PREVIOUS = ROOT / ".local/sample-count"


def test_grid_endpoints_and_physical_band():
    for k in GRIDS:
        f = frequencies(k)
        assert len(f) == k
        assert f[0] == 127 / 2540 and f[-1] == 1026 / 2540
        low, high = band_bounds(k)
        assert np.array_equal(np.flatnonzero((f >= 0.1) & (f <= 22 / 60)), np.arange(low, high + 1))
        den, start, step = grid_parameters(k)
        assert (2**24 - 1) * (start + (k - 1) * step) // (1000 * den) < 2**16
        assert 1000 * den < 2 ** ({32: 22, 64: 28, 128: 29}[k])


def test_integer_mirror_preserves_previous_real_32_bin_results():
    if not (PREVIOUS / "datasets.json").exists():
        pytest.skip("Requires private real CSI preparation")
    for dataset in read(PREVIOUS / "datasets.json")["datasets"]:
        if "excluded" in dataset:
            continue
        for n in COUNTS:
            data = read(PREVIOUS / "inputs" / f"{dataset['name']}-n{n}.json")
            reference = dataset["variants"][str(n)]["integerPython"]
            selected = selected_input(data, reference["selectedSubcarrier"])
            actual = estimate_integer(selected, 32)
            actual["selectedSubcarrier"] = reference["selectedSubcarrier"]
            assert actual == reference
            old_c, old_s = lomb.basis(data["timestampsMs"])
            c, s = basis(data["timestampsMs"], 32)
            assert np.array_equal(c, old_c) and np.array_equal(s, old_s)


def test_all_real_circuit_outputs_and_fixed_grid_selection():
    paths = [WORK / f"n{n}k{k}" / "evaluation.json" for n in COUNTS for k in GRIDS]
    if not all(path.exists() for path in paths):
        pytest.skip("All nine actual circuit executions required")
    for n in COUNTS:
        outputs = [read(WORK / f"n{n}k{k}" / "evaluation.json")["results"] for k in GRIDS]
        assert all(len(rows) == 5 for rows in outputs)
        for baseline in outputs[0]:
            for rows in outputs:
                row = next(r for r in rows if r["name"] == baseline["name"])
                assert row["integerReferenceMatches"]
                assert row["circuit"]["selectedSubcarrier"] == baseline["circuit"]["selectedSubcarrier"]
                public = read(WORK / f"n{n}k{row['frequencyGridCount']}" / row["name"] / "public.json")["publicSignals"]
                original = read(PREVIOUS / f"n{n}" / row["name"] / "public.json")["publicSignals"]
                assert public[0] == original[0]  # Commitment binds the identical full candidate pool.
                assert public[5:] == original[5:]


def test_real_timestamp_basis_and_cross_products_fit_circuit_bounds():
    if not (WORK / "datasets.json").exists():
        pytest.skip("Requires private real CSI preparation")
    for dataset in read(WORK / "datasets.json")["datasets"]:
        if "excluded" in dataset:
            continue
        for n in COUNTS:
            data = read(WORK / "inputs" / f"{dataset['name']}-n{n}.json")
            column = dataset["variants"][f"n{n}k32"]["integerPython"]["selectedSubcarrier"]
            z = selected_input(data, column)
            i = np.asarray(z["csiI"], dtype=object) - 2048
            q = np.asarray(z["csiQ"], dtype=object) - 2048
            power = i * i + q * q
            y = n * power - power.sum(axis=0)
            yy = (y * y).sum(axis=0)
            for k in GRIDS:
                c, s = basis(data["timestampsMs"], k)
                assert min(c.min(), s.min()) >= -1024 and max(c.max(), s.max()) <= 1023
                cc, ss, cs = (c * c).sum(axis=1), (s * s).sum(axis=1), (c * s).sum(axis=1)
                det = cc * ss - cs * cs
                assert min(det) > 0
                cp, sp = c @ y, s @ y
                num = ss[:, None] * cp * cp - 2 * cs[:, None] * cp * sp + cc[:, None] * sp * sp
                den = det[:, None] * yy[None, :]
                assert min(num[:, 0]) >= 0
                assert max(num[:, 0]) * max(den[:, 0]) < 2 ** (236 if n == 64 else 246)
