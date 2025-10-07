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

## 🚀 クイックスタート（推奨）

### 必要な環境
- Docker 20.0以上
- Docker Compose 2.0以上

### 自動セットアップ
```bash
# リポジトリクローン
git clone https://github.com/kuro48/csi-web-platform.git
cd csi-web-platform

# 一括起動（自動セットアップ）
./start.sh
```

起動スクリプトは以下を自動実行します：
- Docker・Docker Compose の確認
- 環境設定ファイルのコピー
- 既存コンテナの停止（オプション）
- イメージビルドとサービス起動
- データベース・Redis接続確認
- API・フロントエンド動作確認

### アクセス先
- **🌐 Frontend**: http://localhost:3000
- **🔧 Backend API**: http://localhost:8000
- **📖 API Documentation**: http://localhost:8000/docs
- **📁 IPFS Gateway**: http://localhost:8080

### 初期管理者アカウント
```
ユーザー名: admin
パスワード: admin123
```

### よく使うコマンド
```bash
# システム状態確認
./scripts/health_check.sh

# ログ確認
docker-compose logs -f

# 特定サービスのログ
docker-compose logs -f backend
docker-compose logs -f frontend

# サービス再起動
docker-compose restart

# サービス停止
docker-compose down

# 完全クリーンアップ
docker-compose down --volumes --remove-orphans
```

## 🛠️ 手動開発環境セットアップ

### 必要な環境
- **Python**: 3.11以上
- **Node.js**: 18.0以上
- **PostgreSQL**: 14.0以上
- **Redis**: 6.0以上

### 1. リポジトリクローン
```bash
git clone https://github.com/kuro48/csi-web-platform.git
cd csi-web-platform
```

### 2. バックエンドセットアップ
```bash
cd backend

# 仮想環境作成・有効化
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .envファイルを編集してデータベース接続情報を設定
```

### 3. フロントエンドセットアップ
```bash
cd frontend

# 依存関係インストール
npm install

# 環境変数設定
cp .env.local.example .env.local
# .env.localファイルでAPI URLを設定
```

### 4. データベースセットアップ
```bash
# PostgreSQLデータベース作成
createdb -U postgres csi_system

# マイグレーション実行
cd backend
alembic upgrade head

# 初期管理者アカウント作成
python scripts/create_admin.py
```

### 5. 外部サービス起動
```bash
# Redis起動
redis-server

# PostgreSQL起動（必要に応じて）
sudo systemctl start postgresql  # Linux
brew services start postgresql   # macOS
```

### 6. アプリケーション起動
```bash
# バックエンド起動（ポート8000）
cd backend
python -m uvicorn app.main:app --reload

# フロントエンド起動（ポート3000）
cd frontend
npm run dev
```

### 7. 動作確認
```bash
# ヘルスチェック
curl http://localhost:8000/health

# フロントエンドアクセス
open http://localhost:3000
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

## 📊 プロジェクト状況

### ✅ 完了済み機能（Phase 1）
- **🏗️ 開発環境構築**（Docker + Docker Compose）
- **🔐 認証システム**（JWT認証、ユーザー登録・ログイン）
- **💻 Web UI基本機能**（Next.js、認証ページ、ダッシュボード）
- **⚡ リアルタイム機能**（WebSocket通信、リアルタイムチャート表示）
- **📱 デバイス管理機能**（デバイス登録、ステータス監視、ハートビート）
- **💾 CSIデータ管理**（アップロード、保存、一覧表示）
- **🔍 PCAP解析機能**（Wi-Fi CSIデータ自動抽出、Scapy統合）
- **📈 CSI可視化機能**（インタラクティブグラフ、時系列分析）
- **🚀 本番環境対応**（デプロイスクリプト、バックアップ、監視）

### 主要機能詳細

#### CSIデータ処理・可視化システム
- **PCAPファイル解析**: Wi-FiパケットからCSI情報自動抽出
- **リアルタイム可視化**: 振幅・位相データのインタラクティブグラフ表示
- **サブキャリア分析**: 最大64サブキャリアの個別表示（5/10/20/32/64個選択可能）
- **時間窓フィルタ**: 30秒〜10分の時間範囲選択
- **データ統計**: サンプル数、信号品質、時間範囲の統計表示

#### 運用・管理機能
- **自動セットアップ**: `./start.sh`でワンクリック環境構築
- **ヘルスチェック**: `./scripts/health_check.sh`でシステム状態監視
- **バックアップ**: `./scripts/backup.sh`で自動データバックアップ
- **管理者作成**: `./scripts/create_admin.py`で初期アカウント作成

#### 技術仕様
- **PCAP解析**: Scapy + PyShark によるパケット解析
- **グラフライブラリ**: Recharts（React）でインタラクティブ表示
- **ファイル形式**: .pcap、.pcapng対応（最大100MB）
- **解析速度**: 100パケット/秒の高速処理
- **認証**: JWT + Redis セッション管理
- **リアルタイム**: WebSocket + チャンネル購読システム

### 🔮 次期実装予定（Phase 2）
- 📊 **呼吸解析アルゴリズム**（FFT、機械学習による呼吸パターン検出）
- 📋 **セッション管理・記録機能**（長期測定記録、履歴管理）
- 📤 **データエクスポート・レポート生成**（CSV、PDF出力）
- 🔔 **リアルタイム異常検知・アラート機能**（閾値監視、通知システム）
- 🌐 **IPFS分散ストレージ統合**（データ永続化）
- ⛓️ **ブロックチェーン連携**（データ完全性保証）

## 🔧 トラブルシューティング

### 📋 問題解決の流れ
```bash
# 1. まずシステム全体の状態確認
./scripts/health_check.sh

