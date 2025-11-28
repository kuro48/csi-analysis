#!/bin/bash

##############################################
# CSI Web Platform CI/CD自動再デプロイスクリプト
# GitHub Actionsから呼び出される軽量版デプロイスクリプト
##############################################

set -e # エラーで停止

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 CSI Web Platform 再デプロイ開始${NC}"
echo "================================================"

# 1. 既存サービスを停止
echo -e "\n${YELLOW}🛑 既存サービスを停止中...${NC}"
docker-compose down

# 2. Dockerイメージをビルド
echo -e "\n${YELLOW}🔨 Dockerイメージをビルド中...${NC}"
docker-compose build

# 3. サービスを起動
echo -e "\n${YELLOW}🚀 サービスを起動中...${NC}"
docker-compose up -d

# 4. サービスの起動を待機
echo -e "\n${YELLOW}⏳ サービスの起動を待機中（30秒）...${NC}"
sleep 30

# 5. ヘルスチェック
echo -e "\n${YELLOW}🏥 ヘルスチェック実行中...${NC}"

# Backendヘルスチェック
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend: 正常${NC}"
else
    echo -e "${RED}❌ Backend: 異常${NC}"
    docker-compose logs backend
    exit 1
fi

# Frontendヘルスチェック
if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend: 正常${NC}"
else
    echo -e "${RED}❌ Frontend: 異常${NC}"
    docker-compose logs frontend
    exit 1
fi

# 6. デプロイ完了
echo ""
echo "================================================"
echo -e "${GREEN}✅ 再デプロイ完了！${NC}"
echo ""
echo "📍 アクセスURL:"
echo "  - Frontend: https://csi.kur048.com"
echo "  - Backend API: https://api.csi.kur048.com"
echo "  - API Docs: https://api.csi.kur048.com/docs"
echo ""
