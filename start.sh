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

# ZKP回路コンパイル/デプロイ（オプション）
if [[ "${ZKP_AUTO_DEPLOY}" == "true" ]]; then
    echo "🧩 ZKP回路のコンパイルとSepoliaデプロイを実行します..."

    if [ ! -f "zkp/hardhat/.env" ]; then
        echo "❌ zkp/hardhat/.env が見つかりません。"
        echo "   zkp/hardhat/.env.example をコピーしてRPC/秘密鍵を設定してください。"
        exit 1
    fi

    if [ ! -d "zkp/node_modules" ]; then
        echo "📦 zkp 依存関係をインストール中..."
        (cd zkp && npm install)
    fi

    echo "🔧 ZKP回路をコンパイル中..."
    (cd zkp && npm run compile:full_similarity)

    echo "🔑 ZKPセットアップ中..."
    (cd zkp && npm run setup:full_similarity)

    echo "🧾 Solidity Verifierを生成中..."
    (cd zkp && npm run export:full_similarity:sol)

    if [ ! -d "zkp/hardhat/node_modules" ]; then
        echo "📦 hardhat 依存関係をインストール中..."
        (cd zkp/hardhat && npm install)
    fi

    echo "🚀 Sepoliaへデプロイ中..."
    DEPLOY_OUTPUT="/tmp/zkp_deploy.json"
    (cd zkp/hardhat && DEPLOY_OUTPUT="${DEPLOY_OUTPUT}" npx hardhat compile && DEPLOY_OUTPUT="${DEPLOY_OUTPUT}" npx hardhat run scripts/deploy.js --network "${ZKP_HARDHAT_NETWORK:-sepolia}")

    if [ -f "${DEPLOY_OUTPUT}" ]; then
        REGISTRY_ADDRESS=$(node -e "const fs=require('fs');const j=JSON.parse(fs.readFileSync(process.argv[1]));console.log(j.registry);" "${DEPLOY_OUTPUT}")
        if [ -n "${REGISTRY_ADDRESS}" ]; then
            if [ -f "backend/.env" ]; then
                if grep -q "^ZKP_SUBMIT_REGISTRY_ADDRESS=" backend/.env; then
                    perl -pi -e "s/^ZKP_SUBMIT_REGISTRY_ADDRESS=.*/ZKP_SUBMIT_REGISTRY_ADDRESS=${REGISTRY_ADDRESS}/" backend/.env
                else
                    echo "ZKP_SUBMIT_REGISTRY_ADDRESS=${REGISTRY_ADDRESS}" >> backend/.env
                fi
                echo "✅ backend/.env に ZKP_SUBMIT_REGISTRY_ADDRESS を設定しました"
            fi
        fi
    fi
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
