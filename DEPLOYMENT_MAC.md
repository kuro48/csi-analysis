# CSI Analysis - Mac 常時稼働設定ガイド

このガイドでは、Mac上でCSI Analysisプロジェクトを常時稼働させるための設定を説明します。

## 🎯 概要

以下のサービスが自動的に起動・監視されます：
- Docker Compose（全コンテナ）
- Cloudflare Tunnel
- 定期ヘルスチェック・監視

## 📋 設定済みコンポーネント

### 1. Cloudflare Tunnel（改善済み）
**場所:** `~/Library/LaunchAgents/com.cloudflare.cloudflared.plist`

**機能:**
- システム起動時に自動起動
- クラッシュ時の自動再起動
- ネットワーク接続復旧時の自動再接続
- 30秒の再試行間隔（以前は5秒）

**設定内容:**
- トンネル名: `csi-web-platform`
- フロントエンド: https://csi.kur048.com → localhost:3000
- バックエンドAPI: https://api.csi.kur048.com → localhost:8000

### 2. Docker Compose自動起動
**場所:** `~/Library/LaunchAgents/com.csi-analysis.docker.plist`

**機能:**
- システム起動時にDocker Composeを起動
- 5分ごとに起動確認（既に起動中の場合は何もしない）

**含まれるコンテナ:**
- PostgreSQL（データベース）
- Redis（キャッシュ）
- Backend（FastAPI）
- Frontend（Next.js）
- IPFS
- Ganache（開発用ブロックチェーン）

### 3. 自動監視・復旧システム
**場所:** `~/Library/LaunchAgents/com.csi-analysis.monitor.plist`

**機能:**
- 5分ごとにシステムをチェック
- 問題検出時に自動復旧を試行
- 全ての操作をログに記録

## 🚀 セットアップ手順

### 1. 現在のサービスを停止

```bash
# Cloudflare Tunnelを一旦停止
pkill -f "cloudflared tunnel"

# 既存のlaunchd設定をアンロード
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist 2>/dev/null
```

### 2. 新しい設定を適用

```bash
# Cloudflare Tunnelをロード
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist

# Docker自動起動をロード
launchctl load ~/Library/LaunchAgents/com.csi-analysis.docker.plist

# 監視スクリプトをロード
launchctl load ~/Library/LaunchAgents/com.csi-analysis.monitor.plist
```

### 3. 設定確認

```bash
# サービスが起動しているか確認
launchctl list | grep -E "cloudflare|csi-analysis"

# プロセス確認
ps aux | grep cloudflared
docker-compose ps
```

## 🔍 監視とメンテナンス

### ヘルスチェックの実行

```bash
# 手動でヘルスチェックを実行
~/csi-analysis/scripts/health-check.sh
```

**チェック項目:**
- Dockerコンテナの起動状態（6/6）
- Cloudflare Tunnelプロセス
- Tunnel経由のアクセス可能性
- バックエンドAPI (/health)
- フロントエンド
- PostgreSQL接続
- Redis接続

### ログの確認

```bash
# Cloudflare Tunnelログ
tail -f ~/Library/Logs/com.cloudflare.cloudflared.out.log
tail -f ~/Library/Logs/com.cloudflare.cloudflared.err.log

# Docker起動ログ
tail -f ~/Library/Logs/csi-docker.out.log
tail -f ~/Library/Logs/csi-docker.err.log

# 監視スクリプトログ
tail -f ~/Library/Logs/csi-monitor.log

# ヘルスチェックログ
tail -f ~/Library/Logs/csi-health-check.log
```

### トラブルシューティング

#### Cloudflare Tunnelが切れる場合

```bash
# Tunnelの状態確認
cloudflared tunnel info csi-web-platform

# 手動再起動
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist

# ログ確認
tail -50 ~/Library/Logs/com.cloudflare.cloudflared.err.log
```

#### Dockerコンテナが起動しない場合

```bash
# コンテナ状態確認
docker-compose ps

# ログ確認
docker-compose logs --tail=50

# 手動再起動
cd ~/csi-analysis
docker-compose down
docker-compose up -d
```

## 🔧 設定のカスタマイズ

### 監視間隔の変更

`~/Library/LaunchAgents/com.csi-analysis.monitor.plist`の`StartInterval`を編集：
```xml
<key>StartInterval</key>
<integer>300</integer>  <!-- 秒単位。300 = 5分 -->
```

変更後は再読み込み：
```bash
launchctl unload ~/Library/LaunchAgents/com.csi-analysis.monitor.plist
launchctl load ~/Library/LaunchAgents/com.csi-analysis.monitor.plist
```

### Cloudflare Tunnel再試行間隔の変更

`~/Library/LaunchAgents/com.cloudflare.cloudflared.plist`の`ThrottleInterval`を編集：
```xml
<key>ThrottleInterval</key>
<integer>30</integer>  <!-- 秒単位 -->
```

## 📊 システム要件

- macOS 10.14以降
- Docker Desktop for Mac
- Cloudflare Tunnel (cloudflared)
- 十分なディスク容量（Docker volumeとログ用）

## 🛡️ セキュリティ

- Cloudflare認証情報: `~/.cloudflared/`（権限: 600）
- データベース認証情報: 環境変数または`.env`ファイル
- ログファイルには機密情報を含めないように設定済み

## 🔄 アップデート手順

プロジェクトをアップデートする際：

```bash
cd ~/csi-analysis
git pull

# コンテナを再ビルド
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 監視スクリプトが自動的に状態を確認
```

## 📞 サポート

問題が発生した場合：
1. ログファイルを確認
2. ヘルスチェックスクリプトを実行
3. 各サービスのステータスを確認
4. 必要に応じて手動で再起動

---

**最終更新:** 2025-12-02
**バージョン:** 1.0
