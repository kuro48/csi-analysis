"""Reduced fixed-point PCA projection witness and proof service."""

from typing import Any, Dict, List, Optional

import numpy as np

from app.services.poseidon_commitment import commit_preprocess_input, commit_preprocess_projection, new_commitment_nonce
from app.services.zkp_circuit_service import ZKPCircuitService


def prepare_projection_witness(
    centered_matrix: np.ndarray,
    component_weights: np.ndarray,
    reference_projection: np.ndarray,
    *,
    samples: int = 32,
    features: int = 8,
) -> Dict[str, Any]:
    matrix = np.asarray(centered_matrix, dtype=np.float64)
    weights = np.asarray(component_weights, dtype=np.float64).reshape(-1)
    reference = np.asarray(reference_projection, dtype=np.float64).reshape(-1)
    if matrix.ndim != 2 or matrix.shape[0] != reference.size or matrix.shape[1] != weights.size:
        raise ValueError("PCA matrix, weights, and projection shapes do not agree")

    chosen_features = np.argsort(np.abs(weights))[-features:]
    chosen_samples = np.linspace(0, matrix.shape[0] - 1, samples, dtype=int)
    reduced_matrix = matrix[np.ix_(chosen_samples, chosen_features)]
    reduced_weights = weights[chosen_features]
    matrix_scale = 127 / max(float(np.max(np.abs(reduced_matrix))), 1e-12)
    weight_scale = 127 / max(float(np.max(np.abs(reduced_weights))), 1e-12)
    matrix_int = np.rint(reduced_matrix * matrix_scale).astype(int)
    weights_int = np.rint(reduced_weights * weight_scale).astype(int)
    projected = matrix_int @ weights_int
    approximate = projected.astype(float) / (matrix_scale * weight_scale)
    reference_reduced = reference[chosen_samples]
    correlation = float(np.corrcoef(approximate, reference_reduced)[0, 1]) if np.std(approximate) > 0 else 0.0
    return {
        "centeredX": matrix_int.tolist(),
        "weights": weights_int.tolist(),
        "projected": projected.astype(int).tolist(),
        "diagnostics": {
            "selected_feature_indices": chosen_features.astype(int).tolist(),
            "matrix_scale": matrix_scale,
            "weight_scale": weight_scale,
            "reference_correlation": correlation,
            "scope": "reduced quantized PCA projection; SNR/filter/eigenvector maximality unproved",
        },
    }


class PreprocessProjectionService(ZKPCircuitService):
    CIRCUIT_NAME = "csi_preprocess_projection"

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(self.CIRCUIT_NAME, zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(
        self,
        centered_x: List[List[int]],
        weights: List[int],
        projected: List[int],
        commitment_nonce: Optional[int] = None,
    ) -> Dict[str, Any]:
        if len(centered_x) != 32 or any(len(row) != 8 for row in centered_x):
            raise ValueError("centered_x must have shape [32][8]")
        if len(weights) != 8 or len(projected) != 32:
            raise ValueError("weights/projected must have lengths 8/32")
        expected = [sum(row[index] * weights[index] for index in range(8)) for row in centered_x]
        if expected != [int(value) for value in projected]:
            raise ValueError("projected does not equal centered_x @ weights")
        nonce = commitment_nonce if commitment_nonce is not None else new_commitment_nonce()
        input_commitment = commit_preprocess_input(centered_x, weights, nonce, str(self.zkp_dir))
        output_commitment = commit_preprocess_projection(projected, nonce, str(self.zkp_dir))
        input_data = {
            "centeredX": centered_x,
            "weights": weights,
            "commitmentNonce": str(nonce),
            "inputCommitment": input_commitment.value,
        }
        proof, signals, valid, benchmark = await self._generate_proof_with_benchmark(input_data, verify=True)
        if not valid or len(signals) < 2:
            raise RuntimeError("Preprocess projection proof failed local verification")
        if str(signals[0]) != output_commitment.value or str(signals[1]) != input_commitment.value:
            raise RuntimeError("Preprocess projection returned unexpected commitments")
        return {
            "proof": proof,
            "publicSignals": signals,
            "isValid": True,
            "method": "preprocess_projection",
            "inputCommitment": input_commitment.as_dict(),
            "projectionCommitment": output_commitment.as_dict(),
            "benchmark": benchmark,
            "performance": self._performance_from_benchmark(benchmark),
        }
