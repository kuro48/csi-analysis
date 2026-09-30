"""Input-only fixed-point VMD approximation proof service."""

from typing import Any, Dict, List, Optional
from app.services.zkp_circuit_service import ZKPCircuitService


class VmdApproxService(ZKPCircuitService):
    CIRCUIT_NAME = "csi_vmd_approx"
    N = 128

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(self.CIRCUIT_NAME, zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(self, waveform: List[int]) -> Dict[str, Any]:
        if len(waveform) != self.N or any(type(x) is not int or not -100 <= x <= 100 for x in waveform):
            raise ValueError("waveform must contain 128 integers in [-100, 100]")
        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if self._circuit_build_is_stale(wasm, zkey):
            raise FileNotFoundError(
                "VMD approximation artifacts missing or stale. Run: cd zkp && npm run compile:vmd_approx && npm run setup:vmd_approx"
            )
        proof, signals, valid, benchmark = await self._generate_proof_with_benchmark(
            {"waveform": waveform}, verify=True
        )
        if not valid:
            raise RuntimeError("VMD approximation proof failed local verification")
        if len(signals) != 3:
            raise RuntimeError(f"VMD approximation circuit returned {len(signals)} public signals; expected 3")
        if int(signals[0]) not in (0, 1) or not 0 <= int(signals[1]) <= 63 or not 0 <= int(signals[2]) <= 2:
            raise RuntimeError("VMD approximation circuit returned invalid public signals")
        bin_no = int(signals[1])
        return {
            "proof": proof,
            "publicSignals": signals,
            "isNormal": bool(int(signals[0])),
            "estimatedFrequencyBin": bin_no,
            "selectedMode": int(signals[2]),
            "estimatedBpm": bin_no * 120 / self.N,
            "isValid": valid,
            "method": "vmd_approx_fixed_point",
            "proofScope": "waveform-derived spectral VMD approximation",
            "approximation": {"sample_rate_hz": 2, "iterations": 4, "modes": 3},
            "benchmark": benchmark,
            "performance": self._performance_from_benchmark(benchmark),
        }
