"""C1-bound VMD certificate proof service."""

import logging
from typing import Any, Dict, List, Optional

from app.services.breathing_certificate_service import BreathingCertificateService
from app.services.poseidon_commitment import commit_vmd_input, new_commitment_nonce

logger = logging.getLogger(__name__)


class CommittedBreathingCertificateService(BreathingCertificateService):
    """Generate a certificate whose private VMD input is bound to public C1."""

    CIRCUIT_NAME = "csi_breathing_certificate_committed"

    async def generate_proof(  # type: ignore[override]
        self,
        vmd_input: Optional[List[int]] = None,
        modes: Optional[List[List[int]]] = None,
        sel: Optional[List[int]] = None,
        commitment_nonce: Optional[int] = None,
    ) -> Dict[str, Any]:
        if vmd_input is None or modes is None or sel is None:
            raise ValueError("vmd_input, modes, sel are required")
        nonce = commitment_nonce if commitment_nonce is not None else new_commitment_nonce()
        commitment = commit_vmd_input(vmd_input, nonce, zkp_dir=str(self.zkp_dir))
        input_data = self._prepare_input(vmd_input, modes, sel)
        input_data.update(
            {
                "commitmentNonce": str(nonce),
                "vmdCommitment": commitment.value,
            }
        )

        proof, public_signals, is_valid, benchmark = await self._generate_proof_with_benchmark(input_data, verify=True)
        if not is_valid:
            raise RuntimeError(f"{self.label} proof failed local verification")
        if len(public_signals) < 2 or str(public_signals[1]) != commitment.value:
            raise RuntimeError("Committed certificate returned an unexpected public C1")
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": bool(int(public_signals[0])),
            "isValid": True,
            "method": "breathing_certificate_committed",
            "commitment": commitment.as_dict(),
            "performance": self._performance_from_benchmark(benchmark),
            "benchmark": benchmark,
        }
