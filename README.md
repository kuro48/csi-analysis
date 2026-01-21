# CSI呼吸監視システム Webプラットフォーム

Wi-Fi CSI（Channel State Information）を活用した非接触呼吸監視システムの統合Webプラットフォームです。

## システム概要

- **Frontend**: React + Next.js + TypeScript
- **Backend**: FastAPI + Python
- **Database**: PostgreSQL
- **Cache**: Redis
- **Auth**: JWT
- **Blockchain**: Ethereum (Ganache) + Smart Contracts

## プロジェクト構造

```
csi-analysis/
├── backend/                # FastAPI サーバー
│   ├── app/
│   │   ├── main.py        # アプリケーションエントリーポイント
│   │   ├── core/          # 設定・データベース
│   │   ├── api/           # APIルーター
│   │   ├── models/        # SQLAlchemyモデル
│   │   ├── schemas/       # Pydanticスキーマ
│   │   └── services/      # ビジネスロジック
│   ├── contracts/         # スマートコントラクト
│   │   ├── ZKProofRegistry.sol    # Solidityコントラクト
│   │   ├── deploy_zkproof_contract.py  # デプロイスクリプト
│   │   └── build/                 # コンパイル済みABI
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
├── zkp/                   # ゼロ知識証明システム
│   ├── circuits/          # Circom回路定義
│   ├── src/               # ZKP実装コード
│   ├── scripts/           # ZKPスクリプト
│   ├── proofs/            # 生成された証明
│   ├── data/              # ZKPデータ
│   └── docs/              # ZKP関連ドキュメント
├── docs/                  # ドキュメント
│   ├── api/               # API仕様
│   ├── backend/           # バックエンド設計
│   ├── deployment/        # デプロイメント手順
│   ├── reports/           # 分析レポート
│   └── research/          # 研究資料
├── scripts/               # 実行スクリプト
└── nginx/                 # Nginx設定
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
- **⛓️ Ganache RPC**: http://localhost:8545
- **📊 Blockchain Explorer**: 開発中

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

3. **エッジデバイスからCSIデータ送信**
   - 研究用エッジデバイスがCSIデータを自動的にアップロード
   - Webインターフェースからの手動アップロードは不可（エッジデバイス専用API）
   - 「💾 データ管理」ページでアップロードされたデータを確認

4. **CSI可視化の確認**
   - 処理完了後、「グラフ表示」リンクをクリック
   - 振幅・位相データのインタラクティブグラフが表示
   - サブキャリア選択、時間窓設定が可能

### 2. 開発・デバッグ

```bash
# APIテスト（PCAPアップロード - エッジデバイス専用）
# 注意: このエンドポイントはエッジデバイスからのアップロード専用です
curl -X POST "http://localhost:8000/api/v2/csi-data/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@path/to/csi.pcap" \
  -F "device_id=test-device-001"

# 可視化データ取得テスト
curl -X GET "http://localhost:8000/api/v2/csi-data/DATA_ID/visualization?subcarriers=5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📡 エッジデバイスセットアップ（Raspberry Pi）

このシステムは、Raspberry Pi上で動作するエッジデバイスからCSIデータを自動収集します。

### エッジデバイスリポジトリ

