# CSI Web Platform - コード分析レポート

**作成日**: 2025-11-11
**プロジェクトバージョン**: v2.5.0
**分析範囲**: 全ドメイン（品質・セキュリティ・パフォーマンス・アーキテクチャ）

---

## 📊 エグゼクティブサマリー

### プロジェクト概要
- **Backend**: Python 3.13.3 + FastAPI (45ファイル)
- **Frontend**: React 19.1 + Next.js 15.5 + TypeScript (37ファイル)
- **アーキテクチャ**: マイクロサービス風のモノリシック構成
- **統合技術**: PostgreSQL, Redis, WebSocket, IPFS, Blockchain

### 総合評価スコア

| ドメイン | スコア | 重大度レベル | 状態 |
|---------|--------|------------|------|
| **セキュリティ** | 🔴 **4.5/10** | 🚨 CRITICAL | 要緊急対応 |
| **品質** | 🟡 **7.0/10** | ⚠️ MODERATE | 改善推奨 |
| **パフォーマンス** | 🟢 **8.5/10** | ✅ GOOD | 良好 |
| **アーキテクチャ** | 🟡 **7.5/10** | ⚠️ MODERATE | 改善推奨 |
| **総合スコア** | 🟡 **6.9/10** | ⚠️ MODERATE | **セキュリティ改善必須** |

---

## 🚨 CRITICAL: 緊急対応必須事項

### 🔴 セキュリティ重大問題（優先度：最高）

#### 1. **ハードコードされた機密情報**
**ファイル**: `backend/app/core/config.py`
**重大度**: 🔴 CRITICAL
**CVSS スコア**: 9.8 (Critical)

**問題点**:
```python
# Line 55-57: デフォルトJWT秘密鍵がハードコード
JWT_SECRET_KEY: str = os.getenv(
    "JWT_SECRET_KEY",
    "your-super-secret-jwt-key-change-in-production"  # ❌ 本番環境で危険
)

# Line 32-35: データベース認証情報がハードコード
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://csi_user:csi_password@localhost:5432/csi_system"  # ❌ 認証情報露出
)

# Line 99-106: ブロックチェーン認証情報がハードコード
BLOCKCHAIN_ACCOUNT_ADDRESS: str = os.getenv(
    "BLOCKCHAIN_ACCOUNT_ADDRESS",
    "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1"  # ❌ 公開アドレス
)
BLOCKCHAIN_PRIVATE_KEY: str = os.getenv(
    "BLOCKCHAIN_PRIVATE_KEY",
    ""  # ❌ デフォルトで空（開発環境のみ安全）
)
```

**リスク**:
- JWT秘密鍵の漏洩 → 認証バイパス、セッションハイジャック
- データベース認証情報の露出 → 不正アクセス、データ漏洩
- ブロックチェーン秘密鍵の管理不備 → 資産盗難、トランザクション改ざん

**修正方法**:
```python
# ✅ 正しい実装
import secrets

class Settings:
    # 環境変数必須、デフォルト値なし
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")

    def __post_init__(self):
        # 起動時に必須環境変数をチェック
        if not self.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY environment variable is required")

        # 開発環境でも安全なランダム生成
        if self.DEBUG and self.JWT_SECRET_KEY == "":
            self.JWT_SECRET_KEY = secrets.token_urlsafe(32)
            print("⚠️ WARNING: Using auto-generated JWT_SECRET_KEY (dev only)")
```

**即座の対応**:
1. `.env`ファイルに本番用の強力な秘密鍵を設定
2. `.env.example`を作成し、プレースホルダーのみ記載
3. `.gitignore`に`.env`が含まれていることを確認（✅ 既に設定済み）
4. 本番環境デプロイ前にすべての秘密鍵をローテーション

---

#### 2. **JWT トークンストレージの脆弱性**
**ファイル**: `frontend/src/services/api.ts`, `frontend/src/hooks/useAuth.tsx`
**重大度**: 🔴 HIGH
**CVSS スコア**: 7.5 (High)

**問題点**:
```typescript
// api.ts:20-22, 28-29, 37-38 - LocalStorageにトークン保存
if (typeof window !== 'undefined') {
  this.token = localStorage.getItem('access_token')  // ❌ XSS攻撃に脆弱
}
localStorage.setItem('access_token', token)  // ❌ XSS攻撃に脆弱
```

**リスク**:
- XSS攻撃によるトークン盗難
- CSRF攻撃への脆弱性
- トークンの永続化（ログアウト後も残る可能性）

**推奨対策**:
1. **HttpOnly Cookie使用** (最優先)
   ```typescript
   // バックエンド: トークンをHttpOnly Cookieで返す
   response.set_cookie(
       key="access_token",
       value=token,
       httponly=True,  // JavaScriptからアクセス不可
       secure=True,    // HTTPS通信のみ
       samesite="strict"  // CSRF対策
   )
   ```