# 2. 問題が見つかった場合のログ確認
docker-compose logs -f [service_name]

# 3. 必要に応じてサービス再起動
docker-compose restart [service_name]
```

### よくある問題と解決法

#### 1. 🚀 起動時のエラー
```bash
# Docker環境確認
docker --version
docker-compose --version

# ポート競合確認
netstat -tulpn | grep -E ':3000|:8000|:5432|:6379'

# 完全クリーンアップして再起動
docker-compose down --volumes --remove-orphans
./start.sh
```

#### 2. 📁 PCAPファイルアップロードエラー
```bash
# ファイル形式確認
file sample.pcap

# ファイルサイズ確認（100MB以下か）
ls -lh sample.pcap

# バックエンドログ確認
docker-compose logs -f backend
```

#### 3. 📈 グラフが表示されない
- ブラウザの開発者ツール（F12）でエラー確認
- CSIデータのステータスが「処理完了」になっているか確認
- 認証トークンの有効性確認

#### 4. 🔐 認証エラー
```bash
# 管理者アカウント再作成
docker-compose exec backend python scripts/create_admin.py

# JWTトークン確認
curl -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

#### 5. 🗄️ データベース接続エラー
```bash
# PostgreSQL状態確認
docker-compose exec postgres pg_isready -U csi_user -d csi_system

# データベース再初期化
docker-compose down -v
docker-compose up -d postgres
docker-compose exec backend alembic upgrade head
```

#### 6. 🔴 Redis接続エラー
```bash
# Redis接続確認
docker-compose exec redis redis-cli ping

# Redis再起動
docker-compose restart redis
```

### 🆘 緊急時対応
```bash
# システム全体の完全リセット
docker-compose down --volumes --remove-orphans
docker system prune -af
./start.sh

# データベースのみ再初期化（データ保持）
docker-compose restart postgres
docker-compose exec backend alembic upgrade head
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

## 🤝 貢献・開発

### 開発環境での貢献方法
1. **フォーク・ブランチ作成**
   ```bash
   git fork https://github.com/kuro48/csi-web-platform.git
   git checkout -b feature/your-feature-name
   ```

2. **機能追加・バグ修正を実装**
   - バックエンド: `backend/app/` 以下
   - フロントエンド: `frontend/src/` 以下

3. **テスト実行・動作確認**
   ```bash
   # システム全体テスト
   ./scripts/health_check.sh

   # バックエンドテスト
   cd backend && python -m pytest

   # フロントエンドビルドテスト
   cd frontend && npm run build
   ```

4. **プルリクエスト作成**
   ```bash
   git add .
   git commit -m "機能追加: 新機能の説明"
   git push origin feature/your-feature-name
   ```

### 🛠️ 開発時の便利コマンド
```bash
# 開発環境でのホットリロード
cd backend && python -m uvicorn app.main:app --reload
cd frontend && npm run dev

# 本番環境での動作確認
docker-compose -f docker-compose.prod.yml up -d

# データベースマイグレーション作成
cd backend && alembic revision --autogenerate -m "変更内容"
```

## 📞 サポート・連絡先

### 技術サポート
- **Issues**: [GitHub Issues](https://github.com/kuro48/csi-web-platform/issues)
- **ドキュメント**: `docs/` フォルダ内
- **API仕様**: http://localhost:8000/docs

### プロジェクト関連
- **エッジデバイス**: [csi-edge-device](https://github.com/kuro48/csi-edge-device.git)
- **研究論文**: （準備中）

---

**CSI Web Platform** - Wi-Fi CSIを活用した次世代非接触呼吸監視システム 🌊📡