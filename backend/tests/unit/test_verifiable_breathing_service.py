"""5-1 / Lomb--Scargle 呼吸解析の Circom 並列実行契約。"""

import asyncio

import pytest


@pytest.mark.unit
def test_bpm_evaluation_is_added_after_analysis_with_table_ready_rows():
    from app.services.verifiable_breathing_service import attach_bpm_evaluation

    result = {
        "analysis": {
            "breathing_rate_bpm": 15.5,
            "lomb_scargle": {"breathing_rate_bpm": 14.75},
        },
    }

    attach_bpm_evaluation(result, 15.0)

    evaluation = result["bpm_evaluation"]
    assert evaluation["ground_truth_bpm"] == 15.0
    assert [row["method"] for row in evaluation["rows"]] == ["5-1", "lomb_scargle"]
    assert [row["measured_bpm"] for row in evaluation["rows"]] == [15.5, 14.75]
    assert [row["absolute_error_bpm"] for row in evaluation["rows"]] == [0.5, 0.25]


@pytest.mark.unit
@pytest.mark.parametrize("ground_truth_bpm", [0, -1, 121, float("nan")])
def test_bpm_evaluation_rejects_invalid_ground_truth(ground_truth_bpm):
    from app.services.verifiable_breathing_service import attach_bpm_evaluation

    with pytest.raises(ValueError, match="正解BPM"):
        attach_bpm_evaluation({}, ground_truth_bpm)


PIPELINE_RESULT = {
    "vmd_approx_input": {"waveform": [0] * 128},
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
}

LOMB_CERTIFICATE_INPUT = {
    "samples": [[1024] * 384 for _ in range(3)],
    "timestampsMs": list(range(384)),
}

LOMB_RESULT = {
    "algorithm_version": "lomb-scargle.ipynb-v1",
    "breathing_rate_bpm": 15.1,
    "peak_freq_hz": 0.2517,
    "global_peak_bpm": 15.1,
    "selected_pc": 1,
    "certificate_input": LOMB_CERTIFICATE_INPUT,
}


class _CircomService:
    def __init__(self, started, release):
        self.started = started
        self.release = release

    async def generate_proof(self, waveform):
        assert waveform == [0] * 128
        self.started.add("circom")
        await self.release.wait()
        return {
            "proof": {"pi_a": ["1"]},
            "publicSignals": ["1", "16", "0"],
            "isNormal": True,
            "isValid": True,
            "method": "breathing_certificate",
        }


class _LombCircomService:
    def __init__(self, started=None, release=None):
        self.started = started
        self.release = release

    async def generate_proof(self, samples, timestamps_ms):
        assert len(samples) == 3
        assert len(timestamps_ms) == 384
        if self.started is not None:
            self.started.add("lomb_circom")
        if self.release is not None:
            await self.release.wait()
        return {
            "proof": {"pi_a": ["2"]},
            "publicSignals": ["1", "0", "139", "139"],
            "isNormal": True,
            "isValid": True,
            "method": "lomb_scargle_timestamp_trig_fixed_point",
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runs_both_circom_proofs_concurrently_and_hides_private_inputs():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    started = set()
    release = asyncio.Event()
    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=lambda: _CircomService(started, release),
        lomb_scargle_runner=lambda _: LOMB_RESULT,
        lomb_circom_service_factory=lambda: _LombCircomService(started, release),
    )

    task = asyncio.create_task(service.analyze("sample.csi"))
    for _ in range(100):
        if started == {"circom", "lomb_circom"}:
            break
        await asyncio.sleep(0.01)

    assert started == {"circom", "lomb_circom"}
    release.set()
    result = await task

    assert result["status"] == "completed"
    assert set(result["proofs"]) == {"python_circom", "lomb_scargle_circom"}
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"]["status"] == "completed"
    assert result["disabled_methods"] == [
        "wavelet",
        "music",
        "fft_cosine_similarity",
    ]
    assert "certificate_input" not in result["analysis"]
    assert result["analysis"]["algorithm_comparison"]["absolute_difference_bpm"] == pytest.approx(0.1)
    assert "certificate_input" not in result["analysis"]["lomb_scargle"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_passes_existing_pipeline_pca_output_to_lomb_scargle():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    shared_input = {"principal_components": object(), "timestamps_ns": object()}
    observed = {}

    def pipeline_runner(file_path, include_lomb_scargle_input=False):
        observed["include_lomb_scargle_input"] = include_lomb_scargle_input
        return {
            **PIPELINE_RESULT,
            "_lomb_scargle_input": shared_input,
        }

    def lomb_runner(pipeline_input):
        observed["lomb_input"] = pipeline_input
        return LOMB_RESULT

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    service = VerifiableBreathingService(
        pipeline_runner=pipeline_runner,
        circom_service_factory=_WorkingCircom,
        lomb_scargle_runner=lomb_runner,
        lomb_circom_service_factory=_LombCircomService,
    )

    result = await service.analyze("sample.csi")

    assert observed["include_lomb_scargle_input"] is True
    assert observed["lomb_input"] is shared_input
    assert "_lomb_scargle_input" not in result["analysis"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preserves_circom_result_when_lomb_scargle_fails():
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    def broken_lomb_runner(_):
        raise RuntimeError("lomb-scargle unavailable")

    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=_WorkingCircom,
        lomb_scargle_runner=broken_lomb_runner,
        lomb_circom_service_factory=_LombCircomService,
    )

    result = await service.analyze("sample.csi")

    assert result["status"] == "partial"
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"] == {
        "status": "failed",
        "error": "lomb-scargle unavailable",
        "error_type": "RuntimeError",
    }
    assert result["analysis"]["lomb_scargle"]["status"] == "failed"
