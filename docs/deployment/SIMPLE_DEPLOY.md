# Mac Miniデプロイガイド（研究環境向け）

Mac Miniを使った**研究用・検証用**の簡単なデプロイ方法です。

---

## 💻 Mac Miniセットアップ

### ✨ 特徴
- **コスト**: 0円（既存ハードウェア活用）
- **難易度**: ⭐（最も簡単）
- **所要時間**: 5分
- **用途**: 研究室内サーバー、24時間稼働可能

### 前提条件
- Mac Mini（Intel/Apple Silicon両対応）
- macOS 12 (Monterey) 以上
- 研究室ネットワーク接続

### 手順（5分で完了）

#### 1. Docker Desktop for Mac インストール
```bash
# Homebrewでインストール（推奨）
brew install --cask docker

# または公式サイトからダウンロード
# https://www.docker.com/products/docker-desktop/
```

初回起動時、Docker Desktopアプリを開いて利用規約に同意してください。

#### 2. プロジェクトセットアップ
```bash
# ホームディレクトリまたは任意の場所で
cd ~/Projects  # または好きなディレクトリ

# リポジトリクローン
git clone https://github.com/kuro48/csi-web-platform.git
cd csi-web-platform

# 起動（完了！）
./start.sh
```

#### 3. アクセス確認

**研究室内からアクセス**:
```bash
# Mac MiniのIPアドレス確認
ifconfig | grep "inet " | grep -v 127.0.0.1

# 表示されたIPアドレスでアクセス
# 例: http://192.168.1.100:3000
```

- Frontend: `http://Mac-MiniのIP:3000`
- Backend API: `http://Mac-MiniのIP:8000`
- API Docs: `http://Mac-MiniのIP:8000/docs`

### Mac Mini固有の設定

#### スリープ無効化（24時間稼働用）
```bash
# ディスプレイスリープのみ許可、コンピュータスリープは無効
sudo pmset -a displaysleep 10 sleep 0 disksleep 0

# 設定確認
pmset -g
```

または「システム設定」→「ロック画面」→「ディスプレイをオフにする」で手動設定

#### 固定IPアドレス設定（推奨）
1. 「システム設定」→「ネットワーク」
2. 使用中の接続（Wi-FiまたはEthernet）を選択
3. 「詳細」→「TCP/IP」
4. 「IPv4の構成」を「DHCPリースを使用」から「手動」に変更
5. IPアドレス、サブネットマスク、ルーターを設定

#### 自動起動設定（オプション）

Mac Mini再起動時に自動でサービスを起動：

```bash
# Launchd設定ファイル作成
cat > ~/Library/LaunchAgents/com.csi-web-platform.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.csi-web-platform</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ~/Projects/csi-web-platform && ./start.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/csi-web-platform.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/csi-web-platform.error.log</string>
</dict>
</plist>
EOF

# パスを実際のプロジェクト場所に変更してください

# Launchd登録
launchctl load ~/Library/LaunchAgents/com.csi-web-platform.plist

# 確認
launchctl list | grep csi-web-platform
```

---

## 🌐 外部アクセス設定

Mac Miniを外部からアクセス可能にする方法を4つ紹介します。

### 🌟 方法1: ngrok（最も簡単・1分で完了）

**特徴**:
- ✅ 設定不要、1コマンドで外部公開
- ✅ HTTPS自動対応
- ✅ 無料版で十分
- ⚠️ 無料版は起動のたびにURLが変わる
- ⚠️ 帯域制限あり（無料版: 1GB/月）

**手順**:
```bash
# 1. ngrokインストール
brew install ngrok

# 2. Mac Miniでサービス起動（別ターミナル）
cd ~/Projects/csi-web-platform
./start.sh

# 3. ngrokで公開
ngrok http 3000

# 4. 表示されたURLをコピーして共有
# 例: https://xxxx-xxxx-xxxx.ngrok-free.app
```

**使い分け**:
- デモ・プレゼン用に一時的に公開
- 研究室外から短期間アクセスしたい
- とにかく今すぐ外部公開したい

**有料版（推奨）**: $8/月で固定URL、帯域無制限

---

### 🔒 方法2: Cloudflare Tunnel（無料・安定・推奨）

**特徴**:
- ✅ 完全無料、帯域無制限
- ✅ 固定URL（カスタムドメイン可）
- ✅ DDoS保護、CDN機能
- ✅ HTTPS自動対応
- ✅ 複数サービス同時公開可能
- ⚠️ 初回設定にCloudflareアカウント必要

**手順**:

#### 1. Cloudflare Tunnelインストール
```bash
# cloudflaredインストール
brew install cloudflare/cloudflare/cloudflared

# Cloudflareログイン（ブラウザが開く）
cloudflared tunnel login
```

#### 2. トンネル作成
```bash
# トンネル作成
cloudflared tunnel create csi-web-platform

# 設定ファイル作成
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: csi-web-platform
credentials-file: /Users/$(whoami)/.cloudflared/<tunnel-id>.json

ingress:
  # フロントエンド
  - hostname: csi.your-domain.com
    service: http://localhost:3000
  # バックエンドAPI
  - hostname: api.csi.your-domain.com
    service: http://localhost:8000
  # その他すべて
  - service: http_status:404
EOF
```

