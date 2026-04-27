#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 CSI Web Platform 再デプロイ開始${NC}"
echo "================================================"

echo -e "\n${YELLOW}🛑 既存サービスを停止中...${NC}"
docker-compose down

echo -e "\n${YELLOW}🔨 Dockerイメージをビルド中...${NC}"
docker-compose build

echo -e "\n${YELLOW}🚀 サービスを起動中...${NC}"
docker-compose up -d

echo -e "\n${YELLOW}⏳ サービスの起動を待機中（30秒）...${NC}"
sleep 30

echo -e "\n${YELLOW}🏥 ヘルスチェック実行中...${NC}"

if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend: 正常${NC}"
else
    echo -e "${RED}❌ Backend: 異常${NC}"
    docker-compose logs backend
    exit 1
fi

echo ""
echo "================================================"
echo -e "${GREEN}✅ 再デプロイ完了！${NC}"
echo ""
echo "📍 アクセスURL:"
echo "  - Backend API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