2. **代替案: セキュアなメモリストレージ**
   ```typescript
   // メモリにのみ保存（リロード時は再認証）
   class SecureTokenStore {
     private token: string | null = null

     setToken(token: string) {
       this.token = token
       // LocalStorageは使用しない
     }
   }
   ```

---

#### 3. **時刻関数の非推奨使用（UTC問題）**
**ファイル**: `backend/app/core/security.py`
**重大度**: 🟡 MEDIUM
**CVSS スコア**: 5.3 (Medium)

**問題点**:
```python
# Line 29, 31: datetime.utcnow() は非推奨
expire = datetime.utcnow() + expires_delta  # ❌ Python 3.12+ で非推奨
```

**リスク**:
- タイムゾーン情報なしのnaive datetimeによる認証エラー
- 将来のPython バージョンで動作しない可能性

**修正方法**:
```python
from datetime import datetime, timedelta, timezone

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """JWTアクセストークンを生成"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta  # ✅ 推奨
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt
```

---

#### 4. **API エンドポイントのハードコード**
**ファイル**: `frontend/src/services/api.ts`
**重大度**: 🟡 MEDIUM

**問題点**:
```typescript
// Line 8-10: IPアドレスのハードコード
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?
  `${process.env.NEXT_PUBLIC_API_URL}/api/v2` :
  'http://192.168.101.168:8000/api/v2'  // ❌ ローカルIPハードコード
```

**リスク**:
- 開発環境の設定が本番環境に漏洩
- ネットワーク構成の変更に脆弱
- セキュリティスキャンツールで検出される可能性

**修正方法**:
```typescript
// ✅ 環境変数必須、適切なフォールバック
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v2`
  : (() => {
      if (process.env.NODE_ENV === 'production') {
        throw new Error('NEXT_PUBLIC_API_URL is required in production')
      }
      // 開発環境では相対パスまたはlocalhost
      return 'http://localhost:8000/api/v2'
    })()
```

---

## 🟡 品質・保守性の問題

### コード品質スコア: 7.0/10

#### 1. **エラーハンドリングの不足**
**影響範囲**: Backend全体
**重大度**: 🟡 MEDIUM

**問題点**:
- 例外の詳細情報がクライアントに漏洩する可能性
- エラーログの構造化が不十分
- ユーザーフレンドリーなエラーメッセージの欠如

**推奨改善**:
```python
# ✅ 構造化エラーハンドリング
from fastapi import HTTPException
from enum import Enum
import structlog

logger = structlog.get_logger()

class ErrorCode(Enum):
    AUTH_FAILED = "AUTH_001"
    INVALID_INPUT = "VAL_001"
    DB_ERROR = "DB_001"

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unexpected error",
        error=str(exc),
        path=request.url.path,
        method=request.method
    )

    # クライアントには詳細を渡さない
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "request_id": str(uuid.uuid4())
        }
    )
```

---

#### 2. **型安全性の向上余地**
**影響範囲**: Frontend API クライアント
**重大度**: 🟡 LOW-MEDIUM

**問題点**:
```typescript
// frontend/src/services/api.ts
async getDevices(params?: URLSearchParams): Promise<any> {  // ❌ any型
  const endpoint = params ? `/devices/?${params.toString()}` : '/devices/'
  return this.get<any>(endpoint)  // ❌ any型
}
```

**推奨改善**:
```typescript
// ✅ 厳密な型定義
interface DeviceListResponse {
  devices: Device[]
  total: number
  page: number
  page_size: number
}

async getDevices(params?: URLSearchParams): Promise<DeviceListResponse> {
  const endpoint = params ? `/devices/?${params.toString()}` : '/devices/'
  return this.get<DeviceListResponse>(endpoint)
}
```

---

#### 3. **依存関係の古いバージョン**
**ファイル**: `backend/requirements.txt`
**重大度**: 🟡 MEDIUM

**問題点**:
```txt
fastapi==0.109.0  # ❌ 最新は 0.115.x (2025年現在)
uvicorn[standard]==0.25.0  # ❌ 最新は 0.34.x
sqlalchemy==2.0.25  # ⚠️ 最新は 2.0.36
redis==5.0.1  # ⚠️ 最新は 5.2.x
```

**推奨対応**:
1. セキュリティパッチ適用のため依存関係を更新
2. `requirements.txt`に上限バージョン指定
3. 定期的な依存関係監査（Dependabot, Renovate等）

```txt
# ✅ バージョン範囲指定
fastapi>=0.115.0,<0.116.0
uvicorn[standard]>=0.34.0,<0.35.0
sqlalchemy>=2.0.36,<2.1.0
```

---

## ⚡ パフォーマンス分析

### パフォーマンススコア: 8.5/10

#### ✅ 良好な実装

1. **キャッシュ戦略**
   - Redis キャッシュ統合済み
   - TTL設定が適切（5分〜30分）
   - キャッシュ有効化フラグあり

2. **WebSocket リアルタイム通信**
   - Socket.io 統合
   - 効率的なデータストリーミング

3. **データベース最適化の余地あり**
   - SQLAlchemy ORM使用
   - インデックス戦略の検証が必要

#### 🟡 改善推奨事項

##### 1. **N+1 クエリ問題の予防**
```python
# ⚠️ 潜在的なN+1問題（要検証）
# 各デバイスのCSIデータを取得する際にループ内でクエリが発行される可能性

