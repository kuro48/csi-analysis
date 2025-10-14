# クイックスタートガイド

このガイドでは、CSI Webプラットフォームを5分で起動して動作確認する手順を説明します。

---

## ⚡ 5分でスタート

### 前提条件

以下のソフトウェアがインストールされていることを確認してください：

- **Docker**: 20.0以上
- **Docker Compose**: 2.0以上

確認コマンド：
```bash
docker --version
docker-compose --version
```

---

## 🚀 ステップ1: システム起動（1分）

### 1.1 リポジトリクローン

```bash
git clone https://github.com/kuro48/csi-web-platform.git
cd csi-web-platform
```

### 1.2 自動起動スクリプト実行

```bash
./start.sh
```

起動スクリプトが以下を自動実行します：
- ✅ Docker・Docker Composeのチェック
- ✅ 環境設定ファイルのコピー
- ✅ 既存コンテナの停止（オプション）
- ✅ イメージビルドとサービス起動
- ✅ データベース・Redis接続確認
- ✅ API・フロントエンド動作確認

**起動には初回3〜5分かかります（イメージダウンロード含む）**

---

## ✅ ステップ2: 動作確認（1分）

### 2.1 サービス状態確認

```bash
docker-compose ps
```

**期待される出力**:
```
NAME           STATUS
csi_backend    Up (healthy)
csi_frontend   Up
csi_postgres   Up (healthy)
csi_redis      Up (healthy)
csi_ipfs       Up (healthy)
csi_ganache    Up
```

### 2.2 Webアクセス

以下のURLにブラウザでアクセス：

| サービス | URL | 説明 |
|---------|-----|------|
| 🌐 **フロントエンド** | http://localhost:3000 | Webアプリケーション |
| 🔧 **API仕様書** | http://localhost:8000/docs | Swagger UI |
| 📊 **バックエンドAPI** | http://localhost:8000/health | ヘルスチェック |

---

## 🔐 ステップ3: ログイン（1分）

### 3.1 フロントエンドにアクセス

1. ブラウザで http://localhost:3000 を開く
2. ログインページが表示される

### 3.2 管理者アカウントでログイン

```
ユーザー名: admin
パスワード: admin123
```

**ログイン成功後、ダッシュボードが表示されます！**

---

## 📊 ステップ4: データ確認（2分）

### 4.1 デバイス登録

1. サイドバーから「デバイス管理」を選択
2. 「デバイス登録」ボタンをクリック
3. 以下の情報を入力：
   - **デバイスID**: `test_device_001`
   - **デバイス名**: `テストデバイス`
   - **デバイスタイプ**: `ESP32`
   - **場所**: `テストラボ`
4. 「登録」ボタンをクリック

### 4.2 デバイス一覧確認

登録したデバイスが一覧に表示されることを確認します。

---

## 🧪 ステップ5: API テスト（1分）

### 5.1 ヘルスチェック

```bash
curl http://localhost:8000/health
```

**期待される出力**:
```json
{
  "status": "healthy",
  "service": "CSI Respiratory Monitoring System",
  "version": "2.5.0"
}
```

### 5.2 認証テスト

```bash
curl -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

**JWTトークンが返却されれば成功です！**

---

## ⛓️ ステップ6: ブロックチェーン確認（1分）

### 6.1 Ganache接続確認

```bash
curl -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}'
```

**期待される出力**:
```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": "1337"
}
```

### 6.2 スマートコントラクト確認

```bash
cat backend/contracts/build/CSIDataRegistry.json | grep "address"
```

コントラクトアドレスが表示されることを確認します。

---

## 🎉 完了！

これでCSI Webプラットフォームの基本セットアップが完了しました。

### 起動中のサービス

| サービス | ポート | 用途 |
|---------|-------|------|
| Frontend | 3000 | Webアプリケーション |
| Backend API | 8000 | RESTful API |
| PostgreSQL | 5432 | メインデータベース |
| Redis | 6379 | キャッシュ・セッション |
| IPFS | 5001, 8080 | 分散ストレージ |
| Ganache | 8545 | ローカルブロックチェーン |

---

## 📚 次のステップ

### 初心者向け
1. [README.md](../README.md) - システム全体の概要
2. [API_REFERENCE.md](./API_REFERENCE.md) - API仕様
3. [SETUP_BLOCKCHAIN.md](./SETUP_BLOCKCHAIN.md) - ブロックチェーン詳細設定

### 開発者向け
1. CSIデータのアップロード
2. 可視化グラフの確認
3. ブロックチェーン記録の検証
4. カスタム機能の実装

---

## 🔧 よく使うコマンド

### サービス管理

```bash
# システム起動
./start.sh

# サービス停止
docker-compose down

# サービス再起動
docker-compose restart

# ログ確認
docker-compose logs -f backend
docker-compose logs -f frontend

# システム状態確認
./scripts/health_check.sh
```

### データベース操作

```bash
# PostgreSQL接続
docker-compose exec postgres psql -U csi_user -d csi_system

# テーブル一覧
\dt

# 終了
\q
```

### ブロックチェーン操作

```bash
# スマートコントラクトデプロイ
python backend/contracts/deploy_contract.py

# ブロックチェーン状態確認
docker-compose logs ganache
```

---

## ⚠️ トラブルシューティング

### 問題1: ポート競合エラー

**症状**: `port is already allocated`

**解決方法**:
```bash
# 使用中のポートを確認
lsof -i :3000
lsof -i :8000

# コンテナを完全停止
docker-compose down
```

### 問題2: コンテナが起動しない

**症状**: `container exited with code 1`

**解決方法**:
```bash
# ログを確認
docker-compose logs [service_name]

# 完全クリーンアップ
docker-compose down --volumes --remove-orphans
./start.sh
```

### 問題3: フロントエンドに接続できない

**症状**: `ERR_CONNECTION_REFUSED`

**解決方法**:
```bash
# フロントエンドログ確認
docker-compose logs frontend

# フロントエンド再起動
docker-compose restart frontend
```

---

## 📞 ヘルプ

問題が解決しない場合：

1. **ログ確認**: `docker-compose logs -f`
2. **システム状態**: `./scripts/health_check.sh`
3. **GitHub Issues**: https://github.com/kuro48/csi-web-platform/issues
4. **ドキュメント**: `docs/` フォルダ内

---

## ✅ チェックリスト

起動確認用のチェックリスト：

- [ ] Docker・Docker Composeがインストール済み
- [ ] リポジトリをクローン済み
- [ ] `./start.sh`を実行済み
- [ ] 全コンテナが起動中（`docker-compose ps`で確認）
- [ ] http://localhost:3000 にアクセス可能
- [ ] 管理者アカウントでログイン成功
- [ ] API ヘルスチェックが成功
- [ ] Ganacheが応答

すべてにチェックが入れば、システムは正常に動作しています！

---

**最終更新**: 2025-10-14
**バージョン**: 2.0.0
**想定時間**: 5〜10分
