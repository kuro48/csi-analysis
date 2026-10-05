import numpy as np
import pytest

from app.services.poseidon_commitment import commit_raw_csi, commit_vmd_input


@pytest.mark.unit
def test_vmd_commitment_is_deterministic_and_binds_nonce():
    first = commit_vmd_input([-100, 0, 100], nonce=7)
    same = commit_vmd_input([-100, 0, 100], nonce=7)
    different_nonce = commit_vmd_input([-100, 0, 100], nonce=8)

    assert first.value == same.value
    assert first.value != different_nonce.value
    assert first.metadata == (3, 1024)
    assert "nonce" not in first.as_dict()


@pytest.mark.unit
def test_raw_csi_commitment_binds_shape_and_iq_order():
    matrix = np.array([[1 + 2j, 3 + 4j]])
    reshaped = np.array([[1 + 2j], [3 + 4j]])

    first = commit_raw_csi(matrix, nonce=9)
    assert first.value != commit_raw_csi(reshaped, nonce=9).value
    assert first.metadata[:2] == (1, 2)


@pytest.mark.unit
def test_vmd_commitment_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="VMD input"):
        commit_vmd_input([1024], nonce=1)
