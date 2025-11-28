# CI/CDセットアップガイド

Mac Mini上で動作するGitHub Actions Self-hosted Runnerを使用したCI/CDパイプラインの構築ガイドです。

---

## 📋 概要

### CI/CDパイプライン構成

```
git push origin main
  ↓
GitHub Actions（トリガー）
  ↓
Mac Mini（Self-hosted Runner）
  ├─ 1. Backend Test（pytest, black, flake8）
  ├─ 2. Frontend Test（lint, type-check）
  ├─ 3. ZKP Circuit Test（snarkjs）
  ├─ 4. Docker Build & Test
  └─ 5. Auto Deploy（docker-compose restart）
  ↓
Cloudflare Tunnel経由で公開
  - Frontend: https://csi.kur048.com
  - Backend API: https://api.csi.kur048.com
```

### 技術スタック

| 項目 | 技術 |
|------|------|
| CI/CD | GitHub Actions + Self-hosted Runner |
| Backend Test | pytest, black, isort, flake8, mypy |
| Frontend Test | ESLint, TypeScript type check |
| ZKP Test | snarkjs（回路コンパイル確認） |
| Container | Docker + Docker Compose |
| Deploy | Mac Mini（常時稼働） |

---

## 🚀 セットアップ手順

### 前提条件

- Mac Mini（常時稼働）
- Docker Desktop for Mac インストール済み
- Cloudflare Tunnel 設定済み
- GitHubリポジトリへのアクセス権

---

### ステップ1: Mac MiniにSelf-hosted Runnerをセットアップ

#### 1-1. GitHubリポジトリでRunner登録ページを開く

```bash
# Mac Mini上で実行
open https://github.com/kuro48/csi-analysis/settings/actions/runners/new
```

#### 1-2. Runnerダウンロード・セットアップ

GitHubページに表示される指示に従います：

```bash
# Runnerディレクトリ作成
mkdir -p ~/actions-runner && cd ~/actions-runner

# Runner をダウンロード（GitHub表示のコマンドを使用）
# macOS Apple Silicon の場合の例:
curl -o actions-runner-osx-arm64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-osx-arm64-2.311.0.tar.gz

# 展開
tar xzf ./actions-runner-osx-arm64-*.tar.gz

# Runner設定（GitHubページに表示されるトークンを使用）
./config.sh --url https://github.com/kuro48/csi-analysis --token <YOUR_TOKEN>
```

**設定時の入力内容**:
- **Runner name**: `mac-mini-runner`
- **Runner group**: `Default`
- **Labels**: `self-hosted,macOS,ARM64`（自動設定）
- **Work folder**: `_work`

#### 1-3. Runnerをサービスとして登録

```bash
# Runnerをサービスとしてインストール
sudo ./svc.sh install

# サービス起動
sudo ./svc.sh start

# 状態確認
sudo ./svc.sh status
```

**確認**: GitHubリポジトリの `Settings > Actions > Runners` で、Runnerが「Idle」状態になっていることを確認。

---

### ステップ2: テスト環境のセットアップ

#### 2-1. Backendテスト環境

```bash
cd backend

# 依存関係インストール
pip install -r requirements.txt

# テスト実行（ローカル確認）
pytest tests/ -v

# コード品質チェック
black --check app/ tests/
isort --check-only app/ tests/
flake8 app/ tests/
```

#### 2-2. Frontendテスト環境

```bash
cd frontend

# 依存関係インストール
npm install

# テスト実行（ローカル確認）
npm run lint
npm run type-check
npm run build
```

#### 2-3. ZKP回路テスト環境

```bash
cd zkp

# 依存関係インストール
npm install

# 回路コンパイル確認
npm run compile:csi_selector

# Trusted Setup確認
npm run setup:csi_selector
```

---

### ステップ3: GitHub Actionsワークフロー確認

ワークフローファイル: `.github/workflows/ci-cd.yml`

**トリガー条件**:
- `main`ブランチへのpush
- 手動実行（`workflow_dispatch`）

**実行内容**:
1. Backend Test
2. Frontend Test
3. ZKP Circuit Test
4. Docker Build & Test
5. Auto Deploy

---

## 📊 使い方

### 通常のデプロイフロー

```bash
# 1. 開発ブランチで作業
git checkout -b feature/new-feature
# ... コーディング ...

# 2. コミット＆プッシュ
git add .
git commit -m "Add new feature"
git push origin feature/new-feature

# 3. Pull Requestを作成（オプション）

# 4. mainブランチにマージ
git checkout main
git merge feature/new-feature
git push origin main

# ↓ 自動的にCI/CDパイプラインが起動
# ↓ テスト → ビルド → デプロイ
# ↓ https://csi.kur048.com に自動反映
```

### 手動でワークフロー実行

```bash
# GitHubリポジトリページで:
# Actions → CI/CD Pipeline → Run workflow
```

### ローカルでテスト実行

