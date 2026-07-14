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
        {"id": csi_id, "status": "uploaded", "processed_data": None, "file_path": "sample.csi"},
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
    assert db.commits >= 2
    assert db.closed is True
