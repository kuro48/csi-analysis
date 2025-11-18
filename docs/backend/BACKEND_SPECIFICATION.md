# CSI Web Platform - バックエンド仕様書

## 概要
Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムのバックエンドAPI仕様です。

**技術スタック**: FastAPI + Python 3.11
**データベース**: PostgreSQL 15
**キャッシュ**: Redis 7
**認証**: JWT Bearer Token
**APIバージョン**: v2.5.0

---

## 🏗️ アーキテクチャ

### システム構成
```
backend/
├── app/
│   ├── main.py                 # FastAPIアプリケーションエントリーポイント
│   ├── core/                   # 核となる設定・共通機能
│   │   ├── config.py          # 環境設定管理
│   │   ├── database.py        # データベース接続
│   │   └── deps.py            # 依存関係注入
│   ├── api/                    # APIエンドポイント
│   │   ├── routes.py          # ルーター統合
│   │   └── endpoints/         # 各機能のエンドポイント
│   │       ├── auth.py        # 認証関連
│   │       ├── users.py       # ユーザー管理
│   │       ├── devices.py     # デバイス管理
│   │       ├── csi_data.py    # CSIデータ管理
│   │       ├── breathing_analysis.py  # 呼吸解析
│   │       ├── websocket.py   # WebSocket通信
│   │       ├── ipfs.py        # IPFS連携
│   │       └── health.py      # ヘルスチェック
│   ├── models/                 # SQLAlchemyモデル
│   │   ├── base.py            # ベースモデル
│   │   ├── user.py            # ユーザーモデル
│   │   ├── device.py          # デバイスモデル
│   │   ├── csi_data.py        # CSIデータモデル
│   │   └── breathing_analysis.py  # 呼吸解析モデル
│   ├── schemas/                # Pydanticスキーマ
│   │   ├── auth.py            # 認証スキーマ
│   │   ├── user.py            # ユーザースキーマ
│   │   ├── device.py          # デバイススキーマ
│   │   ├── csi_data.py        # CSIデータスキーマ
│   │   └── breathing_analysis.py  # 呼吸解析スキーマ
│   └── services/               # ビジネスロジック
│       ├── auth.py            # 認証サービス
│       ├── device.py          # デバイス管理サービス
│       ├── csi_data.py        # CSIデータ管理サービス
│       ├── breathing_analysis.py  # 呼吸解析サービス
│       ├── websocket.py       # WebSocket管理サービス
│       ├── ipfs.py            # IPFS統合サービス
│       └── cache.py           # キャッシュ管理サービス
└── requirements.txt            # Python依存関係
```

### データフロー
```
エッジデバイス → FastAPI → PostgreSQL → Redis → WebSocket → フロントエンド
                     ↓
                   IPFS（分散ストレージ）
```

---

## 🔧 環境設定

### 主要設定ファイル
- **環境変数**: `backend/.env`
- **Docker設定**: `backend/Dockerfile`
- **依存関係**: `backend/requirements.txt`

### 重要な環境変数

#### アプリケーション基本設定
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `PROJECT_NAME` | CSI Respiratory Monitoring System | プロジェクト名 |
| `VERSION` | 2.5.0 | APIバージョン |
| `API_V2_PREFIX` | /api/v2 | APIベースパス |
| `DEBUG` | true | デバッグモード |

#### データベース設定
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `DATABASE_URL` | postgresql://csi_user:csi_password@localhost:5432/csi_system | PostgreSQL接続URL |
| `DATABASE_HOST` | localhost | データベースホスト |
| `DATABASE_PORT` | 5432 | データベースポート |
| `DATABASE_USER` | csi_user | データベースユーザー |
| `DATABASE_PASSWORD` | csi_password | データベースパスワード |
| `DATABASE_NAME` | csi_system | データベース名 |

#### Redis設定
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `REDIS_URL` | redis://localhost:6379/0 | Redis接続URL |
| `REDIS_HOST` | localhost | Redisホスト |
| `REDIS_PORT` | 6379 | Redisポート |
| `REDIS_DB` | 0 | Redisデータベース番号 |

#### JWT認証設定
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `JWT_SECRET_KEY` | your-super-secret-jwt-key-change-in-production | JWT暗号化キー |
| `JWT_ALGORITHM` | HS256 | JWT暗号化アルゴリズム |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | トークン有効期限（分） |

