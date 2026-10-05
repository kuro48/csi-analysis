import numpy as np
import pytest

from app.services.poseidon_commitment import commit_preprocess_input, commit_preprocess_projection
from app.services.preprocess_projection_service import prepare_projection_witness


@pytest.mark.unit
def test_projection_witness_is_exact_after_quantization():
    rng = np.random.default_rng(4)
    matrix = rng.normal(size=(100, 12))
    weights = rng.normal(size=12)
    reference = matrix @ weights

    witness = prepare_projection_witness(matrix, weights, reference)

    expected = [sum(row[index] * witness["weights"][index] for index in range(8)) for row in witness["centeredX"]]
    assert witness["projected"] == expected
    assert len(witness["centeredX"]) == 32
    assert witness["diagnostics"]["reference_correlation"] > 0.5


@pytest.mark.unit
def test_projection_commitments_bind_inputs_and_output():
    matrix = [[index - 4 for index in range(8)] for _ in range(32)]
    weights = list(range(8))
    projected = [sum(row[index] * weights[index] for index in range(8)) for row in matrix]

    input_commitment = commit_preprocess_input(matrix, weights, nonce=5)
    output_commitment = commit_preprocess_projection(projected, nonce=5)

    assert input_commitment.value != output_commitment.value
    assert input_commitment.value != commit_preprocess_input(matrix, weights, nonce=6).value
