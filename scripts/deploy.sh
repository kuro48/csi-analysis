#!/bin/bash

# CSI Web Platform 本番環境デプロイスクリプト

set -e

echo "🚀 CSI Web Platform 本番環境デプロイを開始します..."

# 本番環境用設定ファイルの確認
if [ ! -f ".env.prod" ]; then
    echo "❌ .env.prodファイルが見つかりません。"
    echo "   .env.prod.example をコピーして .env.prod を作成し、適切な値を設定してください。"
    exit 1
fi

# SSL証明書の確認
if [ ! -d "nginx/ssl" ] || [ ! -f "nginx/ssl/cert.pem" ] || [ ! -f "nginx/ssl/key.pem" ]; then
    echo "⚠️  SSL証明書が見つかりません。"
    read -p "   SSL証明書なしで続行しますか? HTTPSが無効になります。[y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   nginx/ssl/ ディレクトリにcert.pemとkey.pemを配置してから再実行してください。"
        exit 1
    fi
fi

# Docker環境確認
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません。"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Composeがインストールされていません。"
    exit 1
fi

# 本番環境用設定ファイルを各サービスにコピー
echo "📄 本番環境設定をコピー中..."
cp .env.prod backend/.env

# フロントエンド用環境変数設定
cat > frontend/.env.production << EOF
NODE_ENV=production
NEXT_PUBLIC_API_URL=${BACKEND_URL:-https://api.yourdomain.com}
NEXT_TELEMETRY_DISABLED=1
EOF

# 既存のコンテナを停止
echo "🛑 既存のコンテナを停止中..."
docker-compose -f docker-compose.prod.yml down

# 本番環境用イメージのビルド
echo "🔨 本番環境用Dockerイメージをビルド中..."
docker-compose -f docker-compose.prod.yml build --no-cache

# バックアップ（既存データがある場合）
echo "💾 データベースバックアップ中..."
if docker volume inspect csi_postgres_data_prod &> /dev/null; then
    mkdir -p backups
    docker run --rm \
        -v csi_postgres_data_prod:/data \
        -v $(pwd)/backups:/backup \
        alpine tar czf /backup/postgres-backup-$(date +%Y%m%d-%H%M%S).tar.gz /data
    echo "✅ バックアップ完了: backups/postgres-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
fi

# 本番環境起動
echo "🚀 本番環境を起動中..."
docker-compose -f docker-compose.prod.yml up -d

# サービス起動待機
echo "⏳ サービスの起動を待機中..."
sleep 30

# ヘルスチェック
echo "🔍 サービスの状態確認..."
docker-compose -f docker-compose.prod.yml ps

# データベース接続確認
if docker-compose -f docker-compose.prod.yml exec -T postgres pg_isready -U ${DATABASE_USER:-csi_user} -d ${DATABASE_NAME:-csi_system}; then
    echo "✅ PostgreSQL: 接続OK"
else
    echo "❌ PostgreSQL: 接続失敗"
fi

# Backend API確認
sleep 10
if curl -f -k https://localhost/api/health > /dev/null 2>&1 || curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend API: 接続OK"
else
    echo "❌ Backend API: 接続失敗"
fi

echo ""
echo "🎉 本番環境デプロイ完了！"
echo ""
echo "📋 アクセス情報:"
echo "   🌐 Frontend:  https://localhost/ (または設定したドメイン)"
echo "   🔧 Backend:   https://localhost/api/ (または設定したドメイン)"
echo "   📖 API Docs:  https://localhost/docs"
echo "   📁 IPFS:      https://localhost/ipfs/"
echo ""
echo "🛠️  管理コマンド:"
echo "   ログ確認:     docker-compose -f docker-compose.prod.yml logs -f"
echo "   サービス停止: docker-compose -f docker-compose.prod.yml down"
echo "   再起動:       docker-compose -f docker-compose.prod.yml restart"
echo ""

# 設定完了後のセキュリティチェックリスト表示
echo "🔐 セキュリティチェックリスト:"
echo "   □ JWT_SECRET_KEYが本番環境用の強力なキーに変更されている"
echo "   □ データベースパスワードが安全なものに変更されている"
echo "   □ Redisパスワードが設定されている"
echo "   □ SSL証明書が正しく設定されている"
echo "   □ ファイアウォールが適切に設定されている"
echo "   □ 定期バックアップが設定されている"
echo "   □ ログ監視が設定されている"