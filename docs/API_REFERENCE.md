# API リファレンス

**バージョン**: 2.5.0
**ベースURL**: `http://localhost:8000`
**APIプレフィックス**: `/api/v2`
**認証方式**: JWT Bearer Token

---

## 📋 目次

1. [認証API](#認証api)
2. [デバイス管理API](#デバイス管理api)
3. [CSIデータAPI](#csiデータapi)
4. [ブロックチェーンAPI](#ブロックチェーンapi)
5. [ヘルスチェックAPI](#ヘルスチェックapi)
6. [エラーレスポンス](#エラーレスポンス)

---

## 認証API

### ユーザー登録

新規ユーザーアカウントを作成します。

**エンドポイント**: `POST /api/v2/auth/register`

**リクエストボディ**:
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "full_name": "string"
}
```

**レスポンス**: `201 Created`
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "id": "uuid",
  "role": "user",
  "is_active": true,
  "created_at": "2025-10-14T00:00:00Z",
  "last_login_at": null
}
```

---

### ログイン

ユーザー認証を行い、JWTトークンを取得します。

**エンドポイント**: `POST /api/v2/auth/login`

**リクエストボディ**:
```json
{
  "username": "string",
  "password": "string"
}
```

**レスポンス**: `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "username": "testuser",
    "email": "test@example.com",
    "id": "uuid",
    "role": "user",
    "is_active": true,
    "created_at": "2025-10-14T00:00:00Z",
    "last_login_at": "2025-10-14T01:00:00Z"
  }
}
```

---

### 現在のユーザー情報取得

認証済みユーザーの情報を取得します。

**エンドポイント**: `GET /api/v2/auth/me`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**レスポンス**: `200 OK`
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "id": "uuid",
  "role": "user",
  "is_active": true,
  "created_at": "2025-10-14T00:00:00Z",
  "last_login_at": "2025-10-14T01:00:00Z"
}
```

---

## デバイス管理API

### デバイス登録

新規デバイスを登録します。

**エンドポイント**: `POST /api/v2/devices/register`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**リクエストボディ**:
```json
{
  "device_id": "string",
  "device_name": "string",
  "device_type": "esp32",
  "location": "string",
  "description": "string"
}
```

**レスポンス**: `201 Created`
```json
{
  "device_name": "Test Device 001",
  "device_type": "esp32",
  "location": "Test Lab",
  "id": "uuid",
  "device_id": "test_device_001",
  "owner_id": "uuid",
  "is_active": true,
  "last_seen": "2025-10-14T01:47:42Z",
  "created_at": "2025-10-14T01:47:42Z",
  "updated_at": "2025-10-14T01:47:42Z",
  "status": "online",
  "connection_status": "online"
}
```

---

### デバイス一覧取得

登録されているデバイスの一覧を取得します。

**エンドポイント**: `GET /api/v2/devices/`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**クエリパラメータ**:
- `page` (int, optional): ページ番号（デフォルト: 1）
- `page_size` (int, optional): 1ページあたりの件数（デフォルト: 20）

**レスポンス**: `200 OK`
```json
{
  "devices": [
    {
      "device_name": "Test Device 001",
      "device_type": "esp32",
      "location": "Test Lab",
      "id": "uuid",
      "device_id": "test_device_001",
      "owner_id": "uuid",
      "is_active": true,
      "last_seen": "2025-10-14T01:47:42Z",
      "created_at": "2025-10-14T01:47:42Z",
      "updated_at": "2025-10-14T01:47:42Z",
      "status": "online",
      "connection_status": "online"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### デバイス統計情報取得

デバイスの統計情報を取得します。

**エンドポイント**: `GET /api/v2/devices/statistics/summary`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**レスポンス**: `200 OK`
```json
{
  "total_devices": 1,
  "online_devices": 0,
  "offline_devices": 1,
  "error_devices": 0,
  "by_type": {
    "esp32": 1
  },
  "by_location": {
    "Test Lab": 1
  },
  "last_updated": "2025-10-14T02:06:24Z",
  "recent_activity": []
}
```

---

## CSIデータAPI

### CSIデータ一覧取得

CSIデータの一覧を取得します。

**エンドポイント**: `GET /api/v2/csi-data/`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**クエリパラメータ**:
- `page` (int, optional): ページ番号（デフォルト: 1）
- `page_size` (int, optional): 1ページあたりの件数（デフォルト: 20）
- `device_id` (string, optional): デバイスIDでフィルタ

**レスポンス**: `200 OK`
```json
{
  "csi_data": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### CSIデータアップロード

新しいCSIデータをアップロードします。

**⚠️ 注意**: このエンドポイントは研究用エッジデバイス専用です。Webインターフェースからの手動アップロードは不可。

**エンドポイント**: `POST /api/v2/csi-data/upload`

**リクエストヘッダー**:
```
Authorization: Bearer <device_token>
Content-Type: multipart/form-data
```

**リクエストボディ** (multipart/form-data):
- `device_id` (string, required): デバイスID
- `file` (file, required): CSIデータファイル（.pcap, .pcapng）

**レスポンス**: `201 Created`
```json
{
  "id": "uuid",
  "device_id": "test_device_001",
  "file_path": "/uploads/...",
  "file_size": 1024,
  "ipfs_hash": "QmXXXXXXX...",
  "blockchain_tx_hash": "0xXXXXXXXX...",
  "blockchain_status": "pending",
  "status": "received",
  "created_at": "2025-10-14T01:50:00Z"
}
```

---

## ブロックチェーンAPI

### コントラクト情報取得

デプロイされたスマートコントラクトの情報を取得します。

**エンドポイント**: `GET /api/v2/blockchain/contract-info`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**レスポンス**: `200 OK`
```json
{
  "enabled": true,
  "connected": true,
  "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
  "owner": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
  "total_records": 0,
  "current_block": 1,
  "chain_id": 1337
}
```

---

### トランザクション状態確認

ブロックチェーントランザクションの状態を確認します。

**エンドポイント**: `GET /api/v2/blockchain/transaction/{tx_hash}`

**リクエストヘッダー**:
```
Authorization: Bearer <access_token>
```

**パスパラメータ**:
- `tx_hash` (string, required): トランザクションハッシュ

**レスポンス**: `200 OK`
```json
{
  "status": "confirmed",
  "block_number": 2,
  "confirmations": 5,
  "gas_used": 123456,
  "tx_hash": "0xXXXXXXXX..."
}
```

---

## ヘルスチェックAPI

### システムヘルスチェック

システムの健全性を確認します。

**エンドポイント**: `GET /health`

**レスポンス**: `200 OK`
```json
{
  "status": "healthy",
  "service": "CSI Respiratory Monitoring System",
  "version": "2.5.0"
}
```

---

## エラーレスポンス

APIはエラー時に以下の形式でレスポンスを返します。

### 認証エラー

**ステータスコード**: `401 Unauthorized`

```json
{
  "detail": "Not authenticated"
}
```

### バリデーションエラー

**ステータスコード**: `422 Unprocessable Entity`

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "username"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

### 内部サーバーエラー

**ステータスコード**: `500 Internal Server Error`

```json
{
  "detail": "内部サーバーエラーが発生しました"
}
```

---

## レート制限

APIには以下のレート制限が適用されます：

- **ログイン**: 5回/分
- **一般API**: 100回/分
- **アップロード**: 10回/分

制限を超えた場合、`429 Too Many Requests`が返されます。

---

## 認証フロー

1. **ユーザー登録** または既存アカウントでログイン
2. **ログインAPI**でアクセストークンを取得
3. 以降のAPIリクエストで`Authorization: Bearer <token>`ヘッダーを付与
4. トークンの有効期限は24時間（86400秒）

---

## Swagger UI

インタラクティブなAPI仕様は以下のURLで確認できます：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

**最終更新**: 2025-10-14
**APIバージョン**: 2.5.0
**ドキュメントバージョン**: 1.0.0