# ✅ Eager Loading推奨
from sqlalchemy.orm import joinedload

devices = session.query(Device).options(
    joinedload(Device.csi_data),
    joinedload(Device.breathing_analyses)
).all()
```

##### 2. **フロントエンドバンドルサイズ最適化**
```json
// package.json - 依存関係の見直し
{
  "dependencies": {
    "axios": "^1.6.5",  // ⚠️ 使用されていない可能性（fetchベース実装）
    "recharts": "^2.15.4"  // ⚠️ 大きなライブラリ（代替案: chart.js）
  }
}
```

**推奨**:
- 未使用依存関係の削除
- Tree-shaking最適化
- Code Splitting（Next.js dynamic import活用）

---

## 🏗️ アーキテクチャ評価

### アーキテクチャスコア: 7.5/10

#### ✅ 強み

1. **明確なレイヤー分離**
   - API層、サービス層、モデル層が分離
   - 責任分担が明確

2. **拡張性のある設計**
   - APIバージョニング（`/api/v2`）
   - モジュラーな構造

3. **最新技術スタック**
   - FastAPI（非同期対応）
   - Next.js 15（App Router）
   - React 19

#### 🟡 改善推奨

##### 1. **環境変数管理の一元化**
**現状**: 分散した環境変数管理
**推奨**: 統一された設定管理

```python
# ✅ Pydantic Settingsによる型安全な設定
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # 必須フィールド（デフォルトなし）
    jwt_secret_key: str = Field(..., min_length=32)
    database_url: str = Field(...)

    # オプショナルフィールド（適切なデフォルト）
    debug: bool = False
    cache_enabled: bool = True

    @validator('jwt_secret_key')
    def validate_jwt_secret(cls, v):
        if v == "your-super-secret-jwt-key-change-in-production":
            raise ValueError("Default JWT secret key is not allowed in production")
        return v

settings = Settings()
```

##### 2. **テストカバレッジの向上**
**現状**: テストファイル不足
**推奨**: 包括的テスト戦略

```python
# backend/tests/test_security.py
import pytest
from app.core.security import create_access_token, verify_token

def test_jwt_token_creation():
    token = create_access_token("user123")
    assert token is not None
    assert verify_token(token) == "user123"

def test_jwt_token_expiration():
    from datetime import timedelta
    token = create_access_token("user123", expires_delta=timedelta(seconds=1))
    time.sleep(2)
    assert verify_token(token) is None  # 期限切れ
```

---

## 📋 優先順位付き改善ロードマップ

### 🔴 Phase 1: セキュリティ緊急対応（1週間以内）

| タスク | 優先度 | 工数見積 | 影響範囲 |
|--------|--------|---------|---------|
| JWT秘密鍵をハードコードから環境変数へ移行 | 🔴 CRITICAL | 2時間 | Backend |
| データベース認証情報の環境変数化 | 🔴 CRITICAL | 1時間 | Backend |
| LocalStorageからHttpOnly Cookieへの移行 | 🔴 HIGH | 4時間 | Frontend + Backend |
| `datetime.utcnow()`を`datetime.now(timezone.utc)`へ修正 | 🟡 MEDIUM | 1時間 | Backend |
| API URLのハードコード削除 | 🟡 MEDIUM | 1時間 | Frontend |

**合計工数**: 約9時間（1-2営業日）

---

### 🟡 Phase 2: 品質・保守性向上（2-3週間）

| タスク | 優先度 | 工数見積 | 影響範囲 |
|--------|--------|---------|---------|
| 構造化エラーハンドリングの実装 | 🟡 MEDIUM | 8時間 | Backend |
| 型安全性の向上（TypeScript厳密化） | 🟡 MEDIUM | 6時間 | Frontend |
| 依存関係の更新とセキュリティ監査 | 🟡 MEDIUM | 4時間 | Both |
| テストカバレッジ向上（60%以上） | 🟡 MEDIUM | 16時間 | Both |
| 環境変数管理の一元化 | 🟡 MEDIUM | 4時間 | Backend |

**合計工数**: 約38時間（5営業日）

---

### 🟢 Phase 3: パフォーマンス最適化（1ヶ月）

| タスク | 優先度 | 工数見積 | 影響範囲 |
|--------|--------|---------|---------|
| N+1クエリ問題の調査と修正 | 🟢 LOW | 8時間 | Backend |
| フロントエンドバンドルサイズ最適化 | 🟢 LOW | 6時間 | Frontend |
| データベースインデックス最適化 | 🟢 LOW | 4時間 | Backend |
| Code Splitting導入 | 🟢 LOW | 6時間 | Frontend |

**合計工数**: 約24時間（3営業日）

---

## 🔧 即座に実行可能なクイックフィックス

### 1. `.env.example`の作成
```bash
# .env.example
PROJECT_NAME="CSI Respiratory Monitoring System"
VERSION="2.5.0"

