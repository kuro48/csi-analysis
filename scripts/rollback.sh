#!/bin/bash

# CSI Web Platform ロールバックスクリプト

set -e

# カラーコード
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "⚠️  =================================="
echo "Rollback to Previous Version"
echo "=================================="
echo ""

# バックアップディレクトリ
BACKUP_DIR="backups"

# 最新のバックアップを探す
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}❌ エラー: バックアップディレクトリが見つかりません${NC}"
    echo "バックアップが存在しないため、ロールバックできません"
    exit 1
fi

LATEST_BACKUP=$(ls -t "$BACKUP_DIR" | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo -e "${RED}❌ エラー: バックアップが見つかりません${NC}"
    exit 1
fi

echo -e "${GREEN}📥 最新のバックアップを発見: $LATEST_BACKUP${NC}"
echo ""

# 確認
read -p "このバックアップでロールバックしますか？ (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "ロールバックをキャンセルしました"
    exit 0
fi

echo ""
echo "🔄 ロールバック処理を開始します..."
echo ""

# 現在のサービスを停止
echo "🛑 現在のサービスを停止中..."
docker-compose down || true

# データベースのリストア
if [ -f "$BACKUP_DIR/$LATEST_BACKUP/database.sql" ]; then
    echo "📥 データベースをリストア中..."

    # PostgreSQLコンテナを起動（データベースのみ）
    docker-compose up -d postgres
    sleep 5

    # データベースのリストア
    docker-compose exec -T postgres psql -U csi_user csi_system < "$BACKUP_DIR/$LATEST_BACKUP/database.sql"

    echo -e "${GREEN}✅ データベースのリストアが完了しました${NC}"
else
    echo -e "${YELLOW}⚠️  データベースバックアップが見つかりません（スキップ）${NC}"
fi

# Gitで前のバージョンに戻す（オプション）
if [ -d ".git" ]; then
    echo ""
    echo "📦 Gitで前のコミットに戻しますか？"
    read -p "前のコミットに戻す (y/N): " git_rollback

    if [ "$git_rollback" = "y" ] || [ "$git_rollback" = "Y" ]; then
        echo "🔄 前のコミットに戻しています..."
        git reset --hard HEAD~1
        echo -e "${GREEN}✅ Gitのロールバックが完了しました${NC}"
    fi
fi

echo ""
echo "🚀 サービスを再起動中..."
docker-compose up -d

# サービスの起動を待つ
echo "⏳ サービスの起動を待機中（30秒）..."
sleep 30

# ヘルスチェック
echo ""
echo "🔍 ヘルスチェックを実行中..."

BACKEND_HEALTH=0
FRONTEND_HEALTH=0

# バックエンドヘルスチェック
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend: OK${NC}"
    BACKEND_HEALTH=1
else
    echo -e "${RED}❌ Backend: Failed${NC}"
fi

# フロントエンドヘルスチェック
if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend: OK${NC}"
    FRONTEND_HEALTH=1
else
    echo -e "${RED}❌ Frontend: Failed${NC}"
fi

echo ""
echo "=================================="

if [ $BACKEND_HEALTH -eq 1 ] && [ $FRONTEND_HEALTH -eq 1 ]; then
    echo -e "${GREEN}✅ ロールバックが成功しました！${NC}"
    echo ""
    echo "サービスURL:"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend API: http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo ""
    echo "ログ確認:"
    echo "  docker-compose logs -f backend"
    echo "  docker-compose logs -f frontend"
else
    echo -e "${RED}❌ ロールバックが完了しましたが、一部サービスが起動していません${NC}"
    echo ""
    echo "ログを確認してください:"
    echo "  docker-compose logs backend"
    echo "  docker-compose logs frontend"
    exit 1
fi

echo ""
echo "🎉 ロールバック完了！"
