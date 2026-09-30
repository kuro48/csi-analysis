"""lomb-scargle.ipynb由来パイプラインの単体テスト。"""

import numpy as np
import pytest

from app.services.lomb_scargle_pipeline import (
    CIRCOM_FREQUENCIES,
    CIRCOM_SAMPLES,
    N_FREQUENCIES,
    PCA_COMPONENTS,
    PERIODOGRAM_POWER_SCALE,
    quantize_periodograms,
    run_lomb_scargle_pipeline,
    run_lomb_scargle_pipeline_from_pca,
)


def _irregular_pca_output(breathing_hz: float = 0.25):
    rng = np.random.default_rng(42)
    intervals = np.clip(0.01 + rng.normal(0, 0.0015, 3200), 0.004, None)
    t = np.cumsum(intervals)
    t -= t[0]
    breathing = np.sin(2 * np.pi * breathing_hz * t)
    principal_components = np.column_stack(
        [
            breathing + 0.025 * rng.standard_normal(t.size),
            0.2 * rng.standard_normal(t.size),
            0.1 * rng.standard_normal(t.size),
        ]
    )
    timestamps_ns = np.rint(t * 1e9).astype(np.int64) + 1_700_000_000_000_000_000
    return principal_components, timestamps_ns


@pytest.mark.unit
def test_lomb_scargle_recovers_breathing_from_irregular_timestamps():
    principal_components, timestamps_ns = _irregular_pca_output()

    result = run_lomb_scargle_pipeline_from_pca(principal_components, timestamps_ns)

    assert result["algorithm_version"] == "shared-pca-lomb-scargle-circom-reanchored-trig-v4"
    assert abs(result["breathing_rate_bpm"] - 15.0) < 0.5
    assert abs(result["global_peak_bpm"] - 15.0) < 0.5
    assert result["sampling_interval_cv"] > 0.05
    assert result["n_subcarriers_selected"] == 0
    assert len(result["certificate_input"]["samples"]) == PCA_COMPONENTS
    assert len(result["certificate_input"]["samples"][0]) == CIRCOM_SAMPLES
    assert len(result["certificate_input"]["timestampsMs"]) == CIRCOM_SAMPLES
    assert result["certificate_input"]["timestampsMs"][0] == 0
    assert all(isinstance(value, int) for value in result["certificate_input"]["timestampsMs"])
    assert all(0 <= value < 2**11 for row in result["certificate_input"]["samples"] for value in row)
    assert "trigonometric approximation" in result["circom_scope"]
    assert "re-anchored" in result["circom_scope"]
    assert "is_normal" not in result
    assert [step["key"] for step in result["processing_steps"]] == [
        "timestamp_preparation",
        "periodogram",
        "peak_selection",
        "circuit_input",
    ]
    assert all(step["seconds"] >= 0 for step in result["processing_steps"])
    assert sum(step["seconds"] for step in result["processing_steps"]) <= result["processing_time_seconds"]


@pytest.mark.unit
def test_lomb_scargle_sorts_and_removes_duplicate_timestamps():
    principal_components, timestamps_ns = _irregular_pca_output()
    timestamps_ns[11] = timestamps_ns[10]
    order = np.arange(timestamps_ns.size)[::-1]

    result = run_lomb_scargle_pipeline_from_pca(principal_components[order], timestamps_ns[order])

    assert result["duplicates_removed"] == 1
    assert result["n_samples"] == principal_components.shape[0] - 1
    assert abs(result["breathing_rate_bpm"] - 15.0) < 0.5


@pytest.mark.unit
def test_lomb_scargle_consumes_shared_pipeline_input_without_csi_preprocessing():
    principal_components, timestamps_ns = _irregular_pca_output()
    pipeline_input = {
        "principal_components": principal_components,
        "timestamps_ns": timestamps_ns,
        "pc_explained_variance_ratio": np.array([0.8, 0.15, 0.05]),
        "selected_subcarrier_indices": np.array([2, 4, 8]),
        "selected_snr": np.array([1.5, 2.0, 2.5]),
        "n_subcarriers_total": 16,
    }

    result = run_lomb_scargle_pipeline(pipeline_input)

    assert abs(result["breathing_rate_bpm"] - 15.0) < 0.5
    assert result["n_subcarriers_total"] == 16
    assert result["selected_subcarrier_indices"] == [2, 4, 8]
    assert result["pc_explained_variance_ratio"] == pytest.approx([0.8, 0.15, 0.05])


@pytest.mark.unit
def test_quantize_periodograms_enforces_fixed_shape_and_range():
    values = np.zeros((PCA_COMPONENTS, N_FREQUENCIES))
    values[0, :4] = [-1.0, 0.25, 1.0, 2.0]

    quantized = quantize_periodograms(values)

    assert quantized[0][:4] == [0, 250_000, PERIODOGRAM_POWER_SCALE, PERIODOGRAM_POWER_SCALE]
    with pytest.raises(ValueError):
        quantize_periodograms(np.zeros((1, N_FREQUENCIES)))
