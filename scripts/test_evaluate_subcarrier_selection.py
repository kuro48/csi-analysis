import json

import evaluate_subcarrier_selection as evaluation
import numpy as np
import pytest
from evaluate_subcarrier_selection import (
    canonicalize_all_columns,
    exact_scores,
    float_scores,
    periodograms,
    rank,
    unique_rows,
    winner,
)
from scipy.signal import lombscargle


def test_exact_reference_ignores_padding_breaks_ties_and_rejects_flat():
    t = np.arange(64)
    signal = 1000 + 100 * np.sin(t / 4)
    matrix = np.column_stack((np.full(64, 1000), signal, signal)).astype(complex)
    data, _ = canonicalize_all_columns(matrix, t * 1000000, capacity=64)
    scores = exact_scores(data)
    assert len(scores) == 3
    assert winner(scores) == 1
    assert rank(scores, 2) == 2
    assert scores[0] == 0
    data["csiI"] = [[3000] * 64 for _ in t]
    assert winner(exact_scores(data)) is None


def test_float_reference_matches_exact_on_integer_inputs_above_int64_range():
    rng = np.random.default_rng(87)
    signed_i = rng.integers(800, 1800, (64, 10))
    signed_q = rng.integers(-1000, 1000, (64, 10))
    data = {"csiI": (signed_i + 2048).tolist(), "csiQ": (signed_q + 2048).tolist(), "candidateCount": 10}
    exact = exact_scores(data)
    assert max(s.denominator for s in exact) > 2**63
    floating = float_scores(signed_i + 1j * signed_q)
    np.testing.assert_allclose([float(s) for s in exact], floating, rtol=1e-12)
    assert winner(exact) == winner(floating)


def test_float_reference_does_not_select_constant_roundoff():
    matrix = np.full((150, 3), 1234.56789 + 987.654321j)
    assert winner(float_scores(matrix)) is None


def test_batched_ls_matches_scipy_and_known_frequency():
    rng = np.random.default_rng(34)
    times = np.sort(rng.uniform(0, 80, 150))
    frequencies = np.linspace(0.05, 0.4, 351)
    power = np.column_stack(
        (100 + 20 * np.sin(2 * np.pi * 0.22 * times), 200 + rng.normal(0, 5, len(times)), np.full(len(times), 64))
    )
    result = periodograms(times, np.sqrt(power).astype(complex), frequencies)
    for column in (0, 1):
        y = power[:, column] - power[:, column].mean()
        reference = lombscargle(times, y, 2 * np.pi * frequencies, normalize=True, floating_mean=True)
        np.testing.assert_allclose(result[:, column], reference, atol=1e-12, rtol=1e-10)
    assert frequencies[np.argmax(result[:, 0])] == pytest.approx(0.22)
    assert result[:, 2].max() == 0


def test_evaluation_rows_match_production_sort_dedup_and_subsample():
    rng = np.random.default_rng(11)
    timestamps = np.arange(140, dtype=np.int64) * 500000
    rng.shuffle(timestamps)
    matrix = np.ones((140, 2), dtype=complex)
    _, metadata = canonicalize_all_columns(matrix, timestamps, capacity=2)
    rows = unique_rows(timestamps)
    assert len(rows) == 71
    expected = rows[np.rint(np.linspace(0, len(rows) - 1, 64)).astype(int)]
    assert metadata["sourceRows"] == expected.tolist()


def test_report_serializes_numpy_ranks_and_records_synthetic_truth(monkeypatch, tmp_path):
    def circuit(data, _):
        return {"selectedColumn": winner(exact_scores(data)), "isNormal": 0, "frequencyBin": 3}

    monkeypatch.setattr(evaluation, "run_circuit", circuit)
    name, matrix, times, truth = next(evaluation.synthetic_cases())
    result = evaluation.compare(name, matrix, times, None, 64, tmp_path, truth)
    restored = json.loads(json.dumps(result, allow_nan=False))
    assert restored["circuitRankUnderPython"]["pythonInteger64"] == 1
    assert restored["groundTruth"] == truth
    assert set(restored["syntheticAccuracy"]) == {"circom", *restored["pythonSelections"]}
