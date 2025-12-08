# CI/CD パイプライン

このプロジェクトのCI/CD（継続的インテグレーション/継続的デリバリー）システムの説明です。

## 📋 概要

GitHub Actionsを使用した自動テスト・ビルド・デプロイのパイプラインを提供します。

### ワークフロー構成

| ワークフロー | トリガー | 目的 |
|------------|---------|------|
| **CI Pipeline** (`ci.yml`) | Push/PR to main | コード品質チェック・テスト |
| **Deploy** (`deploy.yml`) | 手動実行 | 本番/ステージング環境へのデプロイ |

---

## 🔄 CI Pipeline (ci.yml)

### トリガー条件

- `main`ブランチへのPush
- `main`ブランチへのPull Request
- 手動実行（`workflow_dispatch`）

### 実行内容

#### 1. Backend Lint & Test
```yaml
実行環境: ubuntu-latest
Python: 3.11
サービス: PostgreSQL 15, Redis 7
```

**チェック項目:**
- ✅ Black（コードフォーマット）
- ✅ isort（import順序）
- ✅ Flake8（リンティング）
- ✅ pytest（単体テスト + カバレッジ）

**成果物:**
- カバレッジレポート（Codecovにアップロード）

#### 2. Frontend Lint & Build
```yaml
実行環境: ubuntu-latest
Node.js: 20 (LTS)
```

**チェック項目:**
- ✅ ESLint（リンティング）
- ✅ TypeScript型チェック
- ✅ Next.jsビルド

#### 3. Docker Build Test (mainブランチのみ)
```yaml
実行タイミング: mainへのPush時のみ
```

**チェック項目:**
- ✅ Backendイメージビルド
- ✅ Frontendイメージビルド

---

## 🚀 Deploy Pipeline (deploy.yml)

### トリガー条件

手動実行のみ（`workflow_dispatch`）

### 環境選択

- **production** - 本番環境
- **staging** - ステージング環境

### 実行内容

#### 1. Pre-Deployment Check
```yaml
実行環境: ubuntu-latest
```

**チェック項目:**
- ✅ 必須ファイルの存在確認
  - `docker-compose.yml`
  - `backend/requirements.txt`
  - `frontend/package.json`

#### 2. Deploy to Self-Hosted Server
```yaml
実行環境: self-hosted
前提条件: GitHubにself-hostedランナーを登録
```

**デプロイ手順:**
1. 💾 データベースバックアップ作成
2. 🛑 既存サービス停止
3. 📥 最新コードの取得
4. 🔨 Dockerイメージビルド
5. 🚀 サービス起動
6. 🔍 ヘルスチェック

#### 3. Rollback on Failure
```yaml
実行条件: デプロイ失敗時
```

**ロールバック手順:**
1. 📥 最新バックアップからリストア
2. 🔄 前バージョンで再起動

---

## 🛠️ ローカルでのCI/CD確認

### バックエンドテスト

```bash
cd backend

# Lintチェック
black --check app/ tests/
isort --check-only app/ tests/
flake8 app/ tests/

# テスト実行
pytest tests/ -v --cov=app
```

### フロントエンドテスト

```bash
cd frontend

# Lintチェック
npm run lint

# 型チェック
npm run type-check

# ビルド確認
npm run build
```

### Docker ビルドテスト

```bash
# バックエンド
docker build -t csi-backend:test ./backend

# フロントエンド
docker build -t csi-frontend:test ./frontend

# 統合テスト
docker-compose up -d
docker-compose ps
docker-compose down
```

---

## 📊 GitHub Actionsの確認方法

### ワークフロー実行状態の確認

1. GitHubリポジトリページを開く
2. **Actions** タブをクリック
3. 実行中/完了したワークフローを確認

### 手動デプロイの実行

1. GitHubリポジトリ → **Actions** タブ
2. 左サイドバーから **Deploy to Production** を選択
3. **Run workflow** ボタンをクリック
4. 環境を選択（production / staging）
5. **Run workflow** を実行

---

## ⚙️ Self-Hosted Runner の設定

Self-hosted環境でデプロイする場合は、GitHubにランナーを登録する必要があります。

### セットアップ手順

1. GitHubリポジトリ → **Settings** → **Actions** → **Runners**
2. **New self-hosted runner** をクリック
3. OSを選択（macOS / Linux / Windows）
4. 表示されるコマンドを実行してランナーをインストール

```bash
# Mac/Linuxの例
mkdir actions-runner && cd actions-runner
curl -o actions-runner-osx-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-osx-x64-2.311.0.tar.gz
tar xzf ./actions-runner-osx-x64-2.311.0.tar.gz
./config.sh --url https://github.com/YOUR_USERNAME/csi-web-platform --token YOUR_TOKEN
./run.sh
```

5. サービスとして登録（オプション）

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

---

## 🔐 環境変数とシークレット

### GitHubシークレットの設定

デプロイに必要なシークレットをGitHubに登録します。

1. GitHubリポジトリ → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** をクリック
3. 以下のシークレットを追加

| シークレット名 | 説明 | 必須 |
|--------------|------|-----|
| `DOCKER_USERNAME` | Docker Hubユーザー名 | オプション |
| `DOCKER_PASSWORD` | Docker Hubパスワード | オプション |

### 環境別の設定

**Production環境:**
- GitHubリポジトリ → **Settings** → **Environments**
- `production` 環境を作成
- 必要に応じて承認ルールを設定

**Staging環境:**
- `staging` 環境を作成

---

## 📈 カバレッジレポート

### Codecov統合（オプション）

Codecovを使ってカバレッジレポートを可視化できます。

1. [Codecov](https://codecov.io/)にサインアップ
2. リポジトリを連携
3. GitHubシークレットに`CODECOV_TOKEN`を追加

カバレッジバッジをREADME.mdに追加:
```markdown
[![codecov](https://codecov.io/gh/USERNAME/csi-web-platform/branch/main/graph/badge.svg)](https://codecov.io/gh/USERNAME/csi-web-platform)
```

---

## 🐛 トラブルシューティング

### CI/CDが失敗する場合

#### Backend テスト失敗
```bash
# ローカルでテスト実行
cd backend
pytest tests/ -v

# 依存関係の再インストール
pip install -r requirements.txt
```

#### Frontend ビルド失敗
```bash
# ローカルでビルド確認
cd frontend
npm ci
npm run build

# キャッシュクリア
rm -rf node_modules .next
npm install
```

#### Docker ビルド失敗
```bash
# ログ確認
docker-compose logs

# イメージの再ビルド
docker-compose build --no-cache
```

### Self-Hosted Runner接続エラー

```bash
# ランナーの状態確認
./run.sh

# サービスの再起動
sudo ./svc.sh restart

# ログ確認
tail -f _diag/Runner_*.log
```

---

## 🔄 ワークフローの改善

### CI速度の改善

- **キャッシュ活用**: `cache: 'pip'`, `cache: 'npm'`
- **並列実行**: 独立したジョブは並列実行
- **スコープ制限**: 変更のあったディレクトリのみテスト

### セキュリティ強化

- **シークレット管理**: 環境変数をGitHubシークレットに保存
- **承認フロー**: 本番デプロイ前に手動承認を要求
- **権限制限**: `permissions:` でGitHub Token権限を最小化

### 通知設定

- **Slackへの通知**: デプロイ成功/失敗をSlackに通知
- **メール通知**: GitHub設定でメール通知を有効化

---

## 📚 参考リンク

- [GitHub Actions公式ドキュメント](https://docs.github.com/ja/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Setup Python Action](https://github.com/actions/setup-python)
- [Setup Node Action](https://github.com/actions/setup-node)
