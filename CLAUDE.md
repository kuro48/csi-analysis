# CLAUDE.md

このファイルは、このリポジトリでClaude Code (claude.ai/code) が作業を行う際のガイダンスを提供します。

## プロジェクト概要

Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムの統合Webプラットフォームです。

### 主要コンポーネント
- **Frontend**: React + Next.js + TypeScript
- **Backend**: FastAPI + Python
- **Database**: PostgreSQL
- **Cache**: Redis
- **Real-time**: WebSocket
- **Auth**: JWT

## システムアーキテクチャ

統合Webプラットフォーム構成：

```
csi-web-platform/
├── backend/                # FastAPI サーバー
│   ├── app/
│   │   ├── main.py        # アプリケーションエントリーポイント
│   │   ├── core/          # 設定・データベース
│   │   ├── api/           # APIルーター
│   │   ├── models/        # SQLAlchemyモデル
│   │   ├── schemas/       # Pydanticスキーマ
│   │   └── services/      # ビジネスロジック
│   └── requirements.txt   # Python依存関係
├── frontend/              # Next.js アプリケーション
│   └── src/
│       ├── app/          # App Router
│       ├── components/   # Reactコンポーネント
│       ├── hooks/        # カスタムフック
│       ├── services/     # API呼び出し
│       └── types/        # TypeScript型定義
├── database/              # データベース関連
│   ├── migrations/       # Alembicマイグレーション
│   └── scripts/          # 初期化・メンテナンススクリプト
└── docs/                 # ドキュメント
```

## システム起動コマンド

### 🚀 統合システム起動（推奨）
```bash
# Docker一括起動スクリプト（全サービス一括起動）
./start.sh
```

### 個別サービス起動

#### 手動開発環境（Dockerを使わない場合）
```bash
# バックエンド起動（ポート8000）
cd backend
python -m uvicorn app.main:app --reload

# フロントエンド起動（ポート3000）
cd frontend
npm run dev
```

#### Docker個別サービス制御
```bash
# 特定サービスのログ確認
docker-compose logs -f backend
docker-compose logs -f frontend

# サービス停止
docker-compose down

# サービス再起動
docker-compose restart
```

## 設定ファイル

### 主要設定ファイル
- **Docker Compose**: `docker-compose.yml`
- **バックエンド環境変数**: `backend/.env`
- **フロントエンド環境変数**: `frontend/.env.local`

### 重要な環境変数
- `DATABASE_URL`: PostgreSQL接続URL
- `REDIS_URL`: Redis接続URL
- `JWT_SECRET_KEY`: JWT暗号化キー
- `NEXT_PUBLIC_API_URL`: フロントエンドからのAPI接続URL

## データフロー

1. **ユーザー**がWebブラウザでフロントエンドにアクセス
2. **フロントエンド**がバックエンドAPIに認証・データ要求
3. **バックエンド**がPostgreSQLからデータ取得、Redis経由でキャッシュ処理
4. **WebSocket**経由でリアルタイムデータ配信
5. **IPFS**との連携でデータ永続化（将来拡張用）

## 外部アクセス・APIエンドポイント

### Webアプリケーション
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **IPFS Gateway**: http://localhost:8080

### 主要APIエンドポイント
- `POST /api/v2/auth/login` - ユーザーログイン
- `POST /api/v2/auth/register` - ユーザー登録
- `GET /api/v2/users/me` - 現在ユーザー情報取得
- `POST /api/v2/csi-data/upload` - CSIデータアップロード
- `GET /api/v2/csi-data/` - CSIデータ一覧取得
- `GET /health` - サーバーヘルスチェック
- WebSocket: `/api/v2/ws` - リアルタイム通信

### 初期管理者アカウント
- **ユーザー名**: admin
- **パスワード**: admin123

## 主要技術詳細

- **認証システム**: JWT（JSON Web Token）ベース認証
- **リアルタイム通信**: WebSocket使用
- **データベース**: PostgreSQL（メインデータ）+ Redis（キャッシュ）
- **API**: FastAPI（OpenAPI自動生成）
- **フロントエンド**: React + Next.js（App Router）
- **データ永続化**: IPFS（将来拡張予定）

## システム要件

### 必要な環境
- **Docker**: 20.0以上
- **Docker Compose**: 2.0以上

### 手動開発環境の場合
- **Python**: 3.11以上
- **Node.js**: 18.0以上
- **PostgreSQL**: 14.0以上
- **Redis**: 6.0以上

### ポート要件
- **3000**: フロントエンド
- **8000**: バックエンドAPI
- **5432**: PostgreSQL
- **6379**: Redis
- **8080**: IPFS Gateway

## トラブルシューティング

### よくある問題

#### Docker起動エラー
```bash
# ポート競合エラーの場合
docker ps -a  # 使用中のコンテナ確認
docker-compose down  # 既存コンテナ停止

# 完全なクリーンアップ
./scripts/stop.sh
```

#### サービス接続エラー
```bash
# サービス状態確認
docker-compose ps

# 個別サービス確認
docker-compose logs backend
docker-compose logs frontend
```

