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


# ---------------------------------------------------------------------------
# 証明書検証エンドポイント（POST /api/v2/breathing/analyze-certificate）
# ---------------------------------------------------------------------------
_PIPELINE_RESULT = {
    "respiration_waveform": WAVEFORM,
    "breathing_rate_bpm": 15.0,
    "peak_freq_hz": 0.25,
    "selected_vmd_mode": 1,
    "certificate_input": {
        "vmdInput": [1, 2, 3],
        "modes": [[1, 2, 3]] * 5,
        "sel": [1, 0, 0, 0, 0],
        "diagnostics": {"recon_error_ratio": 0.01, "narrow_ratio": 0.9},
    },
}


class _FakeCertificateService:
    async def generate_proof(self, vmd_input, modes, sel):
        return {
            "proof": {"pi_a": ["1", "2"]},
            "publicSignals": ["1"],
            "isNormal": True,
            "isValid": True,
            "method": "breathing_certificate",
        }


def _upload_certificate(client: TestClient, filename: str, content: bytes = b"dummy-csi-bytes"):
    return client.post(
        "/api/v2/breathing/analyze-certificate",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
    )


@pytest.mark.unit
def test_analyze_certificate_returns_proof_and_diagnostics(client: TestClient, monkeypatch):
    """成功時、ZKP証明・判定・診断メトリクスを返すこと"""
    monkeypatch.setattr(
        "app.api.endpoints.breathing.run_breathing_pipeline",
        lambda path: _PIPELINE_RESULT,
    )
    monkeypatch.setattr(
        "app.api.endpoints.breathing._get_certificate_service",
        lambda: _FakeCertificateService(),
    )

    response = _upload_certificate(client, "sample.csi")

    assert response.status_code == 200
    body = response.json()
    assert body["isNormal"] is True
    assert body["method"] == "breathing_certificate"
    assert body["publicSignals"] == ["1"]
    assert body["breathing_rate_bpm"] == 15.0
    assert body["diagnostics"]["recon_error_ratio"] == 0.01


@pytest.mark.unit
def test_analyze_certificate_rejects_unsupported_extension(client: TestClient):
    response = _upload_certificate(client, "sample.txt")
    assert response.status_code == 400


@pytest.mark.unit
def test_analyze_certificate_maps_missing_circuit_to_503(client: TestClient, monkeypatch):
    """回路未セットアップ（FileNotFoundError）は 503 になること"""
    monkeypatch.setattr(
        "app.api.endpoints.breathing.run_breathing_pipeline",
        lambda path: _PIPELINE_RESULT,
    )

    class _MissingCircuitService:
        async def generate_proof(self, vmd_input, modes, sel):
            raise FileNotFoundError("circuit files not found")

    monkeypatch.setattr(
        "app.api.endpoints.breathing._get_certificate_service",
        lambda: _MissingCircuitService(),
    )

    response = _upload_certificate(client, "sample.csi")
    assert response.status_code == 503


@pytest.mark.unit
def test_analyze_verifiable_returns_parallel_proof_results(client: TestClient, monkeypatch):
    class _Service:
        async def analyze(self, path):
            return {
                "status": "completed",
                "analysis": {"pipeline": "5-1.ipynb", "breathing_rate_bpm": 15.0},
                "proofs": {
                    "python_circom": {"status": "completed", "isNormal": True},
                    "zkvm": {"status": "completed", "isNormal": True},
                },
                "disabled_methods": ["wavelet", "music", "fft_cosine_similarity"],
            }

    monkeypatch.setattr(
        "app.api.endpoints.breathing._get_verifiable_service",
        lambda: _Service(),
    )
    response = client.post(
        "/api/v2/breathing/analyze-verifiable",
        files={"file": ("sample.csi", io.BytesIO(b"csi"), "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["pipeline"] == "5-1.ipynb"
    assert set(body["proofs"]) == {"python_circom", "zkvm"}
    assert "fft_cosine_similarity" in body["disabled_methods"]
