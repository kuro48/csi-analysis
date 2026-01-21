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

## 外部アクセス・APIエンドポイント

### Webアプリケーション
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

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

### 外部システム連携
- **エッジデバイス**: https://github.com/kuro48/csi-edge-device.git
- **Blockchain**: イーサリアム連携（**実装済み** - ZKP証明のみを記録）

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

#### 1. スマートコントラクト

**ファイル**: `backend/contracts/ZKProofRegistry.sol`

- ZKP証明専用のSolidityコントラクト
- 証明データ（proof）、公開信号（publicSignals）、メタデータを保存
- アクセス制御（ホワイトリスト）機能
- バッチ処理対応

#### 2. ブロックチェーンサービス

**ファイル**: `backend/app/services/blockchain_service.py`

主要メソッド:
- `record_zkp_proof()` - ZKP証明をブロックチェーンに記録
- `get_zkp_proof_by_id()` - 証明IDから証明を取得
- `get_device_proof_ids()` - デバイスの証明一覧を取得
- `verify_proof_on_chain()` - 証明を検証済みとしてマーク

#### 3. APIエンドポイント

**ベースパス**: `/api/blockchain`

主要エンドポイント:
- `GET /status` - ブロックチェーン接続状態確認
- `POST /record-proof` - ZKP証明を直接記録
- `POST /record-proof-from-csi` - CSIデータから証明を抽出して記録
- `GET /proof/{proof_id}` - 証明を取得
- `GET /device/{device_id}/proofs` - デバイスの証明一覧
- `GET /device/{device_id}/latest-proof` - デバイスの最新証明
- `POST /verify-proof-on-chain` - 証明を検証済みとしてマーク

### セットアップ手順

#### 1. Ganache起動（ローカル開発環境）

```bash
# Docker Composeで起動
docker-compose up ganache -d
```

#### 2. スマートコントラクトのデプロイ

```bash
cd backend
pip install web3 py-solc-x

# ZKProofRegistryコントラクトをデプロイ
python contracts/deploy_zkproof_contract.py
```

#### 3. 環境変数設定

`backend/.env` に以下を追加：

```env
# Ethereumノード接続URL
ETHEREUM_RPC_URL=http://localhost:8545

# ZKProofRegistryコントラクトアドレス（デプロイ時に自動設定）
ZKPROOF_CONTRACT_ADDRESS=0x...

# トランザクション署名用の秘密鍵（本番環境では必須）
BLOCKCHAIN_PRIVATE_KEY=
```

#### 4. バックエンド再起動

```bash
docker-compose restart backend
```

### 使用例

#### 🚀 自動記録（推奨）

CSIデータをアップロードするだけで自動的にZKP証明がブロックチェーンに記録されます。

```bash
# CSIデータをアップロード
curl -X POST http://localhost:8000/api/csi-data/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@csi_data.pcap" \
  -F "device_id=device_001"

# バックグラウンドで自動的に：
# 1. PCAP解析
# 2. ZKP証明生成
# 3. ブロックチェーンに記録 ✨
```

#### ZKP証明を手動で記録

```bash
curl -X POST http://localhost:8000/api/blockchain/record-proof \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "device_001",
    "proof": {...},
    "public_signals": [...],
    "proof_type": "full_similarity"
  }'
```

#### CSIデータから証明を手動で記録

```bash
curl -X POST http://localhost:8000/api/blockchain/record-proof-from-csi \
  -H "Content-Type: application/json" \
  -d '{
    "csi_data_id": "550e8400-e29b-41d4-a716-446655440000",
    "proof_type": "full_similarity"
  }'
```

#### ブロックチェーン状態確認

```bash
# CLIツール
python backend/contracts/check_zkproof_blockchain.py

# 最近の証明を表示
python backend/contracts/check_zkproof_blockchain.py --recent 5

# デバイスの証明を表示
python backend/contracts/check_zkproof_blockchain.py --device device_001
```

### 環境変数

| 変数名 | 説明 | デフォルト値 |
|-------|------|------------|
| `ETHEREUM_RPC_URL` | EthereumノードのRPC URL | `http://ganache:8545` (Docker), `http://localhost:8545` (ローカル) |
| `ZKPROOF_CONTRACT_ADDRESS` | ZKProofRegistryコントラクトアドレス | デプロイ時に設定 |
| `BLOCKCHAIN_PRIVATE_KEY` | トランザクション署名用秘密鍵 | 開発環境では不要 |

### プライバシー保護

- ✅ **元データ非公開**: CSI生データはブロックチェーンに記録しない
- ✅ **ZKP証明のみ**: 計算の正当性のみを証明
- ✅ **透明性**: 証明は誰でも検証可能
- ✅ **改ざん防止**: ブロックチェーンの不変性を活用

### トラブルシューティング

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

### 詳細ドキュメント

完全な実装ガイド・API仕様は `docs/BLOCKCHAIN_ZKP_INTEGRATION.md` を参照してください。

### 本番環境デプロイ

本番環境（Ethereum Mainnet/Testnet）へのデプロイ手順：

1. **Infura/Alchemy等のノードプロバイダー**を設定
2. **デプロイアカウントの秘密鍵**を環境変数に設定
3. **コントラクトをデプロイ**
4. **ガスコストを監視**し、最適化
5. **Etherscanでコントラクトを検証**（透明性向上）

詳細は `docs/BLOCKCHAIN_ZKP_INTEGRATION.md` の「本番環境デプロイ」セクションを参照。
