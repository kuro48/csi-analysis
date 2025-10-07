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

## 🎯 使用方法

### 1. CSIデータ可視化のテスト

1. **Webアプリケーションにアクセス**
   ```
   http://localhost:3000
   ```

2. **管理者でログイン**
   - ユーザー名: `admin`
   - パスワード: `admin123`

3. **データ管理ページでPCAPファイルアップロード**
   - 「💾 データ管理」→「CSIデータアップロード」
   - PCAPファイル（.pcap/.pcapng）を選択
   - デバイスID、セッション名を入力してアップロード

4. **CSI可視化の確認**
   - 処理完了後、「グラフ表示」リンクをクリック
   - 振幅・位相データのインタラクティブグラフが表示
   - サブキャリア選択、時間窓設定が可能

### 2. 開発・デバッグ

```bash
# APIテスト（PCAPアップロード）
curl -X POST "http://localhost:8000/api/v2/csi-data/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample.pcap" \
  -F "device_id=test-device-001"

# 可視化データ取得テスト
curl -X GET "http://localhost:8000/api/v2/csi-data/DATA_ID/visualization?subcarriers=5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## API仕様

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要エンドポイント
- `POST /api/v2/csi-data/upload` - PCAPファイルアップロード
- `GET /api/v2/csi-data/{id}` - CSIデータ詳細取得
- `GET /api/v2/csi-data/{id}/visualization` - 可視化データ取得
- `GET /api/v2/devices/` - デバイス一覧取得
- `POST /api/v2/auth/login` - ユーザーログイン

## プロジェクト状況

### 完了済み機能（Phase 1）
- ✅ 開発環境構築（Docker + Docker Compose）
- ✅ 認証システム（JWT認証、ユーザー登録・ログイン）
- ✅ Web UI基本機能（Next.js、認証ページ、ダッシュボード）
- ✅ リアルタイム機能（WebSocket通信、リアルタイムチャート表示）
- ✅ デバイス管理機能（デバイス登録、ステータス監視、ハートビート）
- ✅ CSIデータ管理（アップロード、保存、一覧表示）
- ✅ **PCAP解析機能**（Wi-Fi CSIデータ自動抽出、Scapy統合）
- ✅ **CSI可視化機能**（インタラクティブグラフ、時系列分析）

### 実装済み主要機能詳細

#### CSIデータ処理・可視化システム
- **PCAPファイル解析**: Wi-FiパケットからCSI情報自動抽出
- **リアルタイム可視化**: 振幅・位相データのインタラクティブグラフ表示
- **サブキャリア分析**: 最大64サブキャリアの個別表示
- **時間窓フィルタ**: 30秒〜10分の時間範囲選択
- **データ統計**: サンプル数、信号品質、時間範囲の統計表示

#### 技術仕様
- **PCAP解析**: Scapy + PyShark によるパケット解析
- **グラフライブラリ**: Recharts（React）
- **ファイル形式**: .pcap、.pcapng対応
- **解析速度**: 100パケット/秒の高速処理

### 次期実装予定（Phase 2）
- 📊 呼吸解析アルゴリズム（FFT、機械学習）
- 📋 セッション管理・記録機能
- 📤 データエクスポート・レポート生成
- 🔔 リアルタイム異常検知・アラート機能
- 🌐 IPFS分散ストレージ統合
- ⛓️ ブロックチェーン連携（データ完全性）

## 🔧 トラブルシューティング

### よくある問題

#### 1. PCAPファイルアップロードエラー
```bash
# 依存関係の確認・インストール
docker-compose exec backend pip install scapy pyshark

# ファイル形式確認
file sample.pcap  # 正しいPCAPファイルか確認
```

#### 2. グラフが表示されない
- ブラウザの開発者ツールでネットワークエラーを確認
- 認証トークンの有効性を確認
- CSIデータのステータスが「処理完了」になっているか確認

#### 3. 認証エラー
```bash
# 管理者アカウントの再作成
docker-compose exec backend python -c "
from app.core.database import get_db
from app.services.user import create_superuser
create_superuser('admin', 'admin@example.com', 'admin123')
"
```

#### 4. サービス起動エラー
```bash
# ポート競合の確認
docker ps -a
netstat -tulpn | grep :3000
netstat -tulpn | grep :8000

# 完全なクリーンアップ
docker-compose down -v
docker system prune -f
./start.sh
```

#### 5. データベース接続エラー
```bash
# PostgreSQL状態確認
docker-compose logs postgres

# データベース再初期化
docker-compose down -v
docker-compose up -d postgres
# マイグレーション実行後、再起動
```

## 📊 システム要件

### 推奨環境
- **CPU**: 2コア以上
- **メモリ**: 4GB以上
- **ディスク**: 10GB以上の空き容量
- **ネットワーク**: インターネット接続（Dockerイメージ取得）

### サポートファイル形式
- **.pcap**: 標準PCAP形式
- **.pcapng**: 次世代PCAP形式
- **最大ファイルサイズ**: 100MB

### ブラウザサポート
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 貢献

プロジェクトへの貢献を歓迎します。まず既存の機能を確認し、改善提案やバグ報告をお願いします。

### 開発環境での貢献方法
1. フォークしてブランチを作成
2. 機能追加・バグ修正を実装
3. テストを実行して動作確認
4. プルリクエストを作成