# CLAUDE.md

このファイルは、このリポジトリでClaude Code (claude.ai/code) が作業を行う際のガイダンスを提供します。

## プロジェクト概要

Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムの統合Webプラットフォームです。

- **バージョン**: 2.5.0

### 主要コンポーネント
- **Frontend**: React 19 + Next.js 15.5.4 + TypeScript
- **Backend**: FastAPI 0.115.0 + Python 3.11
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **Real-time**: WebSocket (socket.io)
- **Auth**: JWT
- **ZKP**: Circom + snarkjs（プライバシー保護）
- **Blockchain**: Ethereum + Solidity（ZKP証明記録）

## システムアーキテクチャ

統合Webプラットフォーム構成：

```
csi-web-platform/
├── backend/                         # FastAPI サーバー
│   ├── app/
│   │   ├── main.py                 # アプリケーションエントリーポイント
│   │   ├── core/                   # 設定・データベース・エラーハンドラー
│   │   ├── api/
│   │   │   ├── routes.py           # APIルーター統合
│   │   │   └── endpoints/
│   │   │       ├── health.py       # ヘルスチェック
│   │   │       ├── csi_data.py     # CSIデータ管理
│   │   │       ├── base_csi.py     # ベースCSI（基準データ）
│   │   │       └── blockchain.py   # ブロックチェーン連携
│   │   ├── models/                 # SQLAlchemyモデル
│   │   ├── schemas/                # Pydanticスキーマ
│   │   └── services/
│   │       ├── zkp_service.py      # ZKP証明生成・検証
│   │       ├── blockchain_service.py # Ethereumコントラクト連携
│   │       ├── csi_data.py         # CSIデータビジネスロジック
│   │       ├── pcap_analyzer.py    # PCAP解析
│   │       ├── base_csi.py         # ベースCSI処理
│   │       └── cache.py            # キャッシュ管理
│   ├── contracts/
│   │   ├── ZKProofRegistry.sol     # Solidityスマートコントラクト
│   │   ├── deploy_zkproof_contract.py
│   │   ├── deploy_full_similarity_verifier.py
│   │   ├── check_zkproof_blockchain.py
│   │   └── build/                  # コンパイル済みABI
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/                        # Next.js アプリケーション
│   └── src/
│       ├── app/                    # App Router
│       │   ├── dashboard/
│       │   ├── csi-data/
│       │   ├── analysis/
│       │   ├── auth/               # login / register
│       │   ├── monitoring/
│       │   ├── devices/
│       │   ├── data/
│       │   └── profile/
│       ├── components/
│       │   ├── visualization/      # CSIChart等
│       │   ├── charts/             # 呼吸分析チャート
│       │   ├── realtime/           # リアルタイムダッシュボード
│       │   ├── layout/             # Header・Sidebar
│       │   ├── auth/
│       │   ├── devices/
│       │   └── ui/                 # 基本UIコンポーネント
│       ├── hooks/
│       ├── services/               # API呼び出し
│       ├── types/
│       └── utils/
├── zkp/                             # ゼロ知識証明システム
│   ├── circuits/
│   │   └── csi_full_similarity.circom  # Circom回路
│   ├── scripts/
│   │   ├── compile.js
│   │   ├── setup.js
│   │   ├── prove.js
│   │   └── verify.js
│   ├── build/                      # コンパイル済み回路 (cpp/js)
│   ├── keys/                       # 証明鍵
│   ├── package.json
│   └── powersOfTau28_hez_final_12.ptau
├── database/                        # データベース関連
│   ├── migrations/                 # Alembicマイグレーション
│   └── scripts/                    # 初期化・メンテナンススクリプト
├── ganache/                         # 開発用Ethereumノード設定
├── nginx/                           # Nginxリバースプロキシ設定
├── scripts/                         # 実行スクリプト
├── docs/                            # ドキュメント
├── docker-compose.yml
└── start.sh                         # 一括起動スクリプト
```

## システム起動コマンド

### 統合システム起動（推奨）
```bash
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

## Dockerサービス構成

| サービス | コンテナ名 | イメージ | ポート |
|---------|-----------|---------|------|
| backend | csi_backend | カスタム (FastAPI) | 8000 |
| frontend | csi_frontend | カスタム (Next.js) | 3000 |
| postgres | csi_postgres | postgres:15-alpine | 5432 |
| redis | csi_redis | redis:7-alpine | 6379 |
| ganache | - | trufflesuite/ganache | 8545 |

## 設定ファイル

### 主要設定ファイル
- **Docker Compose**: `docker-compose.yml`
- **バックエンド環境変数**: `backend/.env`（`backend/.env.example` を参照）
- **フロントエンド環境変数**: `frontend/.env.local`（`frontend/.env.example` を参照）

### 重要な環境変数

#### Backend
```env
# Database / Cache
DATABASE_URL=postgresql://csi_user:csi_password@localhost:5432/csi_system
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Research Mode
RESEARCH_MODE=true          # true: CSI生データ保存, false: プライバシー重視

