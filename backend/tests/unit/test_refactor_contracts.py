"""
Second-pass refactor contract tests.
"""

import json
import uuid
from datetime import datetime, timezone

import anyio
import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.endpoints import csi_data as csi_endpoint
from app.models.csi_data import CSIData
from app.services.file_validation import validate_csi_upload


class _Chunk:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.unit
def test_ground_truth_bpm_can_be_added_after_analysis_and_removed(client, db):
    record = CSIData(
        status="completed",
        processed_data={
            "status": "completed",
            "analysis": {
                "breathing_rate_bpm": 15.5,
                "lomb_scargle": {"breathing_rate_bpm": 14.75},
            },
            "proofs": {"zkvm": {"status": "disabled"}},
        },
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    response = client.patch(
        f"/api/v2/csi-data/{record.id}/ground-truth",
        json={"ground_truth_bpm": 15.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ground_truth_bpm"] == 15.0
    assert body["processed_data"]["bpm_evaluation"]["rows"][0]["absolute_error_bpm"] == 0.5
    db.refresh(record)
    assert record.ground_truth_bpm == 15.0

    cleared = client.patch(
        f"/api/v2/csi-data/{record.id}/ground-truth",
        json={"ground_truth_bpm": None},
    )

    assert cleared.status_code == 200
    assert cleared.json()["ground_truth_bpm"] is None
    assert "bpm_evaluation" not in cleared.json()["processed_data"]


@pytest.mark.unit
def test_ground_truth_bpm_update_validates_range(client, db):
    record = CSIData(status="uploaded")
    db.add(record)
    db.commit()

    response = client.patch(
        f"/api/v2/csi-data/{record.id}/ground-truth",
        json={"ground_truth_bpm": 121},
    )

    assert response.status_code == 422


@pytest.mark.unit
def test_chunk_upload_schedules_shared_csi_processing_pipeline(monkeypatch, tmp_path):
    csi_id = uuid.uuid4()

    class UploadedCSI:
        id = csi_id
        file_path = "/tmp/uploaded.pcap"
        status = "uploaded"
        file_size = 4
        created_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
        updated_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
        session_id = "session-1"
        device_id = None
        processed_data = None

    async def fake_upload_csi_data(db, source_path, upload_info):
        assert source_path.read_bytes() == b"pcap"
        assert upload_info.file_name == "sample.pcap"
        assert upload_info.session_id == "session-1"
        return UploadedCSI()

    monkeypatch.setattr(csi_endpoint, "_CHUNK_TMP_DIR", tmp_path)
    monkeypatch.setattr(csi_endpoint.CSIDataService, "upload_csi_data_from_path", fake_upload_csi_data)

    background_tasks = BackgroundTasks()

    async def run_upload():
        return await csi_endpoint.upload_csi_data_chunk(
            background_tasks=background_tasks,
            chunk=_Chunk(b"pcap"),
            upload_id="upload-1",
            chunk_index=0,
            total_chunks=1,
            filename="sample.pcap",
            session_id="session-1",
            metadata=None,
            db=object(),
        )

    response = anyio.run(run_upload)

    assert json.loads(response.body)["csi_data"]["id"] == str(csi_id)
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is csi_endpoint.process_csi_in_background
    assert task.kwargs["csi_data_id"] == csi_id
    assert task.kwargs["file_path"] == "/tmp/uploaded.pcap"


@pytest.mark.unit
def test_chunk_header_validation_accepts_size_unknown_csi_file(monkeypatch):
    monkeypatch.setattr("app.services.file_validation.settings.PICOSCENES_ENABLED", True)

    assert validate_csi_upload("sample.csi", None) == ".csi"


@pytest.mark.unit
def test_chunk_upload_allows_large_csi_when_limit_is_unlimited(monkeypatch, tmp_path):
    csi_id = uuid.uuid4()

    class UploadedCSI:
        id = csi_id
        file_path = "/tmp/large.csi"
        status = "uploaded"
        file_size = 1_400_000
        created_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
        updated_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
        session_id = None
        device_id = None
        processed_data = None

    monkeypatch.setattr(csi_endpoint, "_CHUNK_TMP_DIR", tmp_path)
    monkeypatch.setattr("app.services.file_validation.settings.PICOSCENES_ENABLED", True)
    monkeypatch.setattr("app.services.file_validation.settings.PICOSCENES_MAX_FILE_SIZE_MB", 0)

    async def fake_upload_csi_data(db, source_path, upload_info):
        assert source_path.read_bytes() == b"a" * 700_000 + b"b" * 700_000
        assert upload_info.file_name == "sample.csi"
        return UploadedCSI()

    monkeypatch.setattr(csi_endpoint.CSIDataService, "upload_csi_data_from_path", fake_upload_csi_data)
    background_tasks = BackgroundTasks()

    async def run_uploads():
        await csi_endpoint.upload_csi_data_chunk(
            background_tasks=background_tasks,
            chunk=_Chunk(b"a" * 700_000),
            upload_id="upload-too-large",
            chunk_index=0,
            total_chunks=2,
            filename="sample.csi",
            session_id=None,
            metadata=None,
            db=object(),
        )
        return await csi_endpoint.upload_csi_data_chunk(
            background_tasks=background_tasks,
            chunk=_Chunk(b"b" * 700_000),
            upload_id="upload-too-large",
            chunk_index=1,
            total_chunks=2,
            filename="sample.csi",
            session_id=None,
            metadata=None,
            db=object(),
        )

    response = anyio.run(run_uploads)

    assert json.loads(response.body)["csi_data"]["id"] == str(csi_id)
    assert not (tmp_path / "upload-too-large").exists()
    assert len(background_tasks.tasks) == 1


@pytest.mark.unit
def test_chunk_header_validation_keeps_unsupported_extension_error():
    with pytest.raises(HTTPException) as exc_info:
        validate_csi_upload("sample.txt", None)

    assert exc_info.value.status_code == 400
    assert "未対応のファイル形式です" in exc_info.value.detail


@pytest.mark.unit
def test_visualization_endpoint_is_removed():
    paths = {route.path for route in csi_endpoint.router.routes}

    assert "/{csi_data_id}/visualization" not in paths


@pytest.mark.unit
def test_csi_endpoint_no_longer_defines_duplicate_pipeline_helpers():
    removed_helpers = {
        "_process_and_generate_zkp_background",
        "_run_base_csi_comparison",
        "_generate_transform_zkp_proofs",
        "_record_zkp_proof_on_chain",
        "_serialize_fft_dataframe",
        "_parse_json_field",
    }

    assert not [name for name in removed_helpers if hasattr(csi_endpoint, name)]


@pytest.mark.unit
def test_dead_user_and_session_exports_are_removed():
    import app.models as models
    import app.schemas as schemas

    assert not hasattr(models, "User")
    assert not hasattr(models, "Session")
    assert "User" not in models.__all__
    assert "Session" not in models.__all__

    for name in {"UserCreate", "UserLogin", "UserResponse", "UserUpdate"}:
        assert not hasattr(schemas, name)
        assert name not in schemas.__all__
