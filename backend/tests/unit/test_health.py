"""
ヘルスチェックエンドポイントのテスト
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_health_check(client: TestClient):
    """ヘルスチェックエンドポイントが正常に動作することを確認"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.unit
def test_root_endpoint(client: TestClient):
    """ルートエンドポイントが正常に動作することを確認"""
    response = client.get("/")
    assert response.status_code == 200