# ZKP
ZKP_AUTO_GENERATE=true      # CSIアップロード時にZKP証明を自動生成
ZKP_AUTO_COMPILE=true       # 初回起動時に回路を自動コンパイル
ZKP_DATA_RETENTION_HOURS=0  # 0: 証明後すぐに生データ削除

# Blockchain (Ethereum)
ETHEREUM_RPC_URL=http://localhost:8545
ZKPROOF_CONTRACT_ADDRESS=
BLOCKCHAIN_PRIVATE_KEY=
ZKPROOF_STORE_FULL_DATA_ONCHAIN=false
ZKPROOF_ONCHAIN_MAX_JSON_CHARS=2048
```

#### Frontend
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME="CSI Respiratory Monitoring System"
NEXT_PUBLIC_APP_VERSION="2.5.0"
```

## データフロー

1. **ユーザー**がWebブラウザでフロントエンドにアクセス
2. **フロントエンド**がバックエンドAPIに認証・データ要求
3. **バックエンド**がPostgreSQLからデータ取得、Redis経由でキャッシュ処理
4. **WebSocket**経由でリアルタイムデータ配信
5. CSIアップロード時: PCAP解析 → ZKP証明生成 → Ethereumブロックチェーンに記録

## 外部アクセス・APIエンドポイント

### Webアプリケーション
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Ganache (開発用Ethereum)**: http://localhost:8545

### 主要APIエンドポイント（ベース: `/api/v2`）

#### 認証
- `POST /api/v2/auth/login` - ユーザーログイン
- `POST /api/v2/auth/register` - ユーザー登録
- `GET /api/v2/users/me` - 現在ユーザー情報取得

#### ヘルスチェック
- `GET /health` - サーバーヘルスチェック
- `GET /api/v2/health/` - 詳細ヘルスチェック
- `GET /api/v2/health/database` - DB接続確認
- `GET /api/v2/health/redis` - Redis接続確認

#### CSIデータ
- `POST /api/v2/csi-data/upload` - CSIデータアップロード（PCAP解析・ZKP自動生成）
- `GET /api/v2/csi-data/` - CSIデータ一覧取得

#### ベースCSI（基準データ）
- `/api/v2/base-csi/` - 基準CSIデータ管理

#### ブロックチェーン
- `GET /api/v2/blockchain/status` - ブロックチェーン接続状態確認
- `POST /api/v2/blockchain/record-proof` - ZKP証明を直接記録
- `POST /api/v2/blockchain/record-proof-from-csi` - CSIデータから証明を抽出して記録
- `GET /api/v2/blockchain/proof/{proof_id}` - 証明を取得
- `GET /api/v2/blockchain/device/{device_id}/proofs` - デバイスの証明一覧
- `GET /api/v2/blockchain/device/{device_id}/latest-proof` - デバイスの最新証明
- `POST /api/v2/blockchain/verify-proof-on-chain` - 証明を検証済みとしてマーク

#### WebSocket
- `ws://localhost:8000/api/v2/ws` - リアルタイム通信

### 初期管理者アカウント
- **ユーザー名**: admin
- **パスワード**: admin123

## 主要技術詳細

- **認証システム**: JWT（JSON Web Token）ベース認証
- **リアルタイム通信**: WebSocket（socket.io-client）使用
- **データベース**: PostgreSQL（メインデータ）+ Redis（キャッシュ・AOF永続化）
- **API**: FastAPI（OpenAPI自動生成）
- **フロントエンド**: React 19 + Next.js 15.5.4（App Router、Turbopack）
- **グラフ**: recharts
- **スタイリング**: Tailwind CSS v4

## システム要件

### 必要な環境
- **Docker**: 20.0以上
- **Docker Compose**: 2.0以上

### 手動開発環境の場合
- **Python**: 3.11以上
- **Node.js**: 18.0以上
- **PostgreSQL**: 15.0以上
- **Redis**: 7.0以上

### ポート要件
- **3000**: フロントエンド
- **8000**: バックエンドAPI
- **5432**: PostgreSQL
- **6379**: Redis
- **8545**: Ganache（開発用Ethereumノード）

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

#### ブロックチェーンに接続できない
```bash
# Ganache起動確認
docker ps | grep ganache

# ポート確認
lsof -i :8545

# Ganache再起動
docker-compose restart ganache
```

#### コントラクトアドレスが見つからない
```bash
# コントラクト再デプロイ
python backend/contracts/deploy_zkproof_contract.py

# .env確認
cat backend/.env | grep ZKPROOF_CONTRACT_ADDRESS
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
mypy app/                  # 型チェック

# テスト実行
pytest                     # 全テスト実行
pytest tests/test_api.py   # 特定ファイルのテスト
```

