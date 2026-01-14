#!/bin/bash

# GitHub Actions Self-Hosted Runner セットアップスクリプト
# Mac Mini用

set -e

echo "🚀 GitHub Actions Self-Hosted Runner セットアップ"
echo "=================================================="
echo ""

# カラーコード
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 必要な環境変数のチェック
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}❌ エラー: GITHUB_TOKEN環境変数が設定されていません${NC}"
    echo ""
    echo "GitHubの設定手順："
    echo "1. GitHub リポジトリ → Settings → Actions → Runners"
    echo "2. 'New self-hosted runner' をクリック"
    echo "3. macOS を選択"
    echo "4. 表示されるトークンをコピー"
    echo ""
    echo "その後、以下のコマンドを実行してください："
    echo "export GITHUB_TOKEN='your-token-here'"
    echo "./scripts/setup-runner.sh"
    exit 1
fi

# リポジトリ情報の取得
REPO_OWNER=$(git config --get remote.origin.url | sed -n 's#.*github.com[:/]\([^/]*\)/.*#\1#p')
REPO_NAME=$(git config --get remote.origin.url | sed -n 's#.*github.com[:/][^/]*/\([^.]*\).*#\1#p')

if [ -z "$REPO_OWNER" ] || [ -z "$REPO_NAME" ]; then
    echo -e "${RED}❌ エラー: GitHubリポジトリ情報を取得できませんでした${NC}"
    echo "このスクリプトはGitリポジトリ内で実行してください"
    exit 1
fi

echo -e "${GREEN}📍 リポジトリ: $REPO_OWNER/$REPO_NAME${NC}"
echo ""

# Runnerディレクトリの設定
RUNNER_DIR="$HOME/actions-runner"

# 既存のRunnerをチェック
if [ -d "$RUNNER_DIR" ]; then
    echo -e "${YELLOW}⚠️  既存のRunnerディレクトリが見つかりました: $RUNNER_DIR${NC}"
    read -p "削除して再インストールしますか？ (y/N): " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        # Runnerサービスを停止
        if [ -f "$RUNNER_DIR/svc.sh" ]; then
            echo "🛑 Runnerサービスを停止中..."
            cd "$RUNNER_DIR"
            sudo ./svc.sh stop || true
            sudo ./svc.sh uninstall || true
        fi
        echo "🗑️  既存のディレクトリを削除中..."
        rm -rf "$RUNNER_DIR"
    else
        echo "セットアップを中止しました"
        exit 0
    fi
fi

# Runnerディレクトリの作成
echo "📁 Runnerディレクトリを作成中..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

# Runner バージョンの取得（最新版）
echo "🔍 最新のRunner バージョンを確認中..."
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/')

if [ -z "$RUNNER_VERSION" ]; then
    echo -e "${RED}❌ エラー: Runner バージョンを取得できませんでした${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 最新バージョン: v$RUNNER_VERSION${NC}"

# Mac用Runner のダウンロード
RUNNER_FILE="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_FILE}"

echo "📥 GitHub Actions Runner をダウンロード中..."
echo "URL: $RUNNER_URL"
curl -o "$RUNNER_FILE" -L "$RUNNER_URL"

# 解凍
echo "📦 解凍中..."
tar xzf "$RUNNER_FILE"
rm "$RUNNER_FILE"

# Runner の設定
echo ""
echo "⚙️  Runner を設定中..."
echo ""

# 登録トークンの取得
echo "🔑 登録トークンを取得中..."
REGISTRATION_TOKEN=$(curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/actions/runners/registration-token" | \
    grep '"token":' | sed -E 's/.*"token": "([^"]+)".*/\1/')

if [ -z "$REGISTRATION_TOKEN" ]; then
    echo -e "${RED}❌ エラー: 登録トークンを取得できませんでした${NC}"
    echo "GITHUB_TOKENの権限を確認してください（repo権限が必要）"
    exit 1
fi

# Runner の設定を実行
./config.sh \
    --url "https://github.com/$REPO_OWNER/$REPO_NAME" \
    --token "$REGISTRATION_TOKEN" \
    --name "mac-mini-runner" \
    --labels "self-hosted,macOS,ARM64" \
    --work "_work" \
    --unattended \
    --replace

echo ""
echo "✅ Runner の設定が完了しました！"
echo ""

# サービスとして登録するか確認
read -p "Runnerをサービスとして登録しますか？（起動時に自動起動） (Y/n): " install_service

if [ "$install_service" != "n" ] && [ "$install_service" != "N" ]; then
    echo "⚙️  サービスとして登録中..."
    sudo ./svc.sh install
    sudo ./svc.sh start
    echo -e "${GREEN}✅ Runnerサービスが起動しました${NC}"
    echo ""
    echo "サービス管理コマンド："
    echo "  起動: sudo $RUNNER_DIR/svc.sh start"
    echo "  停止: sudo $RUNNER_DIR/svc.sh stop"
    echo "  状態確認: sudo $RUNNER_DIR/svc.sh status"
else
    echo ""
    echo "手動でRunnerを起動する場合："
    echo "  cd $RUNNER_DIR"
    echo "  ./run.sh"
fi

echo ""
echo "🎉 セットアップ完了！"
echo "=================================================="
echo ""
echo -e "${GREEN}✅ GitHub Actions Self-Hosted Runner が正常に設定されました${NC}"
echo ""
echo "📍 リポジトリ: https://github.com/$REPO_OWNER/$REPO_NAME"
echo "📍 Runner名: mac-mini-runner"
echo "📍 インストール場所: $RUNNER_DIR"
echo ""
echo "確認方法："
echo "  GitHub リポジトリ → Settings → Actions → Runners"
echo ""
echo "これで main/master ブランチへの push 時に自動デプロイされます！"
echo ""
