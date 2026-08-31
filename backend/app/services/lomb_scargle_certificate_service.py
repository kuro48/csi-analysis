"""Lomb--Scargleピリオドグラム正常判定用Circom証明サービス。"""

import logging
from typing import Any, Dict, List, Optional

from app.services.lomb_scargle_pipeline import N_FREQUENCIES, PCA_COMPONENTS, PERIODOGRAM_POWER_SCALE
from app.services.zkp_circuit_service import ZKPCircuitService

logger = logging.getLogger(__name__)


class LombScargleCertificateService(ZKPCircuitService):
    """量子化ピリオドグラムのPC選択・argmax・正常帯域を証明する。"""

    CIRCUIT_NAME = "csi_lomb_scargle_normality"

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(self.CIRCUIT_NAME, zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(  # type: ignore[override]
        self,
        powers: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        if powers is None:
            raise ValueError("powers is required for LombScargleNormalityCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                "Run: cd zkp && npm run compile:lomb_scargle && npm run setup:lomb_scargle"
            )

        input_data = self._prepare_input(powers)
        proof, public_signals, performance = await self._prove_with_metrics(input_data)
        is_valid, performance = await self._verify_with_metrics(proof, public_signals, performance)
        if not is_valid:
            raise RuntimeError(f"{self.label} proof failed local verification")

        if len(public_signals) < 4:
            raise RuntimeError(f"{self.label} returned incomplete public signals")
        is_normal = bool(int(public_signals[0]))
        selected_pc = int(public_signals[1]) + 1
        estimated_bin = int(public_signals[2])
        global_peak_bin = int(public_signals[3])
        logger.info(
            "[%s] proof done: isNormal=%s, PC%d, estimatedBin=%d, globalBin=%d",
            self.label,
            is_normal,
            selected_pc,
            estimated_bin,
            global_peak_bin,
        )
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            "isValid": is_valid,
            "method": "lomb_scargle_periodogram_certificate",
            "selectedPc": selected_pc,
            "estimatedFrequencyBin": estimated_bin,
            "globalPeakFrequencyBin": global_peak_bin,
            "proofScope": "periodogram_range_pc_selection_argmax_normal_band",
            "performance": performance,
        }

    def _prepare_input(self, powers: List[List[int]]) -> Dict[str, Any]:  # type: ignore[override]
        if len(powers) != PCA_COMPONENTS:
            raise ValueError(f"powers は {PCA_COMPONENTS} PC分である必要があります")

        normalized: List[List[int]] = []
        for pc_index, row in enumerate(powers):
            if len(row) != N_FREQUENCIES:
                raise ValueError(f"powers[{pc_index}] は長さ {N_FREQUENCIES} である必要があります")
            values = [int(value) for value in row]
            if any(value < 0 or value > PERIODOGRAM_POWER_SCALE for value in values):
                raise ValueError(f"powers[{pc_index}] は 0..{PERIODOGRAM_POWER_SCALE} の範囲外です")
            normalized.append(values)
        return {"powers": normalized}
