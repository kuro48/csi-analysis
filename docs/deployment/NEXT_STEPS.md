# 🔜 次のステップ（Mac Mini作業リスト）

> **作成日**: 2025-11-28
> **対象**: Mac Miniが手元に戻ってきた後の作業

---

## ✅ 完了済み（ローカル作業）

- ✅ Backend テスト環境構築（pytest, black, flake8）
- ✅ Frontend テスト環境構築（lint, type-check）
- ✅ GitHub Actions ワークフロー作成
- ✅ 自動デプロイスクリプト作成
- ✅ CI/CDドキュメント作成

---

## 📋 Mac Miniでの作業（優先度順）

### 🔴 必須作業

#### 1. GitHub Actions Self-hosted Runner セットアップ

**作業時間**: 約10分
**場所**: Mac Mini上

```bash
# 1. Runnerディレクトリ作成
mkdir -p ~/actions-runner && cd ~/actions-runner

# 2. GitHubページを開いてトークン取得
open https://github.com/kuro48/csi-analysis/settings/actions/runners/new

# 3. Runnerダウンロード（GitHubページに表示されるコマンドを実行）
# macOS Apple Silicon の場合:
curl -o actions-runner-osx-arm64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-osx-arm64-2.311.0.tar.gz

# 4. 解凍
tar xzf ./actions-runner-osx-arm64-*.tar.gz

# 5. Runner設定（GitHubのトークンを使用）
./config.sh --url https://github.com/kuro48/csi-analysis --token <YOUR_TOKEN>

# 設定内容:
# - Runner name: mac-mini-runner
# - Runner group: Default
# - Labels: self-hosted,macOS,ARM64
# - Work folder: _work

# 6. サービスとしてインストール（自動起動設定）
sudo ./svc.sh install
sudo ./svc.sh start

# 7. 状態確認
sudo ./svc.sh status
```

**確認方法**:
- GitHubリポジトリ: `Settings > Actions > Runners`
- Runnerが「Idle」（緑色）になっていればOK

---

#### 2. CI/CDパイプラインのテスト実行

**作業時間**: 約5分
**前提**: Self-hosted Runner セットアップ完了

```bash
# 1. ローカルリポジトリの最新化（Mac Mini上）
cd ~/Projects/csi-web-platform  # プロジェクトディレクトリ
git pull origin main

# 2. テスト用の小さな変更を追加
echo "# CI/CD Test" >> README.md
git add README.md
git commit -m "test: CI/CDパイプライン動作確認"
git push origin main

# 3. GitHub Actionsの実行確認
open https://github.com/kuro48/csi-analysis/actions

# 4. 実行ログを確認
# - Backend Test
# - Frontend Test
# - ZKP Circuit Test
# - Docker Build & Test
# - Deploy

# 5. デプロイ確認
curl http://localhost:8000/health
curl http://localhost:3000

# 6. 外部アクセス確認
open https://csi.kur048.com
open https://api.csi.kur048.com/docs
```

**確認ポイント**:
- [ ] 全ジョブが成功（緑色のチェックマーク）
- [ ] デプロイ後にサービスが正常起動
- [ ] 外部URLでアクセス可能

---

### 🟡 推奨作業

#### 3. Backendテストのローカル実行確認

```bash
cd ~/Projects/csi-web-platform/backend

# 依存関係インストール
pip install -r requirements.txt

# テスト実行
pytest tests/ -v --cov=app

# 期待される結果:
# - test_health.py: 2 passed
# - test_auth.py: 8 passed
# - Coverage: 70%以上
```

---

#### 4. Frontendテストのローカル実行確認

```bash
cd ~/Projects/csi-web-platform/frontend

# 依存関係インストール
npm install

# テスト実行
npm run test:ci

# 期待される結果:
# - ESLint: No errors
# - TypeScript: No type errors
```

---

### 🟢 オプション作業

#### 5. Cloudflare Tunnelの再確認

```bash
# Cloudflare Tunnelの状態確認
cloudflared tunnel list

# Tunnelが起動しているか確認
launchctl list | grep cloudflared

# Tunnelの再起動（必要な場合）
cloudflared service uninstall
cloudflared service install
```

---

#### 6. Mac Miniの永続化設定確認

```bash
# スリープ設定確認
pmset -g

# Docker Desktopの自動起動確認
# システム設定 > 一般 > ログイン項目 > Docker

# Cloudflare Tunnelの自動起動確認
launchctl list | grep cloudflared
```

---

## 🐛 トラブルシューティング

### Runner が「Offline」になっている

```bash
cd ~/actions-runner
sudo ./svc.sh status

# 停止している場合
sudo ./svc.sh start

# 再インストールが必要な場合
sudo ./svc.sh uninstall
sudo ./svc.sh install
sudo ./svc.sh start
```

### CI/CDが失敗する

```bash
# ローカルでテストを実行して確認
cd ~/Projects/csi-web-platform/backend
pytest tests/ -v

cd ~/Projects/csi-web-platform/frontend
npm run test:ci

# Dockerサービスの状態確認
docker-compose ps

# Dockerリソースのクリーンアップ
docker system prune -a
```

### デプロイ後にサービスが起動しない

```bash
# ログ確認
docker-compose logs backend
docker-compose logs frontend

# サービス再起動
docker-compose restart

# 完全な再デプロイ
./scripts/redeploy.sh
```

---

## 📊 完了チェックリスト

作業完了後、以下を確認：

- [ ] GitHub Actions Runner が「Idle」状態
- [ ] mainブランチへのpushでCI/CDが自動実行される
- [ ] 全テストが成功する
- [ ] デプロイが自動で完了する
- [ ] https://csi.kur048.com でアクセス可能
- [ ] https://api.csi.kur048.com/docs でAPI確認可能
- [ ] Mac Mini再起動後もサービスが自動起動

---

## 📚 参考ドキュメント

- **CI/CDセットアップ詳細**: `docs/deployment/CI_CD_SETUP.md`
- **Mac Miniデプロイガイド**: `docs/deployment/SIMPLE_DEPLOY.md`
- **GitHub Actions公式**: https://docs.github.com/en/actions/hosting-your-own-runners

---

## 📝 作業後の報告

作業完了後、以下を確認して記録してください：

```bash
# 1. Runnerの状態
cd ~/actions-runner
sudo ./svc.sh status

# 2. 最新のCI/CD実行結果
open https://github.com/kuro48/csi-analysis/actions

# 3. サービスの状態
docker-compose ps

# 4. 外部アクセス確認
curl https://csi.kur048.com
curl https://api.csi.kur048.com/health
```

---

**🎯 目標**: Mac Miniが手元に戻ったら、上記の作業を順番に実行して、完全自動化されたCI/CDパイプラインを稼働させる。

**⏱️ 推定作業時間**: 約30分（必須作業のみ）
