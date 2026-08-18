"""5-1 呼吸解析の Circom / zkVM 並列実行契約。"""

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
        "proofs": {
            "zkvm": {"journal": {"breathing_rate_milli_bpm": 15250}},
        },
    }

    attach_bpm_evaluation(result, 15.0)

    evaluation = result["bpm_evaluation"]
    assert evaluation["ground_truth_bpm"] == 15.0
    assert [row["method"] for row in evaluation["rows"]] == ["5-1", "lomb_scargle", "zkvm"]
    assert [row["measured_bpm"] for row in evaluation["rows"]] == [15.5, 14.75, 15.25]
    assert [row["absolute_error_bpm"] for row in evaluation["rows"]] == [0.5, 0.25, 0.25]


@pytest.mark.unit
@pytest.mark.parametrize("ground_truth_bpm", [0, -1, 121, float("nan")])
def test_bpm_evaluation_rejects_invalid_ground_truth(ground_truth_bpm):
    from app.services.verifiable_breathing_service import attach_bpm_evaluation

    with pytest.raises(ValueError, match="正解BPM"):
        attach_bpm_evaluation({}, ground_truth_bpm)


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

LOMB_RESULT = {
    "algorithm_version": "lomb-scargle.ipynb-v1",
    "breathing_rate_bpm": 15.1,
    "peak_freq_hz": 0.2517,
    "global_peak_bpm": 15.1,
    "selected_pc": 1,
    "certificate_input": {"powers": [[0, 1, 0]] * 3},
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


class _LombCircomService:
    def __init__(self, started=None, release=None):
        self.started = started
        self.release = release

    async def generate_proof(self, powers):
        if self.started is not None:
            self.started.add("lomb_circom")
        if self.release is not None:
            await self.release.wait()
        return {
            "proof": {"pi_a": ["2"]},
            "publicSignals": ["1", "0", "139", "139"],
            "isNormal": True,
            "isValid": True,
            "method": "lomb_scargle_periodogram_certificate",
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runs_circom_and_zkvm_concurrently_and_hides_private_inputs(monkeypatch):
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_ENABLED", True)
    started = set()
    release = asyncio.Event()
    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=lambda: _CircomService(started, release),
        lomb_scargle_runner=lambda _: LOMB_RESULT,
        lomb_circom_service_factory=lambda: _LombCircomService(started, release),
        zkvm_service=_ZkVMService(started, release),
    )

    task = asyncio.create_task(service.analyze("sample.csi"))
    for _ in range(100):
        if started == {"circom", "lomb_circom", "zkvm"}:
            break
        await asyncio.sleep(0.01)

    assert started == {"circom", "lomb_circom", "zkvm"}
    release.set()
    result = await task

    assert result["status"] == "completed"
    assert set(result["proofs"]) == {"python_circom", "lomb_scargle_circom", "zkvm"}
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"]["status"] == "completed"
    assert result["disabled_methods"] == [
        "wavelet",
        "music",
        "fft_cosine_similarity",
    ]
    assert "certificate_input" not in result["analysis"]
    assert "zkvm_input" not in result["analysis"]
    assert result["analysis"]["algorithm_comparison"]["absolute_difference_bpm"] == pytest.approx(0.1)
    assert "certificate_input" not in result["analysis"]["lomb_scargle"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_passes_existing_pipeline_pca_output_to_lomb_scargle(monkeypatch):
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_ENABLED", False)
    shared_input = {"principal_components": object(), "timestamps_ns": object()}
    observed = {}

    def pipeline_runner(file_path, include_zkvm_input=True, include_lomb_scargle_input=False):
        observed["pipeline_options"] = (include_zkvm_input, include_lomb_scargle_input)
        return {
            **PIPELINE_RESULT,
            "zkvm_input": None,
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

    assert observed["pipeline_options"] == (False, True)
    assert observed["lomb_input"] is shared_input
    assert "_lomb_scargle_input" not in result["analysis"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preserves_circom_result_when_zkvm_fails(monkeypatch):
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_ENABLED", True)

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    class _BrokenZkVM:
        async def generate_proof(self, pipeline_input):
            raise RuntimeError("prover unavailable")

    service = VerifiableBreathingService(
        pipeline_runner=lambda _: PIPELINE_RESULT,
        circom_service_factory=_WorkingCircom,
        lomb_scargle_runner=lambda _: LOMB_RESULT,
        lomb_circom_service_factory=_LombCircomService,
        zkvm_service=_BrokenZkVM(),
    )

    result = await service.analyze("sample.csi")

    assert result["status"] == "partial"
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"] == {
        "status": "failed",
        "error": "prover unavailable",
        "error_type": "RuntimeError",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_large_file_skips_zkvm_input_and_keeps_circom_result(monkeypatch, tmp_path):
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    csi_file = tmp_path / "large.csi"
    csi_file.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_ENABLED", True)
    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_MAX_FILE_SIZE_MB", 1)

    def pipeline_runner(file_path, include_zkvm_input=True):
        assert file_path == str(csi_file)
        assert include_zkvm_input is False
        return {**PIPELINE_RESULT, "zkvm_input": None}

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    class _ForbiddenZkVM:
        async def generate_proof(self, pipeline_input):
            raise AssertionError("zkVM must not run for a file above the safety limit")

    service = VerifiableBreathingService(
        pipeline_runner=pipeline_runner,
        circom_service_factory=_WorkingCircom,
        lomb_scargle_runner=lambda _: LOMB_RESULT,
        lomb_circom_service_factory=_LombCircomService,
        zkvm_service=_ForbiddenZkVM(),
    )

    result = await service.analyze(str(csi_file))

    assert result["status"] == "partial"
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"] == {
        "status": "skipped",
        "reason": "file_too_large",
        "file_size": 1024 * 1024 + 1,
        "threshold_mb": 1,
    }
    assert "input_commitment" not in result["analysis"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zkvm_is_disabled_by_default_without_building_its_input(monkeypatch, tmp_path):
    from app.services.verifiable_breathing_service import VerifiableBreathingService

    csi_file = tmp_path / "sample.csi"
    csi_file.write_bytes(b"csi")
    monkeypatch.setattr("app.services.verifiable_breathing_service.settings.CSI_ZKVM_ENABLED", False)

    def pipeline_runner(file_path, include_zkvm_input=True):
        assert include_zkvm_input is False
        return {**PIPELINE_RESULT, "zkvm_input": None}

    class _WorkingCircom:
        async def generate_proof(self, **kwargs):
            return {"isNormal": True, "isValid": True, "method": "breathing_certificate"}

    class _ForbiddenZkVM:
        async def generate_proof(self, pipeline_input):
            raise AssertionError("disabled zkVM must not be invoked")

    service = VerifiableBreathingService(
        pipeline_runner=pipeline_runner,
        circom_service_factory=_WorkingCircom,
        lomb_scargle_runner=lambda _: LOMB_RESULT,
        lomb_circom_service_factory=_LombCircomService,
        zkvm_service=_ForbiddenZkVM(),
    )

    result = await service.analyze(str(csi_file))

    assert result["status"] == "completed"
    assert result["proofs"]["python_circom"]["status"] == "completed"
    assert result["proofs"]["lomb_scargle_circom"]["status"] == "completed"
    assert result["proofs"]["zkvm"] == {
        "status": "disabled",
        "reason": "disabled_by_configuration",
    }
