"""5-1 呼吸解析の Circom / zkVM 並列実行契約。"""

import asyncio

import pytest


PIPELINE_RESULT = {
    "respiration_waveform": [0.1, -0.2, 0.1],
    "breathing_rate_bpm": 15.0,
    "peak_freq_hz": 0.25,
    "selected_pc": 1,
    "selected_vmd_mode": 0,
    "certificate_input": {
        "vmdInput": [1, 2, 1],
        "modes": [[1, 2, 1]] * 5,
        "sel": [1, 0, 0, 0, 0],
        "diagnostics": {"recon_ok": True},
    },
    "zkvm_input": {
        "samples": 3,
        "subcarriers": 2,
        "amplitudes": [10, 20, 11, 21, 10, 19],
        "scale": 100,
        "input_commitment": "abc123",
    },
}


class _CircomService:
    def __init__(self, started, release):
        self.started = started
        self.release = release

    async def generate_proof(self, vmd_input, modes, sel):
        self.started.add("circom")
        await self.release.wait()
        return {
            "proof": {"pi_a": ["1"]},
            "publicSignals": ["1"],
            "isNormal": True,
            "isValid": True,
            "method": "breathing_certificate",
        }


class _ZkVMService:
    def __init__(self, started, release):
        self.started = started
        self.release = release

    async def generate_proof(self, pipeline_input):
        assert pipeline_input["input_commitment"] == "abc123"
        self.started.add("zkvm")
        await self.release.wait()
        return {
            "receipt": "base64-receipt",
            "journal": {
                "breathing_rate_milli_bpm": 15000,
                "is_normal": True,
                "input_commitment": "abc123",
            },
            "isNormal": True,
            "isValid": True,
            "method": "risc0_5_1_fixed_v1",
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runs_circom_and_zkvm_concurrently_and_hides_private_inputs():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    started = set()
    release = asyncio.Event()
    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=lambda: _CircomService(started, release),
        zkvm_service=_ZkVMService(started, release),
    )

    task = asyncio.create_task(service.analyze("sample.csi"))
    for _ in range(50):
        if started == {"circom", "zkvm"}:
            break
        await asyncio.sleep(0)

    assert started == {"circom", "zkvm"}
    release.set()
    result = await task

    assert result["status"] == "completed"
    assert set(result["proofs"]) == {"python_circom", "zkvm"}
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"]["status"] == "completed"
    assert result["disabled_methods"] == [
        "wavelet",
        "music",
        "fft_cosine_similarity",
    ]
    assert "certificate_input" not in result["analysis"]
    assert "zkvm_input" not in result["analysis"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preserves_circom_result_when_zkvm_fails():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    class _BrokenZkVM:
        async def generate_proof(self, pipeline_input):
            raise RuntimeError("prover unavailable")

    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=_WorkingCircom,
        zkvm_service=_BrokenZkVM(),
    )

    result = await service.analyze("sample.csi")

    assert result["status"] == "partial"
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"] == {
        "status": "failed",
        "error": "prover unavailable",
        "error_type": "RuntimeError",
    }