エッジデバイス用のコードは別リポジトリで管理されています：
- **リポジトリ**: [csi-edge-device](https://github.com/kuro48/csi-edge-device.git)

### 前提条件

#### ハードウェア
- **Raspberry Pi**: 3B+ / 4 / 5 推奨
- **CSI対応WiFiアダプター**: Intel 5300 など
- **MicroSDカード**: 16GB以上
- **電源**: 5V 3A（Raspberry Pi 4/5の場合）

#### ソフトウェア
- **OS**: Raspberry Pi OS (Debian系)
- **Python**: 3.7以上
- **tcpdump**: CSIデータキャプチャ用
- **ネットワーク**: Webプラットフォームへの接続

### クイックスタート

#### 1. Webプラットフォーム側の準備

まず、このWebプラットフォームを起動してください：

```bash
# Webプラットフォーム起動
cd csi-web-platform
./start.sh

# 管理者でログイン: http://localhost:3000
# ユーザー名: admin
# パスワード: admin123
```

#### 2. Raspberry Piへのセットアップ

```bash
# Raspberry PiにSSHログイン
ssh pi@<raspberry_pi_ip>

# エッジデバイスリポジトリをクローン
git clone https://github.com/kuro48/csi-edge-device.git
cd csi-edge-device

# 依存関係インストール
pip3 install -r requirements.txt

# tcpdumpインストール（未インストールの場合）
sudo apt-get update
sudo apt-get install tcpdump
```

#### 3. デバイス登録

```bash
# デバイスをWebプラットフォームに登録
python3 register_device.py \
  --server http://192.168.1.100:8000 \
  --device-id raspberry_pi_001 \
  --device-name "Lab Raspberry Pi 001" \
  --location lab_room_1 \
  --username admin

# パスワード入力: admin123
```

**成功すると**:
- `config/device_config_v2.json` が自動生成されます
- デバイストークンが設定されます

#### 4. 接続テスト

```bash
# サーバー接続テスト
python3 main.py --mode test
```

#### 5. CSIデータ収集開始

```bash
# 単発テスト（60秒収集）
sudo python3 main.py --mode collect

# スケジュール実行（常時稼働）
sudo python3 main.py --mode schedule
```

**注意**: CSIデータ収集には`sudo`権限が必要です。

### 設定ファイル詳細

`config/device_config.json`:

```json
{
  "device_id": "raspberry_pi_001",
  "server_url": "http://192.168.1.100:8000",
  "device_token": "device_raspberry_pi_001_abc123def456",
  "collection_interval": 300,        // データ収集間隔（秒）
  "collection_duration": 60,         // 1回の収集時間（秒）
  "base_duration": 180,              // ベースライン収集時間（秒）
  "channel_width": "80MHz",          // WiFiチャネル幅
  "location": "lab_room_1",          // 設置場所
  "network_interface": "wlan0",      // ネットワークインターフェース
  "csi_port": 5500,                  // CSI取得ポート
  "upload_timeout": 60,              // アップロードタイムアウト（秒）
  "health_check_interval": 3600,    // ヘルスチェック間隔（秒）
  "delete_after_upload": false      // 送信後ファイル削除フラグ
}
```

### 環境変数設定

バックエンドの`.env`ファイルで重要な設定を管理します：

#### プライバシーモード設定

```bash
# 研究モード設定
RESEARCH_MODE=true              # true: データ保存, false: ZKP証明のみ保存

# ZKP設定
ZKP_AUTO_GENERATE=true          # 呼吸解析後に自動的にZKP証明を生成
ZKP_DATA_RETENTION_HOURS=0      # ZKP生成後のデータ保持時間（時間単位）
                                # 0: 即削除, >0: 指定時間後削除, -1: 削除しない
```

**推奨設定**:

| 用途 | RESEARCH_MODE | ZKP_AUTO_GENERATE | ZKP_DATA_RETENTION_HOURS |
|------|---------------|-------------------|-------------------------|
| 🔬 **研究・開発** | `true` | `false` | `-1` |
| 🧪 **テスト環境** | `true` | `true` | `24` |
| 🏥 **本番環境** | `false` | `true` | `0` |

#### その他の重要な環境変数

```bash
# データベース設定
DATABASE_URL=postgresql://user:password@localhost:5432/csi_system

# JWT認証設定（本番環境では必ず変更）
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Redis設定
REDIS_URL=redis://localhost:6379/0

# デバッグモード（本番環境ではfalse）
DEBUG=false
ENABLE_TEST_ENDPOINTS=false
```

### systemd自動起動設定

常時稼働させる場合、systemdサービスとして登録します：

```bash
# サービスファイル作成
sudo nano /etc/systemd/system/csi-edge-device.service
```

**サービスファイル内容**:
```ini
[Unit]
Description=CSI Edge Device (v2)
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/csi-edge-device
ExecStart=/usr/bin/python3 main.py --mode schedule --config config/device_config.json
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**サービス有効化**:
```bash
# systemdリロード
sudo systemctl daemon-reload

# サービス有効化
sudo systemctl enable csi-edge-device.service

# サービス起動
sudo systemctl start csi-edge-device.service

# ステータス確認
sudo systemctl status csi-edge-device.service

# ログ確認
sudo journalctl -u csi-edge-device.service -f
```

### データフロー全体像

#### 研究モード（RESEARCH_MODE=true）
```
[Raspberry Pi]
    ↓ tcpdump (60秒)
[PCAPファイル生成]
    ↓ EdgeDeviceManager
[HTTP POST multipart/form-data]
    ↓ Bearer device_token認証
[Webプラットフォーム: /api/v2/csi-data/upload]
    ↓ CSIDataService
[ファイル保存 + PCAP解析]
    ↓ CSIData保存（file_path, raw_data, processed_data）
[PostgreSQL + Blockchain]
    ↓ タスクキュー
[呼吸解析実行]
    ↓ ZKP証明生成（オプション）
[解析結果 + ZKP証明保存]
    ↓ REST API / ポーリング
[フロントエンド表示]
```

#### 本番モード（RESEARCH_MODE=false、プライバシー重視）
```
[Raspberry Pi]
    ↓ tcpdump (60秒)
[PCAPファイル生成]
    ↓ EdgeDeviceManager
[HTTP POST multipart/form-data]
    ↓ Bearer device_token認証
[Webプラットフォーム: /api/v2/csi-data/upload]
    ↓ CSIDataService
[一時ファイルで解析（保存しない）]
    ↓ CSIData保存（processed_dataのみ）
[PostgreSQL（file_path=null）]
    ↓ タスクキュー
[呼吸解析実行]
    ↓ ZKP証明生成（自動）
[ZKP証明のみ保存]
    ↓ データクリーンアップ（設定時間後）
[processed_dataも削除可能]
    ↓ REST API / ポーリング
[フロントエンド表示（ZKP検証済み）]
```

#### データ保持ポリシー
| モード | CSIファイル | raw_data | processed_data | ZKP証明 |
|--------|------------|----------|----------------|---------|
| **研究モード** | 保存 ✅ | 保存 ✅ | 保存 ✅ | 生成可能 |
| **本番モード** | 保存しない ❌ | 保存しない ❌ | 一時的に保存 | 必須 ✅ |
| **クリーンアップ後** | - | - | 削除可能 | 保持 ✅ |

### 実行モード

| モード | コマンド | 説明 | 用途 |
|--------|---------|------|------|
| **test** | `--mode test` | 接続テスト | セットアップ確認 |
| **collect** | `--mode collect` | 単発収集（60秒） | 動作確認 |
| **base** | `--mode base` | ベース収集（180秒） | 環境変化時 |
| **schedule** | `--mode schedule` | 定期実行（5分間隔） | 本番運用 |

### よくある問題と解決法

#### 1. tcpdump権限エラー
```bash
# エラー: You don't have permission to capture
# 解決: sudoで実行
sudo python3 main.py --mode collect
```

#### 2. 認証エラー (401 Unauthorized)
```bash
# 原因: デバイストークンが無効
# 確認:
cat config/device_config.json | grep device_token

# 再登録:
python3 register_device.py --device-id raspberry_pi_001 --username admin
```

#### 3. 接続エラー (Connection refused)
```bash
# 原因: サーバーURL間違いまたはサーバー未起動
# 確認:
curl http://192.168.1.100:8000/health

# 設定確認:
cat config/device_config.json | grep server_url
```

#### 4. CSIデータ収集失敗
```bash
# 原因: ネットワークインターフェース不正
# WiFiインターフェース確認:
ifconfig
iwconfig

# 設定修正:
nano config/device_config.json
# "network_interface": "wlan0" など
```

#### 5. アップロードタイムアウト
```json
{
  "upload_timeout": 120  // 60→120秒に変更
}
```

### ログ管理

**ログファイル場所**: `logs/edge_device_YYYYMMDD_HHMMSS.log`

```bash
# 最新ログ確認
tail -f logs/edge_device_$(date +%Y%m%d)*.log

# エラーのみ抽出
grep ERROR logs/*.log

# systemd経由のログ
sudo journalctl -u csi-edge-device.service -f
```

### リモートデプロイ

ローカルマシンからRaspberry Piへ一括デプロイ：

```bash
# ローカルマシンで実行
cd csi-edge-device
./deploy.sh <raspberry_pi_ip>

# 例:
./deploy.sh 192.168.1.100
```

**自動処理内容**:
1. リモートディレクトリ作成
2. 全ファイル転送（scp）
3. セットアップスクリプト実行
4. systemdサービス登録

### CSI対応WiFiアダプター設定

CSIデータ収集には専用のWiFiアダプターとドライバが必要です：

**推奨ハードウェア**:
- Intel WiFi Link 5300
- Atheros AR9280/AR9380
- Realtek RTL8812AU（一部対応）

**ドライバ設定** (Intel 5300の例):
```bash
# CSIツールのインストール
git clone https://github.com/dhalperi/linux-80211n-csitool.git
cd linux-80211n-csitool

# カーネルモジュールビルド
make

# モジュールロード
sudo modprobe iwlwifi connector_log=0x1
```

詳細は各CSIツールのドキュメントを参照してください。

### ベストプラクティス

#### 開発環境
```bash
# 単発テスト実行
sudo python3 main.py --mode collect

# ログ確認
tail -f logs/*.log

# 送信後削除しない
"delete_after_upload": false
```

#### 本番環境
```bash
# systemdサービス化
sudo systemctl enable csi-edge-device.service

# 自動再起動設定
"Restart=always"
"RestartSec=10"

# 送信後削除
"delete_after_upload": true
```

## API仕様

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要エンドポイント
- `POST /api/v2/csi-data/upload` - PCAPファイルアップロード（**エッジデバイス専用**）
- `GET /api/v2/csi-data/{id}` - CSIデータ詳細取得
- `GET /api/v2/csi-data/{id}/visualization` - 可視化データ取得
- `GET /api/v2/devices/` - デバイス一覧取得
- `POST /api/v2/auth/login` - ユーザーログイン

**注意**: CSIデータのアップロードは研究用エッジデバイスからのみ可能です。Webインターフェースからの手動アップロード機能はありません。

## 🚀 デプロイ（Mac Mini）

### 💻 Mac Miniセットアップ（5分・0円）

```bash
# 1. Docker Desktop for Mac インストール
brew install --cask docker  # 初回のみ

# 2. プロジェクトセットアップ
git clone https://github.com/kuro48/csi-web-platform.git
cd csi-web-platform
./start.sh

# 3. アクセス確認
# Frontend: http://Mac-MiniのIP:3000
# Backend API: http://Mac-MiniのIP:8000
```

**IPアドレス確認**:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

---

### 🌐 外部アクセス設定

**研究室外からアクセスしたい場合**:

#### ngrok（最も簡単・1分で完了）
```bash
brew install ngrok
ngrok http 3000  # HTTPS対応の外部URLが即座に発行
```

#### Cloudflare Tunnel（長期運用推奨・無料）
```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared tunnel login
cloudflared tunnel create csi-web-platform
# 詳細は SIMPLE_DEPLOY.md を参照
```

#### Tailscale（VPN・最もセキュア・無料）
```bash
brew install --cask tailscale
# 研究室メンバーのみ安全にアクセス可能
# 詳細は SIMPLE_DEPLOY.md を参照
```

**詳細な設定手順**: [Mac Miniデプロイガイド](docs/deployment/SIMPLE_DEPLOY.md)

---

### ✨ Mac Miniのメリット

- ✅ **コスト0円**（既存ハードウェア活用）
- ✅ **低消費電力**（24時間稼働で月数百円）
- ✅ **簡単セットアップ**（5分で起動）
- ✅ **物理アクセス**（トラブル時にすぐ対応可能）
- ✅ **安定性**（macOSの安定したDocker環境）

---

## 📊 プロジェクト状況

### ✅ 完了済み機能（Phase 1）
- **🏗️ 開発環境構築**（Docker + Docker Compose）
- **🔐 認証システム**（JWT認証、ユーザー登録・ログイン）
- **💻 Web UI基本機能**（Next.js、認証ページ、ダッシュボード）
- **📱 デバイス管理機能**（デバイス登録、ステータス監視、ハートビート）
- **💾 CSIデータ管理**（エッジデバイスからの自動アップロード、保存、一覧表示）
- **🔍 PCAP解析機能**（Wi-Fi CSIデータ自動抽出、Scapy統合）
- **📈 CSI可視化機能**（インタラクティブグラフ、時系列分析）
- **⛓️ ブロックチェーン統合**（Ethereum/Ganache、スマートコントラクト、データ完全性保証）
- **🚀 本番環境対応**（デプロイスクリプト、バックアップ、監視）

### 主要機能詳細

#### CSIデータ処理・可視化システム
- **PCAPファイル解析**: Wi-FiパケットからCSI情報自動抽出
- **リアルタイム可視化**: 振幅・位相データのインタラクティブグラフ表示
- **サブキャリア分析**: 最大64サブキャリアの個別表示（5/10/20/32/64個選択可能）
- **時間窓フィルタ**: 30秒〜10分の時間範囲選択
- **データ統計**: サンプル数、信号品質、時間範囲の統計表示

#### ブロックチェーン・分散ストレージ
- **スマートコントラクト**: Solidity製ZKProofRegistryコントラクト
- **改ざん防止**: ブロックチェーンによる証明トレーサビリティ
- **トランザクション管理**: 自動ガス見積もり、署名、確認
- **コントラクトデプロイ**: `python backend/contracts/deploy_zkproof_contract.py`

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
- **非同期処理**: タスクキュー（Redis）によるバックグラウンド処理
- **ブロックチェーン**: Solidity 0.8.20、Web3.py、Ganache（開発環境）
- **スマートコントラクト**: ERC標準準拠、ガス最適化済み

### 🔮 次期実装予定（Phase 2）
- 📊 **呼吸解析アルゴリズム**（FFT、機械学習による呼吸パターン検出）
- 📋 **セッション管理・記録機能**（長期測定記録、履歴管理）
- 📤 **データエクスポート・レポート生成**（CSV、PDF出力）
- 🔔 **リアルタイム異常検知・アラート機能**（閾値監視、通知システム）
- 🌐 **テストネットデプロイ**（Sepolia/Goerli対応）
- 🔍 **ブロックチェーンエクスプローラー**（トランザクション追跡UI）
- 📊 **データ分析ダッシュボード**（統計・可視化強化）

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
file path/to/csi.pcap

# ファイルサイズ確認（100MB以下か）
ls -lh path/to/csi.pcap

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
  - Raspberry Pi用CSI収集システム
  - tcpdumpベースの自動データ収集
  - HTTP/multipart-formでのアップロード
  - systemd自動起動対応
- **主要技術スタック**:
  - **Backend**: FastAPI + SQLAlchemy + Alembic
  - **Frontend**: Next.js 15 + React 19 + TypeScript
  - **Database**: PostgreSQL + Redis
  - **Blockchain**: Solidity + Web3.py + Ganache
  - **CSI解析**: Scapy + PyShark
  - **ZKP**: Circom + SnarkJS
- **研究論文**: （準備中）

---

**CSI Web Platform** - Wi-Fi CSIを活用した次世代非接触呼吸監視システム 🌊📡# CI/CD Test
