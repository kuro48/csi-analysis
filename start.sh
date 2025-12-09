#!/bin/bash

# CSI Web Platform Docker一括起動スクリプト

set -e

echo "🚀 CSI Web Platform を起動しています..."

# Docker と Docker Compose がインストールされているか確認
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません。"
    echo "   https://docs.docker.com/get-docker/ からインストールしてください。"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Composeがインストールされていません。"
    echo "   https://docs.docker.com/compose/install/ からインストールしてください。"
    exit 1
fi

# Docker環境用設定ファイルをバックエンドにコピー
if [ -f ".env.docker" ]; then
    echo "📄 Docker環境設定をコピー中..."
    cp .env.docker backend/.env
fi

if [ -f "frontend/.env.local.docker" ]; then
    cp frontend/.env.local.docker frontend/.env.local
fi

# 既存のコンテナを停止・削除（オプション）
read -p "🛑 既存のコンテナを停止・削除しますか? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🛑 既存のコンテナを停止・削除中..."
    docker-compose down --volumes --remove-orphans || true
fi

# イメージのビルドと起動
echo "🔨 Dockerイメージをビルド中..."
docker-compose build

echo "🚀 サービスを起動中..."
docker-compose up -d

# サービスの起動確認
echo "⏳ サービスの起動を待機中..."
sleep 10

# ヘルスチェック
echo "🔍 サービスの状態確認..."
docker-compose ps

# データベース接続確認
echo "🔍 データベース接続確認..."
if docker-compose exec -T postgres pg_isready -U csi_user -d csi_system; then
    echo "✅ PostgreSQL: 接続OK"
else
    echo "❌ PostgreSQL: 接続失敗"
fi

# Redis接続確認
if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
    echo "✅ Redis: 接続OK"
else
    echo "❌ Redis: 接続失敗"
fi

# バックエンドAPI確認
sleep 5
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend API: 接続OK"
else
    echo "❌ Backend API: 接続失敗"
fi

echo ""
echo "🎉 セットアップ完了！"
echo ""
echo "📋 サービス情報:"
echo "   🌐 Frontend:  http://localhost:3000"
echo "   🔧 Backend:   http://localhost:8000"
echo "   📖 API Docs:  http://localhost:8000/docs"
echo "   🗄️  Database:  localhost:5432 (csi_user/csi_password)"
echo "   🔴 Redis:     localhost:6379"
echo ""
echo "🛠️  便利なコマンド:"
echo "   ログ確認:     docker-compose logs -f"
echo "   サービス停止: docker-compose down"
echo "   再起動:       docker-compose restart"
echo ""
echo "🔐 初期管理者アカウント:"
echo "   ユーザー名: admin"
echo "   パスワード: admin123"
echo ""

# ログの監視開始（オプション）
read -p "📋 リアルタイムログを表示しますか? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker-compose logs -f
fi