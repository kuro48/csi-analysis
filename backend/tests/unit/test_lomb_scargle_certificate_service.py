"""Lomb--Scargle Circomサービスの入力契約。"""

import pytest

from app.services.lomb_scargle_certificate_service import LombScargleCertificateService
from app.services.lomb_scargle_pipeline import N_FREQUENCIES, PCA_COMPONENTS, PERIODOGRAM_POWER_SCALE


def _service_without_setup() -> LombScargleCertificateService:
    return object.__new__(LombScargleCertificateService)


@pytest.mark.unit
def test_prepare_input_accepts_exact_bounded_periodograms():
    powers = [[0] * N_FREQUENCIES for _ in range(PCA_COMPONENTS)]
    powers[2][100] = PERIODOGRAM_POWER_SCALE

    result = _service_without_setup()._prepare_input(powers)

    assert result == {"powers": powers}


@pytest.mark.unit
@pytest.mark.parametrize("value", [-1, PERIODOGRAM_POWER_SCALE + 1])
def test_prepare_input_rejects_out_of_range_power(value):
    powers = [[0] * N_FREQUENCIES for _ in range(PCA_COMPONENTS)]
    powers[0][0] = value

    with pytest.raises(ValueError, match="範囲外"):
        _service_without_setup()._prepare_input(powers)


@pytest.mark.unit
def test_prepare_input_rejects_wrong_shape():
    with pytest.raises(ValueError):
        _service_without_setup()._prepare_input([[0] * N_FREQUENCIES])
