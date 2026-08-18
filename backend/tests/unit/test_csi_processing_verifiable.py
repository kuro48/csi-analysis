"""アップロード後の主解析が 5-1 並列証明だけを使うことを検証する。"""

import uuid

import pytest


class _Query:
    def __init__(self, record):
        self.record = record

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.record


class _DB:
    def __init__(self, record):
        self.record = record
        self.commits = 0
        self.closed = False

    def query(self, model):
        return _Query(self.record)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_background_processing_uses_only_5_1_parallel_proof_pipeline(monkeypatch):
    from app.services import csi_processing

    csi_id = uuid.uuid4()
    record = type(
        "Record",
        (),
        {
            "id": csi_id,
            "status": "uploaded",
            "processed_data": None,
            "file_path": "sample.csi",
            "ground_truth_bpm": 15.0,
        },
    )()
    db = _DB(record)
    expected = {
        "status": "completed",
        "analysis": {"pipeline": "5-1.ipynb", "breathing_rate_bpm": 15.0},
        "proofs": {
            "python_circom": {"status": "completed"},
            "zkvm": {"status": "completed"},
        },
        "disabled_methods": ["wavelet", "music", "fft_cosine_similarity"],
    }

    class _VerifiableService:
        async def analyze(self, file_path):
            assert file_path == "sample.csi"
            return expected

    class _ForbiddenLegacyAnalyzer:
        def __init__(self):
            raise AssertionError("legacy FFT/Wavelet/MUSIC analyzer must not be constructed")

    monkeypatch.setattr(csi_processing, "VerifiableBreathingService", _VerifiableService, raising=False)
    monkeypatch.setattr(csi_processing, "PCAPAnalyzer", _ForbiddenLegacyAnalyzer)
    monkeypatch.setattr(csi_processing.settings, "RESEARCH_MODE", True)

    await csi_processing.process_csi_in_background(
        csi_data_id=csi_id,
        file_path="sample.csi",
        db_session_maker=lambda: db,
    )

    assert record.status == "completed"
    assert record.processed_data == expected
    assert record.processed_data["bpm_evaluation"]["ground_truth_bpm"] == 15.0
    assert record.processed_data["bpm_evaluation"]["rows"][0]["measured_bpm"] == 15.0
    assert db.commits >= 2
    assert db.closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_background_processing_serializes_memory_heavy_jobs(monkeypatch):
    import asyncio

    from app.services import csi_processing

    active = 0
    max_active = 0

    class _VerifiableService:
        async def analyze(self, file_path):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {"status": "completed", "analysis": {}, "proofs": {}}

    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    first_record = type(
        "Record",
        (),
        {"id": first_id, "status": "uploaded", "processed_data": None, "file_path": "first.csi"},
    )()
    second_record = type(
        "Record",
        (),
        {"id": second_id, "status": "uploaded", "processed_data": None, "file_path": "second.csi"},
    )()
    first_db = _DB(first_record)
    second_db = _DB(second_record)

    monkeypatch.setattr(csi_processing, "_CSI_PROCESSING_SEMAPHORE", asyncio.Semaphore(1))
    monkeypatch.setattr(csi_processing, "VerifiableBreathingService", _VerifiableService)
    monkeypatch.setattr(csi_processing.settings, "RESEARCH_MODE", True)

    await asyncio.gather(
        csi_processing.process_csi_in_background(first_id, "first.csi", lambda: first_db),
        csi_processing.process_csi_in_background(second_id, "second.csi", lambda: second_db),
    )

    assert max_active == 1
    assert first_record.status == "completed"
    assert second_record.status == "completed"
