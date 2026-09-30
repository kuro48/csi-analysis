"""タイムスタンプ由来の固定小数点Lomb--Scargle用Circom証明サービス。"""

import logging
from typing import Any, Dict, List, Optional

from app.services.lomb_scargle_pipeline import (
    CIRCOM_FREQUENCIES_HZ,
    CIRCOM_SAMPLES,
    CIRCOM_TIMESTAMP_BITS,
    PCA_COMPONENTS,
)
from app.services.zkp_circuit_service import ZKPCircuitService

logger = logging.getLogger(__name__)


class LombScargleCertificateService(ZKPCircuitService):
    """固定小数点PCA波形からLomb--Scargle投影と判定を証明する。"""

    CIRCUIT_NAME = "csi_lomb_scargle_normality"

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(self.CIRCUIT_NAME, zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(  # type: ignore[override]
        self,
        samples: Optional[List[List[int]]] = None,
        timestamps_ms: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        if samples is None or timestamps_ms is None:
            raise ValueError("samples and timestamps_ms are required for LombScargleFixedPointCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                "Run: cd zkp && npm run compile:lomb_scargle && npm run setup:lomb_scargle"
            )
        if self._circuit_build_is_stale(wasm, zkey):
            raise RuntimeError(
                f"{self.label} ZKP circuit files are stale. "
                "Run: cd zkp && npm run compile:lomb_scargle && npm run setup:lomb_scargle"
            )

        input_data = self._prepare_input(samples, timestamps_ms)
        proof, public_signals, is_valid, benchmark = await self._generate_proof_with_benchmark(
            input_data,
            verify=True,
        )
        performance = self._performance_from_benchmark(benchmark)
        if not is_valid:
            raise RuntimeError(f"{self.label} proof failed local verification")

        if len(public_signals) < 4:
            raise RuntimeError(f"{self.label} returned incomplete public signals")
        is_normal = bool(int(public_signals[0]))
        selected_pc = int(public_signals[1]) + 1
        estimated_bin = int(public_signals[2])
        global_peak_bin = int(public_signals[3])
        estimated_frequency_hz = float(CIRCOM_FREQUENCIES_HZ[estimated_bin])
        global_peak_frequency_hz = float(CIRCOM_FREQUENCIES_HZ[global_peak_bin])
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
            "method": "lomb_scargle_timestamp_trig_fixed_point",
            "selectedPc": selected_pc,
            "estimatedFrequencyBin": estimated_bin,
            "globalPeakFrequencyBin": global_peak_bin,
            "estimatedFrequencyHz": estimated_frequency_hz,
            "estimatedBpm": estimated_frequency_hz * 60,
            "globalPeakFrequencyHz": global_peak_frequency_hz,
            "globalPeakBpm": global_peak_frequency_hz * 60,
            "proofScope": "timestamp_reanchored_trig_approximation_tau_free_lomb_scargle_pc_selection_argmax_normal_band",
            "performance": performance,
            "benchmark": benchmark,
        }

    def _prepare_input(  # type: ignore[override]
        self,
        samples: List[List[int]],
        timestamps_ms: List[int],
    ) -> Dict[str, Any]:
        def validate_matrix(name: str, matrix: List[List[int]], rows: int, columns: int) -> List[List[int]]:
            if len(matrix) != rows:
                raise ValueError(f"{name} は {rows} 行である必要があります")
            normalized: List[List[int]] = []
            for row_index, row in enumerate(matrix):
                if len(row) != columns:
                    raise ValueError(f"{name}[{row_index}] は長さ {columns} である必要があります")
                values = [int(value) for value in row]
                if any(value < 0 or value >= 2**11 for value in values):
                    raise ValueError(f"{name}[{row_index}] は11-bit範囲外です")
                normalized.append(values)
            return normalized

        if len(timestamps_ms) != CIRCOM_SAMPLES:
            raise ValueError(f"timestamps_ms は長さ {CIRCOM_SAMPLES} である必要があります")
        normalized_timestamps = [int(value) for value in timestamps_ms]
        if any(value < 0 or value >= 2**CIRCOM_TIMESTAMP_BITS for value in normalized_timestamps):
            raise ValueError(f"timestamps_ms は{CIRCOM_TIMESTAMP_BITS}-bit範囲外です")
        if normalized_timestamps[0] != 0:
            raise ValueError("timestamps_ms[0] は0である必要があります")
        return {
            "samples": validate_matrix("samples", samples, PCA_COMPONENTS, CIRCOM_SAMPLES),
            "timestampsMs": normalized_timestamps,
        }