#### IPFS設定
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `IPFS_HOST` | localhost | IPFSホスト |
| `IPFS_PORT` | 5001 | IPFS APIポート |
| `IPFS_GATEWAY_PORT` | 8080 | IPFSゲートウェイポート |

#### セキュリティ・レート制限
| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `RATE_LIMIT_LOGIN` | 5/minute | ログイン試行制限 |
| `RATE_LIMIT_API` | 100/minute | 一般API呼び出し制限 |
| `RATE_LIMIT_UPLOAD` | 10/minute | ファイルアップロード制限 |

---

## 📊 データベーススキーマ

### 主要テーブル

#### users テーブル
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE
);
```

#### devices テーブル
```sql
CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(255) UNIQUE NOT NULL,
    device_name VARCHAR(255) NOT NULL,
    device_type VARCHAR(100) NOT NULL,
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    location VARCHAR(255),
    status VARCHAR(50) DEFAULT 'offline',
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat TIMESTAMP WITH TIME ZONE
);
```

#### csi_data テーブル
```sql
CREATE TABLE csi_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    session_id VARCHAR(255),
    raw_data JSONB,
    processed_data JSONB,
    file_path VARCHAR(500),
    file_size BIGINT,
    ipfs_hash VARCHAR(255),  -- IPFS統合用
    status VARCHAR(50) DEFAULT 'received',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### breathing_analyses テーブル
```sql
CREATE TABLE breathing_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    csi_data_id UUID REFERENCES csi_data(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    breathing_rate FLOAT,
    breathing_pattern JSONB,
    analysis_result JSONB,
    confidence_score FLOAT,
    ipfs_hash VARCHAR(255),  -- IPFS統合用
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### sessions テーブル
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    session_name VARCHAR(255),
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration INTEGER,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### インデックス戦略
```sql
-- 高頻度クエリ用インデックス
CREATE INDEX idx_csi_device_created ON csi_data(device_id, created_at);
CREATE INDEX idx_csi_device_status ON csi_data(device_id, status);
CREATE INDEX idx_csi_session_created ON csi_data(session_id, created_at);
CREATE INDEX idx_devices_owner_status ON devices(owner_id, status);
CREATE INDEX idx_breathing_device_created ON breathing_analyses(device_id, created_at);
```

---

## 🔐 認証・認可システム

### JWT認証フロー
```
1. POST /api/v2/auth/login
   ├── ユーザー名・パスワード検証
   ├── JWTトークン生成（24時間有効）
   └── レスポンス: access_token, token_type, expires_in, user

2. 保護されたエンドポイントアクセス
   ├── Authorization: Bearer <token>
   ├── JWTトークン検証
   └── ユーザー情報抽出
```

### ユーザーロール
| ロール | 権限 | 説明 |
|--------|------|------|
| `superuser` | 全権限 | システム管理者 |
| `admin` | 管理権限 | 組織管理者 |
| `user` | 一般権限 | 一般ユーザー |
| `readonly` | 読み取り専用 | 閲覧のみ |

### 認可の実装
```python
# 現在ユーザー取得
def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # JWTデコード・ユーザー検証

# 管理者権限必須
def get_admin_user(user: User = Depends(get_current_user)) -> User:
    # 管理者権限チェック

# デバイス所有者チェック
def check_device_ownership(device_id: str, user: User) -> bool:
    # デバイス所有権確認
```

---

## 🌐 APIエンドポイント詳細

### 認証関連 (`/api/v2/auth`)

#### POST /api/v2/auth/login
**機能**: ユーザーログイン
```json
// リクエスト
{
    "username": "admin",
    "password": "admin123"
}

