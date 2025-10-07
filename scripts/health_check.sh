#!/bin/bash

# CSI Web Platform ヘルスチェックスクリプト

set -e

echo "🔍 CSI Web Platform ヘルスチェック開始..."
echo "==========================================="

# カラーコード
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ヘルスチェック結果
OVERALL_STATUS=0

# Docker & Docker Compose チェック
echo -e "\n📦 Docker環境チェック"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅ Docker: インストール済み${NC}"
    docker --version
else
    echo -e "${RED}❌ Docker: 未インストール${NC}"
    OVERALL_STATUS=1
fi

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo -e "${GREEN}✅ Docker Compose: インストール済み${NC}"
    if command -v docker-compose &> /dev/null; then
        docker-compose --version
    else
        docker compose version
    fi
else
    echo -e "${RED}❌ Docker Compose: 未インストール${NC}"
    OVERALL_STATUS=1
fi

# コンテナ状態チェック
echo -e "\n🐳 コンテナ状態チェック"
if docker-compose ps &> /dev/null; then
    echo "コンテナ状態:"
    docker-compose ps

    # 各サービスの状態チェック
    services=("postgres" "redis" "backend" "frontend")
    for service in "${services[@]}"; do
        if docker-compose ps $service | grep -q "Up"; then
            echo -e "${GREEN}✅ $service: 稼働中${NC}"
        else
            echo -e "${RED}❌ $service: 停止中${NC}"
            OVERALL_STATUS=1
        fi
    done
else
    echo -e "${YELLOW}⚠️ docker-compose.yml が見つからないか、コンテナが起動していません${NC}"
fi

# データベース接続チェック
echo -e "\n🗄️ データベース接続チェック"
if docker-compose ps postgres | grep -q "Up"; then
    if docker-compose exec -T postgres pg_isready -U csi_user -d csi_system &> /dev/null; then
        echo -e "${GREEN}✅ PostgreSQL: 接続可能${NC}"
    else
        echo -e "${RED}❌ PostgreSQL: 接続失敗${NC}"
        OVERALL_STATUS=1
    fi
else
    echo -e "${YELLOW}⚠️ PostgreSQLコンテナが起動していません${NC}"
fi

# Redis接続チェック
echo -e "\n📦 Redis接続チェック"
if docker-compose ps redis | grep -q "Up"; then
    if docker-compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo -e "${GREEN}✅ Redis: 接続可能${NC}"
    else
        echo -e "${RED}❌ Redis: 接続失敗${NC}"
        OVERALL_STATUS=1
    fi
else
    echo -e "${YELLOW}⚠️ Redisコンテナが起動していません${NC}"
fi

# バックエンドAPI接続チェック
echo -e "\n🔧 バックエンドAPI接続チェック"
if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend API: 接続可能${NC}"

    # API詳細ヘルスチェック
    health_response=$(curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
    if echo "$health_response" | grep -q "healthy"; then
        echo -e "${GREEN}✅ API詳細ヘルスチェック: 正常${NC}"
    else
        echo -e "${YELLOW}⚠️ API詳細ヘルスチェック: 要確認${NC}"
        echo "Response: $health_response"
    fi
else
    echo -e "${RED}❌ Backend API: 接続失敗${NC}"
    OVERALL_STATUS=1
fi

# フロントエンド接続チェック
echo -e "\n🌐 フロントエンド接続チェック"
if curl -f -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend: 接続可能${NC}"
else
    echo -e "${RED}❌ Frontend: 接続失敗${NC}"
    OVERALL_STATUS=1
fi

# IPFS接続チェック（オプション）
echo -e "\n📁 IPFS接続チェック"
if docker-compose ps ipfs | grep -q "Up"; then
    if curl -f -s http://localhost:8080/ipfs/ > /dev/null 2>&1; then
        echo -e "${GREEN}✅ IPFS: 接続可能${NC}"
    else
        echo -e "${YELLOW}⚠️ IPFS: アクセス要確認${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ IPFSコンテナが起動していません（オプション）${NC}"
fi

# ディスク使用量チェック
echo -e "\n💾 ディスク使用量チェック"
df -h | grep -E "Filesystem|/dev/"
echo

# メモリ使用量チェック
echo -e "🧠 メモリ使用量チェック"
if command -v free &> /dev/null; then
    free -h
elif command -v vm_stat &> /dev/null; then
    # macOS
    vm_stat | head -n 10
else
    echo "メモリ情報を取得できませんでした"
fi

# 結果サマリー
echo -e "\n==========================================="
echo -e "🎯 ヘルスチェック結果サマリー"
echo -e "==========================================="

if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}🎉 全体的なステータス: 正常${NC}"
    echo -e "\n📋 アクセス情報:"
    echo -e "   🌐 Frontend:  http://localhost:3000"
    echo -e "   🔧 Backend:   http://localhost:8000"
    echo -e "   📖 API Docs:  http://localhost:8000/docs"
    echo -e "   📁 IPFS:      http://localhost:8080"
else
    echo -e "${RED}⚠️ 全体的なステータス: 要確認${NC}"
    echo -e "一部のサービスで問題が検出されました。上記の詳細を確認してください。"
fi

echo -e "\n🛠️ 便利なコマンド:"
echo -e "   ログ確認:     docker-compose logs -f [service_name]"
echo -e "   サービス再起動: docker-compose restart [service_name]"
echo -e "   全体再起動:   docker-compose restart"
echo -e "   システム停止: docker-compose down"

exit $OVERALL_STATUS