"""
認証エンドポイントのテスト
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestAuthRegister:
    """ユーザー登録のテスト"""

    def test_register_success(self, client: TestClient, test_user_data):
        """正常なユーザー登録"""
        response = client.post("/api/v2/auth/register", json=test_user_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["username"] == test_user_data["username"]
        assert data["email"] == test_user_data["email"]
        assert "password" not in data  # パスワードは返されない

    def test_register_duplicate_username(self, client: TestClient, test_user_data):
        """重複するユーザー名での登録は失敗"""
        # 1回目の登録
        response = client.post("/api/v2/auth/register", json=test_user_data)
        assert response.status_code == 200

        # 2回目の登録（同じユーザー名）
        response = client.post("/api/v2/auth/register", json=test_user_data)
        assert response.status_code == 400

    def test_register_invalid_email(self, client: TestClient, test_user_data):
        """無効なメールアドレスでの登録は失敗"""
        test_user_data["email"] = "invalid-email"
        response = client.post("/api/v2/auth/register", json=test_user_data)
        assert response.status_code == 422


@pytest.mark.unit
class TestAuthLogin:
    """ログインのテスト"""

    def test_login_success(self, client: TestClient, test_user_data):
        """正常なログイン"""
        # ユーザー登録
        client.post("/api/v2/auth/register", json=test_user_data)

        # ログイン
        login_data = {"username": test_user_data["username"], "password": test_user_data["password"]}
        response = client.post("/api/v2/auth/login", data=login_data)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, test_user_data):
        """間違ったパスワードでのログインは失敗"""
        # ユーザー登録
        client.post("/api/v2/auth/register", json=test_user_data)

        # 間違ったパスワードでログイン
        login_data = {"username": test_user_data["username"], "password": "wrongpassword"}
        response = client.post("/api/v2/auth/login", data=login_data)
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        """存在しないユーザーでのログインは失敗"""
        login_data = {"username": "nonexistent", "password": "somepassword"}
        response = client.post("/api/v2/auth/login", data=login_data)
        assert response.status_code == 401


@pytest.mark.unit
def test_get_current_user(authenticated_client: TestClient):
    """認証済みユーザー情報の取得"""
    response = authenticated_client.get("/api/v2/users/me")
    assert response.status_code == 200
    data = response.json()
    assert "username" in data
    assert "email" in data


@pytest.mark.unit
def test_get_current_user_unauthorized(client: TestClient):
    """未認証でのユーザー情報取得は失敗"""
    response = client.get("/api/v2/users/me")
    assert response.status_code == 401
