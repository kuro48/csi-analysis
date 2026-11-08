"""Exercise the shipped edge selector without a dependency on backend configuration."""
import sys
from pathlib import Path

import numpy as np
import pytest

BIN = Path(__file__).resolve().parents[3] / "edge/lomb_scargle_e2e/bin"
sys.path.insert(0, str(BIN))
from select_subcarriers import capture_rows, rank_subcarriers, select_capture
from prepare_input import canonicalize, load_npz


def capture(seed=4, frequency=0.25):
    rng = np.random.default_rng(seed)
    times = np.cumsum(rng.uniform(0.045, 0.075, 1000))
    stamps = np.rint(times * 1e9).astype(np.int64)
    amplitude = 1 + rng.normal(0, 0.002, (times.size, 80))
    active = np.array([3, 6, 14, 25, 38, 46, 57, 73])
    for j, sc in enumerate(active):
        amplitude[:, sc] = 1 + (0.12 + j * 0.008) * np.sin(2 * np.pi * frequency * times + j * 0.41)
    amplitude[:, 0] = 100  # strong stationary carrier is not strong motion
    amplitude[:, 1] = np.abs(1 + rng.normal(0, 0.35, times.size))  # large white noise
    amplitude[:, 2] = 1e-6 * (1 + 0.4 * np.sin(times))  # deep fade
    amplitude[:, 4] = 1
    amplitude[100, 4] = 100  # single impulsive spike
    phase = rng.normal(0, 0.04, amplitude.shape)
    return amplitude * np.exp(1j * phase), stamps, active


def test_motion_channels_beat_static_noise_null_and_impulse():
    csi, stamps, active = capture()
    chosen, _, metadata = select_capture(csi, stamps)
    assert chosen.shape == (64, 8)
    assert set(metadata["selected_subcarrier_indices"]) == set(active)
    assert metadata["selection"]["proof_scope"] == "selection_not_proven"
    assert not metadata["selection"]["low_quality_fallback"]


def test_selection_does_not_use_normal_breathing_band():
    csi, stamps, active = capture(frequency=1.2)
    _, _, metadata = select_capture(csi, stamps)
    assert set(metadata["selected_subcarrier_indices"]) == set(active)


def test_scale_phase_and_row_order_invariance_and_original_iq_preserved():
    csi, stamps, _ = capture()
    selected, selected_stamps, metadata = select_capture(csi, stamps)
    shuffled = np.random.default_rng(31).permutation(stamps.size)
    _, other_stamps, other = select_capture(csi[shuffled] * 20 * np.exp(1.2j), stamps[shuffled])
    assert metadata["selected_subcarrier_indices"] == other["selected_subcarrier_indices"]
    np.testing.assert_array_equal(selected_stamps, other_stamps)
    _, proof = capture_rows(stamps)
    np.testing.assert_array_equal(selected, csi[np.ix_(proof, metadata["selected_subcarrier_indices"])])


def test_uniform_reproduces_old_indices_and_time_sampling():
    csi, stamps, _ = capture()
    result, sampled_stamps, metadata = select_capture(csi, stamps, "uniform")
    rows = np.rint(np.linspace(0, 999, 64)).astype(int)
    columns = np.rint(np.linspace(0, 79, 8)).astype(int)
    np.testing.assert_array_equal(result, csi[np.ix_(rows, columns)])
    np.testing.assert_array_equal(sampled_stamps, stamps[rows])
    assert metadata["selected_subcarrier_indices"] == columns.tolist()


def test_bad_channels_excluded_and_duplicate_timestamps_deterministic():
    csi, stamps, _ = capture()
    csi[:, 8] = np.nan
    csi[:, 9] = np.inf
    repeated = np.repeat(csi, 2, axis=0)
    times = np.repeat(stamps, 2)
    _, _, actual = select_capture(repeated, times)
    _, _, expected = select_capture(csi, stamps)
    assert actual["selected_subcarrier_indices"] == expected["selected_subcarrier_indices"]
    assert 8 not in actual["selected_subcarrier_indices"] and 9 not in actual["selected_subcarrier_indices"]


def test_insufficient_dynamic_channels_fails_instead_of_duplicating_or_faking_motion():
    csi, stamps, _ = capture()
    with pytest.raises(ValueError, match="distinct"):
        select_capture(csi[:, :7], stamps)
    with pytest.raises(ValueError, match="usable dynamic"):
        select_capture(np.ones_like(csi), stamps)
    with pytest.raises(ValueError, match="nonzero"):
        select_capture(np.zeros_like(csi), stamps)
    with pytest.raises(ValueError, match="unique millisecond"):
        select_capture(csi, np.zeros(stamps.size, dtype=np.int64))


