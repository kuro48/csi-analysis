"""
呼吸解析エンドポイント（POST /api/v2/breathing/analyze）の単体テスト
"""
import io

import pytest
from fastapi.testclient import TestClient

WAVEFORM = [0.1, -0.2, 0.3, -0.1, 0.05]


def _upload(client: TestClient, filename: str, content: bytes = b"dummy-csi-bytes"):
    return client.post(
        "/api/v2/breathing/analyze",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
    )


@pytest.mark.unit
def test_analyze_returns_waveform_array_only(client: TestClient, monkeypatch):
    """解析成功時、呼吸波形の配列だけがそのまま返ること"""
    monkeypatch.setattr(
        "app.api.endpoints.breathing.run_breathing_pipeline",
        lambda path: {"respiration_waveform": WAVEFORM, "breathing_rate_bpm": 15.0},
    )

    response = _upload(client, "sample.csi")

    assert response.status_code == 200
    assert response.json() == WAVEFORM


@pytest.mark.unit
def test_analyze_rejects_unsupported_extension(client: TestClient):
    response = _upload(client, "sample.txt")

    assert response.status_code == 400


@pytest.mark.unit
def test_analyze_rejects_empty_file(client: TestClient):
    response = _upload(client, "sample.csi", content=b"")

    assert response.status_code == 400


@pytest.mark.unit
def test_analyze_maps_value_error_to_400(client: TestClient, monkeypatch):
    """CSIが読めない等の入力起因エラーは 400 になること"""
    def _raise(path):
        raise ValueError("CSIデータが見つかりません。")

    monkeypatch.setattr("app.api.endpoints.breathing.run_breathing_pipeline", _raise)

    response = _upload(client, "sample.csi")

    assert response.status_code == 400
    assert "CSIデータ" in response.json()["detail"]


@pytest.mark.unit
def test_analyze_maps_missing_dependency_to_503(client: TestClient, monkeypatch):
    """解析ライブラリ未導入（RuntimeError）は 503 になること"""
    def _raise(path):
        raise RuntimeError("必要なパッケージが未インストールです")

    monkeypatch.setattr("app.api.endpoints.breathing.run_breathing_pipeline", _raise)

    response = _upload(client, "sample.csi")

    assert response.status_code == 503