// レスポンス
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
        "id": "uuid",
        "username": "admin",
        "email": "admin@example.com",
        "role": "superuser"
    }
}
```

#### POST /api/v2/auth/register
**機能**: ユーザー登録
```json
// リクエスト
{
    "username": "newuser",
    "email": "user@example.com",
    "password": "password123"
}
```

### デバイス管理 (`/api/v2/devices`)

#### POST /api/v2/devices/
**機能**: デバイス登録
```json
// リクエスト
{
    "device_id": "raspberry_pi_001",
    "device_name": "RaspberryPi Lab Room",
    "device_type": "raspberry_pi",
    "location": "lab_room_1",
    "metadata": {
        "channel_width": "80MHz",
        "antenna_count": 2
    }
}
```

#### GET /api/v2/devices/
**機能**: デバイス一覧取得
```
クエリパラメータ:
- status: offline|online|error|all (デフォルト: all)
- device_type: raspberry_pi|esp32|all (デフォルト: all)
- location: 場所フィルター
- search: 検索キーワード
- page: ページ番号 (デフォルト: 1)
- page_size: 1ページあたりの件数 (デフォルト: 20)
```

### CSIデータ管理 (`/api/v2/csi-data`)

#### POST /api/v2/csi-data/upload
**機能**: CSIデータアップロード（エッジデバイス用）
```
multipart/form-data:
- device_id: string (必須)
- file: binary (必須) - pcap/csv形式
- session_id: string (オプション)
- collection_start_time: datetime (オプション)
- collection_duration: float (オプション)
- metadata: JSON string (オプション)
```

**処理フロー**:
1. デバイス所有権確認
2. ファイル保存（ローカル + IPFS）
3. データベース記録
4. WebSocket通知
5. 非同期解析処理キュー

#### GET /api/v2/csi-data/
**機能**: CSIデータ一覧取得
```
クエリパラメータ:
- device_id: デバイスIDフィルター
- session_id: セッションIDフィルター
- status: received|processing|completed|error|all
- start_date: 開始日時 (ISO format)
- end_date: 終了日時 (ISO format)
- page: ページ番号
- page_size: 1ページあたりの件数
```

### IPFS連携 (`/api/v2/ipfs`)

#### GET /api/v2/ipfs/status
**機能**: IPFS接続状態確認
```json
// レスポンス
{
    "status": "connected|disconnected|error",
    "ipfs_node": "ipfs_connection_url",
    "connected": true
}
```

#### POST /api/v2/ipfs/upload
**機能**: ファイルを直接IPFSにアップロード
```
multipart/form-data:
- file: binary (必須)
```

#### GET /api/v2/ipfs/download/{ipfs_hash}
**機能**: IPFSからファイルダウンロード

#### POST /api/v2/ipfs/pin/{ipfs_hash}
**機能**: IPFSファイルピン留め（永続保存）

### WebSocket (`/api/v2/ws`)

#### 接続エンドポイント
```
ws://localhost:8000/api/v2/ws?token=JWT_TOKEN
```

#### メッセージ形式
```json
// デバイス状態更新
{
    "type": "device_status_update",
    "device_id": "raspberry_pi_001",
    "status": "online",
    "timestamp": "2024-09-30T12:00:00Z"
}

// CSIデータアップロード完了
{
    "type": "csi_data_uploaded",
    "device_id": "raspberry_pi_001",
    "csi_data_id": "uuid",
    "file_name": "data.pcap",
    "file_size": 161044,
    "ipfs_hash": "QmHash..."
}

// 呼吸解析完了
{
    "type": "breathing_analysis_completed",
    "device_id": "raspberry_pi_001",
    "analysis_id": "uuid",
    "breathing_rate": 18.5,
    "confidence_score": 0.95
}
```

---

## 🔄 サービス層詳細

### CSIDataService
**機能**: CSIデータの管理・処理

#### 主要メソッド
```python
async def upload_csi_data(
    db: Session,
    device_id: str,
    file_data: bytes,
    upload_info: CSIDataUpload,
    user_id: UUID
) -> CSIData:
    """CSIデータアップロード処理"""
    # 1. デバイス所有権確認
    # 2. ファイル保存（ローカル）
    # 3. IPFS アップロード
    # 4. データベース記録
    # 5. WebSocket通知

def get_csi_data_list(
    db: Session,
    user_id: UUID,
    filters: CSIDataFilter,
    page: int,
    page_size: int
) -> Tuple[List[CSIData], int]:
    """CSIデータ一覧取得（ページネーション付き）"""

async def delete_csi_data(
    db: Session,
    csi_data_id: UUID,
    user_id: UUID
) -> bool:
    """CSIデータ削除（ローカル + IPFS）"""
```

### IPFSService
**機能**: IPFS分散ストレージとの統合

#### 主要メソッド
```python
async def upload_file(self, file_data: bytes, filename: str = None) -> str:
    """ファイルをIPFSにアップロード"""

