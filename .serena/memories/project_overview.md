# プロジェクト概要

## プロジェクト名
CSI呼吸監視システム Webプラットフォーム

## 目的
Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムの統合Webプラットフォーム

## 技術スタック

### フロントエンド
- **フレームワーク**: Next.js 15.5.4 (App Router)
- **言語**: TypeScript
- **UIライブラリ**: React 19.1.0
- **ビルドツール**: Turbopack
- **グラフ**: Recharts
- **状態管理**: SWR + React Hook Form
- **リアルタイム通信**: Socket.io Client

### バックエンド
- **フレームワーク**: FastAPI 0.115.0
- **言語**: Python 3.11+
- **データベース**: PostgreSQL 15
- **キャッシュ**: Redis 7
- **ORM**: SQLAlchemy 2.0.25
- **マイグレーション**: Alembic 1.13.1
- **認証**: JWT (python-jose)
- **パスワードハッシュ**: bcrypt + passlib

### CSI解析
- **パケット解析**: Scapy 2.5.0, PyShark 0.6
- **CSI処理**: CSIKit 2.5
- **数値計算**: NumPy 1.24+, SciPy 1.11+
- **データ処理**: Pandas 2.0+

### ZKP（Zero-Knowledge Proof）
- **回路言語**: Circom
- **証明システム**: SnarkJS 0.7.4
- **ライブラリ**: circomlib 2.0.5

### インフラ
- **コンテナ**: Docker + Docker Compose
- **Webサーバー**: Uvicorn
- **プロキシ**: Nginx（将来）
- **分散ストレージ**: IPFS（将来）
- **ブロックチェーン**: Ethereum/Ganache（将来）

## コードベース構造

### Backend (FastAPI)
```
backend/app/
├── main.py              # アプリケーションエントリーポイント
├── core/                # 設定・データベース・セキュリティ
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   └── deps.py
├── api/                 # APIルーター
│   ├── routes.py        # ルーター統合
│   ├── endpoints/       # エンドポイント定義
│   └── v2/              # API v2
├── models/              # SQLAlchemyモデル
│   ├── user.py
│   ├── csi_data.py
│   └── breathing_analysis.py
├── schemas/             # Pydanticスキーマ
│   ├── auth.py
│   ├── user.py
│   └── csi_data.py
└── services/            # ビジネスロジック
    ├── auth.py
    ├── csi_data.py
    ├── pcap_analyzer.py
    ├── breathing_analysis.py
    ├── zkp_service.py
    ├── task_queue.py
    └── cache.py
```

### Frontend (Next.js)
```
frontend/src/
├── app/                 # App Router（Next.js 15）
├── components/          # Reactコンポーネント
├── hooks/               # カスタムフック
├── services/            # API呼び出しロジック
└── types/               # TypeScript型定義
```

### ZKP (Circom + SnarkJS)
```
zkp/
├── circuits/            # Circom回路定義
├── scripts/             # ZKPスクリプト（compile, setup, prove, verify）
├── proofs/              # 生成された証明
└── data/                # ZKPデータ
```

## 主要モデル

### CSIData
- セッション管理（session_id）
- データ格納（raw_data, processed_data）
- ファイル情報（file_path, file_size, ipfs_hash）
- ステータス（status: received, processing, completed, failed）
- ブロックチェーン連携（blockchain_tx_hash, blockchain_status）

### User
- 認証情報（username, hashed_password）
- プロフィール（email, full_name）
- 権限（is_active, is_superuser）

### Session
- セッション管理（session_name, start_time, end_time）
- 測定時間（duration）
- メタデータ（meta_data: JSONB）

### BreathingAnalysis
- 呼吸数（breathing_rate）
- 信頼度（confidence_score）
- 周波数域データ（frequency_domain_data）
- 時間域データ（time_domain_data）
- 品質メトリクス（quality_metrics）

## API設計

### エンドポイント構成
- `/api/v2/auth` - 認証（ログイン・登録）
- `/api/v2/csi-data` - CSIデータ管理
- `/api/v2/breathing-analysis` - 呼吸解析結果
- `/api/v2/zkp` - ゼロ知識証明
- `/api/v2/tasks` - タスク管理
- `/api/v2/health` - ヘルスチェック

### 認証方式
- JWT Bearer Token
- アクセストークン有効期限: 30分（設定可能）
- Redis セッション管理

## 開発環境

### Docker構成
- **postgres**: PostgreSQL 15
- **redis**: Redis 7
- **backend**: FastAPI アプリケーション
- **frontend**: Next.js アプリケーション

### ネットワーク
- csi_network (bridge)

### ボリューム
- postgres_data
- redis_data
- csi_uploads