# 必須: セキュリティ設定（本番環境で設定必須）
JWT_SECRET_KEY=CHANGE_ME_TO_RANDOM_32_CHAR_STRING
DATABASE_URL=postgresql://username:password@host:port/dbname
REDIS_URL=redis://host:port/db

# オプショナル: デフォルト値あり
DEBUG=false
CACHE_ENABLED=true
BLOCKCHAIN_ENABLED=true
```

### 2. セキュリティチェックスクリプト
```python
# backend/scripts/security_check.py
import os
import sys

REQUIRED_ENV_VARS = [
    "JWT_SECRET_KEY",
    "DATABASE_URL",
    "REDIS_URL"
]

DANGEROUS_DEFAULTS = {
    "JWT_SECRET_KEY": "your-super-secret-jwt-key-change-in-production"
}

def check_env_vars():
    """環境変数のセキュリティチェック"""
    errors = []

    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if not value:
            errors.append(f"❌ {var} is not set")
        elif var in DANGEROUS_DEFAULTS and value == DANGEROUS_DEFAULTS[var]:
            errors.append(f"🚨 {var} is using DANGEROUS default value")

    if errors:
        print("\n".join(errors))
        sys.exit(1)
    else:
        print("✅ All security checks passed")

if __name__ == "__main__":
    check_env_vars()
```

### 3. Docker Composeのシークレット管理
```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}  # ✅ 環境変数から注入
      - DATABASE_URL=${DATABASE_URL}
    env_file:
      - .env  # ✅ .envファイルから読み込み
```

---

## 📊 継続的モニタリング推奨事項

### セキュリティ監視
- [ ] **Dependabot / Renovate** - 依存関係の自動更新
- [ ] **Bandit / Safety** - Python セキュリティスキャン
- [ ] **npm audit** - Node.js 依存関係監査
- [ ] **SonarQube / CodeQL** - 静的コード分析

### 品質監視
- [ ] **Pytest Coverage** - テストカバレッジ（目標: 80%以上）
- [ ] **ESLint / Prettier** - コードスタイル統一
- [ ] **Black / isort / flake8** - Pythonコード品質

### パフォーマンス監視
- [ ] **Lighthouse** - フロントエンド性能スコア
- [ ] **New Relic / DataDog** - APMツール統合
- [ ] **PostgreSQL Slow Query Log** - データベースパフォーマンス

---

## 🎯 成功基準

### Phase 1完了時（セキュリティ）
- ✅ 全ての機密情報が環境変数から読み込まれる
- ✅ トークンがHttpOnly Cookieで管理される
- ✅ セキュリティスキャンで重大な脆弱性ゼロ

### Phase 2完了時（品質）
- ✅ テストカバレッジ60%以上
- ✅ TypeScript厳密モード有効
- ✅ 依存関係が最新安定版に更新

### Phase 3完了時（パフォーマンス）
- ✅ Lighthouseスコア90以上
- ✅ APIレスポンスタイム平均200ms以下
- ✅ バンドルサイズ30%削減

---

## 📝 結論

**現状評価**: プロジェクトは全体的に健全ですが、**セキュリティ面で緊急対応が必要**です。

**最優先事項**:
1. **JWT秘密鍵とDB認証情報の環境変数化**（CRITICAL）
2. **トークンストレージの安全化**（HIGH）
3. **非推奨APIの更新**（MEDIUM）

**推奨アクション**:
- Phase 1（セキュリティ）を1週間以内に完了
- Phase 2（品質）を3週間以内に実施
- Phase 3（パフォーマンス）は継続的改善として実施

このレポートに基づいた改善により、プロジェクトのセキュリティと品質が大幅に向上します。

---

**レポート作成**: Claude Code (Analysis Agent)
**次回レビュー推奨日**: 2025-12-11
**技術スタック**: FastAPI, Next.js, PostgreSQL, Redis, Blockchain