#### 認証エラー
```bash
# JWT設定確認
# backend/.envのJWT_SECRET_KEYを確認
```

## 開発コマンド

### バックエンド開発
```bash
cd backend

# 依存関係インストール
pip install -r requirements.txt

# 開発サーバー起動
python -m uvicorn app.main:app --reload

# コード品質チェック
black app/                 # コードフォーマット
isort app/                 # import順序修正
flake8 app/                # リンター実行

# テスト実行
pytest                     # 全テスト実行
pytest tests/test_api.py   # 特定ファイルのテスト
```

### フロントエンド開発
```bash
cd frontend

# 依存関係インストール
npm install

# 開発サーバー起動
npm run dev                # Turbopack使用

# ビルド・品質チェック
npm run build              # 本番ビルド
npm run lint               # ESLint実行
npm run lint:fix           # ESLint自動修正
npm run type-check         # TypeScript型チェック
```

## API仕様とアーキテクチャ

### APIバージョニング
- **現在のAPIバージョン**: v2
- **ベースパス**: `/api/v2`
- **認証**: JWT Bearer Token
- **レート制限**: ログイン5回/分、API100回/分、アップロード10回/分

### 主要モデル構造
- **User**: ユーザー管理（認証・権限）
- **Device**: エッジデバイス登録・管理
- **CSIData**: CSI測定データ（生データ・解析結果）
- **Session**: 測定セッション管理
- **BreathingAnalysis**: 呼吸解析結果

### CSIデータフロー
1. エッジデバイス → `/api/v2/csi-data/upload` （認証必須）
2. バックエンド → PostgreSQL保存 + Redis キャッシュ
3. WebSocket経由でリアルタイム配信 → フロントエンド
4. IPFS連携でデータ永続化（将来機能）

### 外部システム連携
- **エッジデバイス**: https://github.com/kuro48/csi-edge-device.git
- **IPFS**: 分散ストレージ（将来拡張）
- **Blockchain**: イーサリアム連携（将来拡張）

## ZKPシステム（Zero-Knowledge Proof）

### コサイン類似度計算アーキテクチャ

**本番環境**: ZKP回路のみでコサイン類似度を計算（プライバシー保護）
**開発環境**: JavaScript/Python実装も使用可能（精度比較・デバッグ用）

#### 実装方式の使い分け

| 実装方式 | 開発環境 | 本番環境 | 用途 |
|---------|---------|---------|------|
| **ZKP回路（Circom）** | ✅ | ✅ **必須** | プライバシー保護された類似度計算 |
| **JavaScript実装** | ✅ | ❌ | Witness生成・精度比較 |
| **Python実装** | ✅ | ❌ | 高精度リファレンス・精度検証 |

#### ZKPサービス

**ファイル**: `backend/app/services/zkp_service.py`

主要メソッド:
- `generate_cosine_similarity_proof()` - コサイン類似度ZKP証明生成
- `verify_cosine_similarity_proof()` - ZKP証明検証
- `generate_proof()` - 呼吸解析ZKP証明生成（既存）
- `verify_proof()` - 呼吸解析ZKP証明検証（既存）

#### ZKP回路セットアップ

```bash
cd zkp

# 1. CSIサブキャリア選択回路のコンパイル
npm run compile:csi_selector

# 2. Trusted Setup（証明キー生成）
npm run setup:csi_selector

# 3. 証明生成テスト
node scripts/prove_from_all_subcarriers.js
```

#### 環境別設定

**本番環境** (`.env.production`):
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=false
ALLOW_JS_SIMILARITY=false
ALLOW_PYTHON_SIMILARITY=false
```

**開発環境** (`.env.development`):
```bash
ZKP_ENABLED=true
ZKP_DEVELOPMENT_MODE=true
ALLOW_JS_SIMILARITY=true      # JavaScript直接計算を許可
ALLOW_PYTHON_SIMILARITY=true  # Python直接計算を許可
```

#### 開発用スクリプト（本番環境では除外）

```
zkp/scripts/
├── calculate_all_subcarrier_similarity.js  # 全サブキャリア類似度計算
├── compare_similarity_accuracy.py          # 精度比較（Python vs 近似）
└── prove_from_all_subcarriers.js          # ZKP証明生成テスト
```

**重要**: これらのスクリプトは開発・テスト専用です。本番デプロイパッケージには含めません。

### ZKPデプロイガイド

詳細は `docs/ZKP_DEPLOYMENT_ARCHITECTURE.md` を参照してください。

#### 本番デプロイチェックリスト

- [ ] ZKP回路のコンパイル完了
- [ ] Trusted Setup完了
- [ ] 環境変数が本番設定（`ZKP_DEVELOPMENT_MODE=false`）
- [ ] 開発用スクリプトがデプロイパッケージから除外
- [ ] ZKP証明の生成・検証テスト完了
- [ ] パフォーマンステスト完了（証明生成 < 2秒、検証 < 100ms）