### フロントエンド開発
```bash
cd frontend

# 依存関係インストール
npm install

# 開発サーバー起動（Turbopack使用）
npm run dev

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
2. バックエンド → PCAP解析 → PostgreSQL保存 + Redis キャッシュ
3. ZKP証明自動生成（`ZKP_AUTO_GENERATE=true` 時）
4. Ethereumブロックチェーンに証明記録
5. WebSocket経由でリアルタイム配信 → フロントエンド

### 外部システム連携
- **エッジデバイス**: https://github.com/kuro48/csi-edge-device.git
- **Blockchain**: イーサリアム連携（実装済み - ZKP証明のみを記録）

## ZKPシステム（Zero-Knowledge Proof）

### コサイン類似度計算アーキテクチャ

**本番環境**: ZKP回路のみでコサイン類似度を計算（プライバシー保護）

#### 実装方式

| 実装方式 | 用途 |
|---------|------|
| **ZKP回路（Circom: csi_full_similarity）** | プライバシー保護された類似度計算（本番必須） |

#### ZKPサービス

**ファイル**: `backend/app/services/zkp_service.py`

主要メソッド:
- `generate_cosine_similarity_proof()` - コサイン類似度ZKP証明生成
- `verify_cosine_similarity_proof()` - ZKP証明検証
- `generate_proof()` - 呼吸解析ZKP証明生成
- `verify_proof()` - 呼吸解析ZKP証明検証

#### ZKP回路セットアップ

```bash
cd zkp

# 1. 回路のコンパイル
npm run compile

# 2. Trusted Setup（証明キー生成）
npm run setup

# 3. 証明生成テスト
npm run prove

# 4. 証明検証テスト
npm run verify
```

**回路ファイル**: `zkp/circuits/csi_full_similarity.circom`

#### 環境変数

```bash
ZKP_ENABLED=true
ZKP_AUTO_GENERATE=true       # CSIアップロード時に自動生成
ZKP_AUTO_COMPILE=true        # 初回起動時に自動コンパイル
ZKP_DATA_RETENTION_HOURS=0   # 0: 証明後すぐに生データ削除
```

### ZKPデプロイチェックリスト

- [ ] ZKP回路（csi_full_similarity）のコンパイル完了
- [ ] Trusted Setup完了
- [ ] 環境変数設定済み
- [ ] ZKP証明の生成・検証テスト完了
- [ ] パフォーマンステスト完了（証明生成 < 2秒、検証 < 100ms）

## ブロックチェーン統合（ZKP証明記録）

### 概要

ZKP証明**のみ**をブロックチェーンに記録し、元のCSIデータは公開しないプライバシー保護システム。

### アーキテクチャ

```
CSI解析 → ZKP証明生成 → ブロックチェーン記録（証明のみ）
                            ↓
                    改ざん防止 & 透明性確保
```

### 主要コンポーネント

#### スマートコントラクト

**ファイル**: `backend/contracts/ZKProofRegistry.sol`

- ZKP証明専用のSolidityコントラクト
- 証明データ（proof）、公開信号（publicSignals）、メタデータを保存
- アクセス制御（ホワイトリスト）機能
- バッチ処理対応

**デプロイスクリプト**:
- `deploy_zkproof_contract.py` - ZKProofRegistryコントラクトデプロイ
- `deploy_full_similarity_verifier.py` - Verifierコントラクトデプロイ

#### ブロックチェーンサービス

**ファイル**: `backend/app/services/blockchain_service.py`

主要メソッド:
- `record_zkp_proof()` - ZKP証明をブロックチェーンに記録
- `get_zkp_proof_by_id()` - 証明IDから証明を取得
- `get_device_proof_ids()` - デバイスの証明一覧を取得
- `verify_proof_on_chain()` - 証明を検証済みとしてマーク

### セットアップ手順

#### 1. Ganache起動（ローカル開発環境）

```bash
docker-compose up ganache -d
```

#### 2. スマートコントラクトのデプロイ

```bash
cd backend
pip install web3 py-solc-x

python contracts/deploy_zkproof_contract.py
```

#### 3. 環境変数設定

`backend/.env` に以下を追加：

```env
ETHEREUM_RPC_URL=http://localhost:8545
ZKPROOF_CONTRACT_ADDRESS=0x...   # デプロイ時に自動設定
BLOCKCHAIN_PRIVATE_KEY=           # 本番環境では必須
```

#### 4. ブロックチェーン状態確認

```bash
# CLIツール
python backend/contracts/check_zkproof_blockchain.py

# 最近の証明を表示
python backend/contracts/check_zkproof_blockchain.py --recent 5

# デバイスの証明を表示
python backend/contracts/check_zkproof_blockchain.py --device device_001
```

### プライバシー保護

- **元データ非公開**: CSI生データはブロックチェーンに記録しない
- **ZKP証明のみ**: 計算の正当性のみを証明
- **透明性**: 証明は誰でも検証可能
- **改ざん防止**: ブロックチェーンの不変性を活用

### 詳細ドキュメント

完全な実装ガイド・API仕様は `docs/BLOCKCHAIN_ZKP_INTEGRATION.md` を参照。
