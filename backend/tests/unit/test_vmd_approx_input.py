import numpy as np
import pytest

from app.services.breathing_pipeline import prepare_vmd_approx_input


def test_sinusoid_is_resampled_to_128_bounded_integer_samples():
    time = np.arange(6400) / 100.0
    result = prepare_vmd_approx_input(np.sin(2 * np.pi * 0.25 * time))

    waveform = result["waveform"]
    assert len(waveform) == 128
    assert all(isinstance(value, int) for value in waveform)
    assert max(waveform) <= 100
    assert min(waveform) >= -100


def test_zero_input_is_accepted():
    assert prepare_vmd_approx_input(np.zeros(6400))["waveform"] == [0] * 128


@pytest.mark.parametrize("value", [np.array([]), np.array([np.nan]), np.array([np.inf]), np.array([-np.inf])])
def test_empty_or_non_finite_input_is_rejected(value):
    with pytest.raises(ValueError):
        prepare_vmd_approx_input(value)


def test_equal_input_is_deterministic():
    signal = np.linspace(-1.0, 1.0, 6400)
    assert prepare_vmd_approx_input(signal) == prepare_vmd_approx_input(signal.copy())