async def get_file(self, ipfs_hash: str) -> bytes:
    """IPFSからファイル取得"""

async def pin_file(self, ipfs_hash: str) -> bool:
    """ファイルをピン留め（永続保存）"""

async def unpin_file(self, ipfs_hash: str) -> bool:
    """ピン留め解除"""

async def is_connected(self) -> bool:
    """IPFS接続状態確認"""
```

### RealtimeDataService
**機能**: WebSocketによるリアルタイム通信

#### 主要メソッド
```python
async def send_device_status_update(device_id: str, data: Dict):
    """デバイス状態更新を配信"""

async def send_csi_data_notification(device_id: str, data: Dict):
    """CSIデータ関連通知を配信"""

async def broadcast_system_message(message: Dict):
    """システム全体へのブロードキャスト"""
```

### CacheService
**機能**: Redisキャッシュ管理

#### キャッシュ戦略
```python
# キャッシュTTL設定
CACHE_DEFAULT_TTL = 300      # 5分
CACHE_DEVICE_TTL = 600       # 10分
CACHE_ANALYSIS_TTL = 120     # 2分
CACHE_SESSION_TTL = 1800     # 30分

# キーパターン
device:{device_id}           # デバイス情報
csi_data:{data_id}          # CSIデータ
analysis:{analysis_id}       # 解析結果
user_devices:{user_id}       # ユーザーデバイス一覧
```

---

## 📈 パフォーマンス・監視

### ログレベル設定
```
DEBUG: 開発用詳細ログ
INFO: 一般的な動作ログ
WARNING: 警告（IPFS接続失敗等）
ERROR: エラー（認証失敗、データベース接続エラー等）
```

### メトリクス
- **API レスポンス時間**: 95%ile < 500ms
- **データベース接続プール**: 最大20接続
- **Redis接続プール**: 最大10接続
- **ファイルアップロード**: 最大100MB
- **WebSocket接続**: 最大1000同時接続

### ヘルスチェック
```
GET /health                     # 基本ヘルスチェック
GET /api/v2/health/detailed     # 詳細ヘルスチェック
    ├── データベース接続確認
    ├── Redis接続確認
    ├── IPFS接続確認
    └── ディスク容量確認
```

---

## 🔒 セキュリティ仕様

### 入力検証
- **SQLインジェクション**: SQLAlchemy ORM使用
- **XSS対策**: Pydanticスキーマ検証
- **CSRF対策**: SameSite Cookie設定
- **ファイルアップロード**: 拡張子・MIME型チェック

### レート制限
```python
# Slowapi使用（Redis バックエンド）
@limiter.limit("5/minute")    # ログイン
@limiter.limit("100/minute")  # 一般API
@limiter.limit("10/minute")   # アップロード
```

### CORS設定
```python
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]
```

---

## 🚀 デプロイ・運用

### Docker設定
```dockerfile
# マルチステージビルド
FROM python:3.11-slim as builder
# 依存関係インストール

FROM python:3.11-slim as runtime
# アプリケーション実行
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 環境別設定
- **開発環境**: DEBUG=true, ログレベル=DEBUG
- **ステージング環境**: DEBUG=false, ログレベル=INFO
- **本番環境**: DEBUG=false, ログレベル=WARNING

### 依存関係
```
主要ライブラリ:
- fastapi==0.109.0          # WebAPIフレームワーク
- uvicorn[standard]==0.25.0 # ASGIサーバー
- sqlalchemy==2.0.25        # ORM
- alembic==1.13.1          # データベースマイグレーション
- redis==5.0.1             # Redisクライアント
- ipfshttpclient==0.8.0a2  # IPFSクライアント
- pydantic==2.5.3          # データ検証
- python-jose[cryptography]==3.3.0  # JWT処理
```

---

## 📋 今後の拡張計画

### v2.6.0 予定機能
- [ ] Alembic マイグレーション統合
- [ ] IPFS フル統合（メタデータ含む）
- [ ] WebSocket認証強化
- [ ] バッチ解析処理キュー

### v3.0.0 予定機能
- [ ] GraphQL API統合
- [ ] マルチテナント対応
- [ ] リアルタイム機械学習推論
- [ ] Blockchain統合

---

**最終更新**: 2024年9月30日
**APIバージョン**: v2.5.0
**Python**: 3.11+
**FastAPI**: 0.109.0