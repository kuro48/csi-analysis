#!/bin/bash

set -e

BUILD=false
NO_CACHE=false
CLEAN=false
RESET_VOLUMES=false
FOLLOW_LOGS=false
ZKP_AUTO_COMPILE="${ZKP_AUTO_COMPILE:-false}"

usage() {
    cat <<'EOF'
Usage: ./start.sh [options]

Options:
  --build         起動前にDockerイメージをビルドする
  --rebuild       キャッシュなしでDockerイメージを再ビルドする
  --clean         既存コンテナを停止・削除してから起動する
  --reset-volumes --clean時にボリュームも削除する（DB/Redis/Ganacheデータ消去）
  --compile-zkp   backend起動時のZKP回路自動コンパイルを有効にする
  --logs          起動後にログを追尾する
  -h, --help      このヘルプを表示する
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --build)
            BUILD=true
            ;;
        --rebuild)
            BUILD=true
            NO_CACHE=true
            ;;
        --clean)
            CLEAN=true
            ;;
        --reset-volumes)
            RESET_VOLUMES=true
            ;;
        --compile-zkp)
            ZKP_AUTO_COMPILE=true
            ;;
        --logs)
            FOLLOW_LOGS=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ 不明なオプション: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

echo "🚀 CSI Web Platform を起動しています..."

if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません。"
    echo "   https://docs.docker.com/get-docker/ からインストールしてください。"
    exit 1
fi

if command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE="docker compose"
else
    echo "❌ Docker Composeがインストールされていません。"
    echo "   https://docs.docker.com/compose/install/ からインストールしてください。"
    exit 1
fi

if [ -f ".env.docker" ]; then
    echo "📄 Docker環境設定をコピー中..."
    cp .env.docker backend/.env
fi

export ZKP_AUTO_COMPILE

if [ "$CLEAN" = true ]; then
    echo "🛑 既存のコンテナを停止・削除中..."
    if [ "$RESET_VOLUMES" = true ]; then
        $COMPOSE down --volumes --remove-orphans || true
    else
        $COMPOSE down --remove-orphans || true
    fi
fi

if [ "$BUILD" = true ]; then
    echo "🔨 Dockerイメージをビルド中..."
    if [ "$NO_CACHE" = true ]; then
        $COMPOSE build --no-cache
    else
        $COMPOSE build
    fi
else
    echo "⏭️  Dockerイメージの明示ビルドをスキップします（必要なら --build / --rebuild）。"
fi

echo "🚀 サービスを起動中..."
$COMPOSE up -d

wait_for() {
    local name="$1"
    local attempts="$2"
    local interval="$3"
    shift 3

    for ((i=1; i<=attempts; i++)); do
        if "$@" > /dev/null 2>&1; then
            echo "✅ $name: 接続OK"
            return 0
        fi
        sleep "$interval"
    done

    echo "❌ $name: 接続失敗（バックグラウンドで起動中の可能性あり）"
    return 1
}

echo "🔍 サービスの状態確認..."
$COMPOSE ps

wait_for "PostgreSQL" 30 1 $COMPOSE exec -T postgres pg_isready -U csi_user -d csi_system || true
wait_for "Redis" 30 1 sh -c "$COMPOSE exec -T redis redis-cli ping | grep -q PONG" || true
wait_for "Backend API" 60 2 curl -f http://localhost:8000/health || true
wait_for "Frontend (nginx)" 60 2 curl -f http://localhost || true

echo ""
echo "🎉 セットアップ完了！"
echo ""
echo "📋 サービス情報:"
echo "   🌐 Frontend:  http://localhost"
echo "   📤 Upload:    http://localhost/upload"
echo "   🔧 API:       http://localhost/api/v2/"
echo "   📖 API Docs:  http://localhost/docs"
echo "   🗄️  Database:  localhost:5432 (csi_user/csi_password)"
echo "   🔴 Redis:     localhost:6379"
echo ""
echo "🛠️  便利なコマンド:"
echo "   高速起動:     ./start.sh"
echo "   ビルド起動:   ./start.sh --build"
echo "   完全再構築:   ./start.sh --clean --rebuild"
echo "   ログ確認:     $COMPOSE logs -f"
echo "   サービス停止: $COMPOSE down"
echo "   再起動:       $COMPOSE restart"
echo ""
echo "🔐 初期管理者アカウント:"
echo "   ユーザー名: admin"
echo "   パスワード: admin123"
echo ""

if [ "$FOLLOW_LOGS" = true ]; then
    $COMPOSE logs -f
fi