def test_bounded_analysis_and_shared_scale_quantization():
    csi, stamps, _ = capture()
    values = np.tile(csi, (6, 1))
    times = np.concatenate([stamps - stamps[0] + k * 61_000_000_000 for k in range(6)])
    analysis, proof = capture_rows(times)
    assert len(analysis) == 1024 and len(proof) == 64
    assert len(set(analysis)) == 1024
    selected, ts, metadata = select_capture(values, times)
    payload, conversion = canonicalize(selected, ts)
    assert np.shape(payload["csiI"]) == (64, 8)
    assert conversion["encoded_min"] >= 0 and conversion["encoded_max"] < 4096
    assert "selection" not in payload and "selected_subcarrier_indices" not in payload
    assert metadata["selection"]["analysis_rows"] == 1024


def test_shared_scale_degeneracy_is_reported_before_witness_generation():
    csi, stamps, _ = capture()
    selected, ts, _ = select_capture(csi, stamps)
    selected[:, 0] *= 1e9
    with pytest.raises(ValueError, match="constant after shared"):
        canonicalize(selected, ts)


def test_npz_default_and_legacy_are_both_usable(tmp_path):
    csi, stamps, active = capture()
    source = tmp_path / "capture.npz"
    np.savez(source, csi=csi, timestamps_ns=stamps)
    selected, ts, metadata = load_npz(source)
    assert set(metadata["selected_subcarrier_indices"]) == set(active)
    assert selected.shape == (64, 8) and ts.size == 64
    _, _, old = load_npz(source, "uniform")
    assert old["selection"]["method"] == "uniform-v1"


def test_npz_rejects_fractional_and_overflowing_timestamps(tmp_path):
    csi, stamps, _ = capture()
    source = tmp_path / "bad.npz"
    np.savez(source, csi=csi, timestamps_ns=stamps.astype(float))
    with pytest.raises(ValueError, match="integer timestamps"):
        load_npz(source)
    np.savez(source, csi=csi, timestamps_ms=np.full(stamps.size, 2**63 - 1, dtype=np.int64))
    with pytest.raises(ValueError, match="range"):
        load_npz(source)


def test_picoscenes_modal_width_bounded_loader_matches_npz(monkeypatch):
    import prepare_input as module

    csi, stamps, _ = capture()
    csi = np.tile(csi, (3, 1))
    stamps = np.concatenate([stamps + k * 61_000_000_000 for k in range(3)])
    frames = [
        {"CSI": {"CSI": csi[i], "numTones": 80, "numRx": 1, "numTx": 1}, "RxSBasic": {"systemns": stamps[i]}}
        for i in range(len(stamps))
    ]
    # Interleave frames of a non-modal CSI width, as actual PicoScenes captures do.
    frames.insert(3, {"CSI": {"CSI": np.ones(53)}, "RxSBasic": {"systemns": stamps[2] + 1}})

    class Parser:
        raw = []

        def seek(self, path, offset, count):
            self.raw = frames[offset : offset + count]

    monkeypatch.setattr(module, "_new_parser", Parser)
    monkeypatch.setattr(
        module, "_frame_batches", lambda path: [(i, min(32, len(frames) - i)) for i in range(0, len(frames), 32)]
    )
    for method in ("uniform", "motion-quality"):
        actual, actual_t, metadata = module.load_picoscenes(Path("unused.csi"), method)
        expected, expected_t, expected_metadata = select_capture(csi, stamps, method)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual_t, expected_t)
        assert metadata["selected_subcarrier_indices"] == expected_metadata["selected_subcarrier_indices"]
        assert metadata["modal_csi_width"] == 80
        assert metadata["buffered_full_width_frames"] <= 1088


def test_exact_ties_are_deterministic():
    stamps = (np.arange(1000) * 50_000_000).astype(np.int64)
    trace = 1 + 0.1 * np.sin(np.arange(1000) * 0.07)
    csi = np.tile(trace[:, None], (1, 12)).astype(complex)
    _, _, metadata = select_capture(csi, stamps)
    assert metadata["selected_subcarrier_indices"] == list(range(8))