```bash
# Backendテスト
cd backend && pytest tests/ -v

# Frontendテスト
cd frontend && npm run test:ci

# すべてのテストを実行
./scripts/run_all_tests.sh  # TODO: このスクリプトを後で作成
```

---

## 🔍 モニタリング

### GitHub Actions ログ確認

```bash
# GitHubリポジトリページで:
# Actions → 最新のワークフロー実行を選択 → ログ表示
```

### Mac Mini上のログ確認

```bash
# Runnerサービスログ
sudo journalctl -u actions.runner.*

# Dockerサービスログ
docker-compose logs -f backend
docker-compose logs -f frontend

# デプロイログ
tail -f /tmp/deploy.log  # スクリプト内でログ出力する場合
```

### サービス状態確認

```bash
# Runnerサービス
sudo ./svc.sh status

# Dockerサービス
docker-compose ps

# ヘルスチェック
curl http://localhost:8000/health
curl http://localhost:3000
```

---

## 🛠️ トラブルシューティング

### 問題1: Runnerがオフライン

**症状**: GitHubでRunnerが「Offline」表示

**解決方法**:
```bash
# Mac Mini上で
cd ~/actions-runner
sudo ./svc.sh status

# サービスが停止している場合
sudo ./svc.sh start

# Mac Mini再起動後も自動起動しない場合
sudo ./svc.sh install  # 再インストール
```

### 問題2: テストが失敗する

**症状**: CI/CDパイプラインでテストが失敗

**解決方法**:
```bash
# ローカルで同じテストを実行して確認
cd backend && pytest tests/ -v
cd frontend && npm run test:ci

# 依存関係を再インストール
pip install -r requirements.txt --force-reinstall
npm ci  # package-lock.jsonから厳密にインストール
```

### 問題3: デプロイが失敗する

**症状**: Deploy jobが失敗

**解決方法**:
```bash
# Mac Mini上で手動デプロイを試す
cd ~/actions-runner/_work/csi-analysis/csi-analysis
./scripts/redeploy.sh

# Dockerサービスのログ確認
docker-compose logs

# Dockerリソースのクリーンアップ
docker system prune -a
```

### 問題4: ZKP回路テストが失敗

**症状**: ZKP Circuit Testsが失敗

**解決方法**:
```bash
# ZKP回路を再コンパイル
cd zkp
npm run compile:csi_selector
npm run setup:csi_selector

# ビルドファイルが存在するか確認
ls -la circuits/build/csi_selector_js/
ls -la circuits/build/csi_selector_final.zkey
```

---

## 📝 メンテナンス

### 定期的な作業

#### 週次
- [ ] GitHubActionsログの確認
- [ ] デプロイ成功率の確認
- [ ] Mac Miniのディスク容量確認

#### 月次
- [ ] Dockerイメージのクリーンアップ
- [ ] テストカバレッジの確認
- [ ] 依存関係のアップデート確認

### Dockerクリーンアップ

```bash
# 未使用イメージの削除
docker image prune -a

# 未使用ボリュームの削除
docker volume prune

# すべて削除（注意！）
docker system prune -a --volumes
```

### Runner のアップデート

```bash
cd ~/actions-runner

# サービス停止
sudo ./svc.sh stop

# 新しいバージョンをダウンロード
# （GitHubのRunnerページで最新版を確認）

# サービス再起動
sudo ./svc.sh start
```

---

## 🔐 セキュリティ

### 重要な注意事項

- **Secrets管理**: GitHub SecretsにDB パスワードやAPIキーを保存
- **Runner権限**: Mac Mini上のRunnerは最小限の権限で実行
- **ネットワーク**: Mac Miniのファイアウォール設定を確認
- **ログ監視**: 不正アクセスの兆候を定期的に確認

### GitHub Secrets設定

```bash
# GitHubリポジトリページで:
# Settings → Secrets and variables → Actions → New repository secret

# 設定するSecret（必要に応じて）:
# - DATABASE_PASSWORD
# - JWT_SECRET_KEY
# - REDIS_PASSWORD
```

---

## 📚 参考リンク

- [GitHub Actions Self-hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [Docker Compose](https://docs.docker.com/compose/)
- [pytest Documentation](https://docs.pytest.org/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)

---

## 🎉 完了チェックリスト

セットアップ完了時の確認項目：

- [ ] Mac Mini Self-hosted Runner が「Idle」状態
- [ ] Backendテストがローカルで成功
- [ ] Frontendテストがローカルで成功
- [ ] ZKP回路がコンパイル済み
- [ ] Docker Composeが正常に起動
- [ ] Cloudflare Tunnelが動作中
- [ ] mainブランチへのpushでCI/CDが自動実行される
- [ ] デプロイ後にhttps://csi.kur048.comでアクセス可能

---

**🔧 後日実施**: Mac Miniが手元に戻ったら、Self-hosted Runnerのセットアップ（ステップ1）を実行してください。
