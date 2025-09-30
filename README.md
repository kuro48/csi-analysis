# CSI呼吸監視システム Webプラットフォーム

Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムの統合Webプラットフォームです。

## システム概要

- **Frontend**: React + Next.js + TypeScript
- **Backend**: FastAPI + Python
- **Database**: PostgreSQL
- **Cache**: Redis
- **Real-time**: WebSocket
- **Auth**: JWT

## プロジェクト構造

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
│   ├── requirements.txt   # Python依存関係
│   └── .env.example      # 環境変数例
├── frontend/              # Next.js アプリケーション
│   ├── src/
│   │   ├── app/          # App Router
│   │   ├── components/   # Reactコンポーネント
│   │   ├── hooks/        # カスタムフック
│   │   ├── services/     # API呼び出し
│   │   └── types/        # TypeScript型定義
│   ├── package.json
│   └── next.config.js
├── database/              # データベース関連
│   ├── migrations/       # Alembicマイグレーション
│   └── scripts/          # 初期化・メンテナンススクリプト
├── docker/               # デバイス用Dockerfile
├── scripts/              # 実行スクリプト
└── docs/                 # ドキュメント
```

## 🚀 クイックスタート（Docker使用）

### 必要な環境
- Docker 20.0以上
- Docker Compose 2.0以上

### 一括セットアップ
```bash
# リポジトリクローン後、一括起動
./start.sh
```

起動後のアクセス:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **IPFS Gateway**: http://localhost:8080

### 初期管理者アカウント
- **ユーザー名**: admin
- **パスワード**: admin123

### サービス制御コマンド
```bash
# サービス停止
docker-compose down

# ログ確認
docker-compose logs -f

# 特定サービスのログ確認
docker-compose logs -f backend
docker-compose logs -f frontend

# サービス再起動
docker-compose restart

# 完全停止（ボリューム削除）
./scripts/stop.sh
```

## 手動開発環境セットアップ

### 必要な環境
- Python 3.11以上
- Node.js 18.0以上
- PostgreSQL 14.0以上
- Redis 6.0以上

### セットアップ手順

1. **リポジトリクローン**
   ```bash
   cd csi-web-platform
   ```

2. **バックエンドセットアップ**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env  # 環境変数設定
   ```

3. **フロントエンドセットアップ**
   ```bash
   cd frontend
   npm install
   cp .env.local.example .env.local  # 環境変数設定
   ```

4. **データベースセットアップ**
   ```bash
   # PostgreSQL起動
   createdb -U postgres csi_system
   # マイグレーション実行
   cd backend && alembic upgrade head
   ```

5. **Redis起動**
   ```bash
   redis-server
   ```

### 手動サーバー起動

```bash
# バックエンド（ポート8000）
cd backend && python -m uvicorn app.main:app --reload

# フロントエンド（ポート3000）
cd frontend && npm run dev
```

## API仕様

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## プロジェクト状況

### 完了済み機能（Phase 1）
- ✅ 開発環境構築（Docker + Docker Compose）
- ✅ 認証システム（JWT認証、ユーザー登録・ログイン）
- ✅ Web UI基本機能（Next.js、認証ページ、ダッシュボード）
- ✅ リアルタイム機能（WebSocket通信、リアルタイムチャート表示）

### 次期実装予定（Phase 2）
- 📋 デバイス管理機能
- 📊 データ分析機能
- 📤 エクスポート・通知機能
- 👥 管理者機能

## 貢献

プロジェクトへの貢献を歓迎します。まず既存の機能を確認し、改善提案やバグ報告をお願いします。