#### 3. DNS設定
```bash
# トンネルとドメインを紐付け
cloudflared tunnel route dns csi-web-platform csi.your-domain.com
cloudflared tunnel route dns csi-web-platform api.csi.your-domain.com
```

#### 4. トンネル起動
```bash
# Mac Miniでサービス起動
cd ~/Projects/csi-web-platform
./start.sh

# 別ターミナルでトンネル起動
cloudflared tunnel run csi-web-platform

# または自動起動設定
cloudflared service install
```

**アクセス**:
- Frontend: `https://csi.your-domain.com`
- Backend API: `https://api.csi.your-domain.com`

**使い分け**:
- 長期運用したい
- 研究室外から常時アクセスしたい
- カスタムドメインを使いたい
- セキュリティ重視

---

### 🔐 方法3: Tailscale（VPN・最もセキュア）

**特徴**:
- ✅ VPNで安全なプライベートアクセス
- ✅ 完全無料（個人利用）
- ✅ 複数デバイス間で安全に接続
- ✅ 認証されたユーザーのみアクセス可能
- ⚠️ 各デバイスにTailscaleインストール必要

**手順**:

#### 1. Mac MiniにTailscaleインストール
```bash
# Tailscaleインストール
brew install --cask tailscale

# Tailscale起動（ブラウザでログイン）
open /Applications/Tailscale.app
```

#### 2. アクセスしたいデバイスにもインストール
```bash
# Windows/Mac/Linux/iOS/Android対応
# https://tailscale.com/download からダウンロード
```

#### 3. Mac MiniのTailscale IPを確認
```bash
# Tailscale IPアドレス確認
tailscale ip -4

# 例: 100.x.x.x
```

#### 4. アクセス
```bash
# Tailscaleネットワーク経由でアクセス
http://100.x.x.x:3000  # Frontend
http://100.x.x.x:8000  # Backend
```

**使い分け**:
- セキュリティ最重視
- 研究室メンバーのみアクセス許可したい
- VPN経由で安全にアクセスしたい
- 複数の研究室拠点から接続したい

---

### 🌐 方法4: ポートフォワーディング（上級者向け）

**特徴**:
- ✅ 完全に自分で制御
- ✅ 追加コストなし
- ⚠️ ルーター設定が必要
- ⚠️ グローバルIPアドレスが必要
- ⚠️ セキュリティリスク高い
- ⚠️ 大学・研究室ネットワークでは通常不可

**手順**（研究室ネットワークでは通常実行不可）:

1. **ルーター管理画面にアクセス**
2. **ポートフォワーディング設定**
   - 外部ポート 3000 → Mac Mini IP:3000（Frontend）
   - 外部ポート 8000 → Mac Mini IP:8000（Backend）
3. **グローバルIPアドレス確認**
   ```bash
   curl ifconfig.me
   ```
4. **アクセス**
   - `http://グローバルIP:3000`

**⚠️ 注意**:
- 研究室ネットワークでは通常管理者権限が必要
- セキュリティリスクが高いため非推奨
- Cloudflare TunnelやTailscaleを推奨

---

## 📊 外部アクセス方法の比較

| 方法 | 難易度 | 費用 | セキュリティ | 安定性 | おすすめ用途 |
|------|--------|------|------------|--------|------------|
| **ngrok** | ⭐ | 無料（制限あり） | 中 | 中 | デモ・一時公開 |
| **Cloudflare Tunnel** | ⭐⭐ | 無料 | 高 | 高 | **長期運用（最推奨）** |
| **Tailscale** | ⭐⭐ | 無料 | 最高 | 高 | **セキュア接続** |
| **ポートフォワーディング** | ⭐⭐⭐⭐ | 無料 | 低 | 中 | 非推奨 |

---

## 🎯 推奨構成

### 研究用途（推奨）
→ **Cloudflare Tunnel** または **Tailscale**

### デモ・プレゼン用
→ **ngrok**（有料版推奨: $8/月で固定URL）

### 研究室メンバーのみアクセス
→ **Tailscale**（VPNで安全）

### 研究室内のみアクセス（外部公開なし）

設定不要。研究室ネットワーク内からIPアドレスでアクセス：

```bash
# Mac MiniのIPアドレス確認
ifconfig | grep "inet " | grep -v 127.0.0.1

# 研究室内の他のPCから
http://192.168.x.x:3000
```

---

## ✨ Mac Miniのメリット

- ✅ **低消費電力**: 24時間稼働でも電気代月数百円
- ✅ **静音**: 研究室に置いても静か
- ✅ **安定性**: macOSの安定したDocker環境
- ✅ **物理アクセス**: トラブル時にすぐ対応可能
- ✅ **コスト0円**: 追加費用なし

---

## ⚠️ 注意点

- 研究室ネットワークのファイアウォール設定が必要な場合あり
- Mac Miniの電源が切れるとサービス停止
- 外部公開する場合はセキュリティに注意

---

## 📝 まとめ

### 研究室内のみ使用
→ **そのまま使用**（設定不要）

### 今すぐ外部公開したい
→ **ngrok**（1分で完了）

### 長期運用したい
→ **Cloudflare Tunnel**（無料・安定）

### セキュリティ重視
→ **Tailscale**（VPN・研究室メンバーのみ）

---

**🎉 Mac Miniなら5分で起動、0円で運用できます！**
