#!/bin/bash

# CSI Web Platform データベースバックアップスクリプト

set -e

# 設定
BACKUP_DIR="backup"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="csi_system"
DB_USER="csi_user"

# バックアップディレクトリの作成
mkdir -p "$BACKUP_DIR"

echo "🗄️ データベースバックアップを開始します..."

# PostgreSQLバックアップ
if docker-compose ps postgres | grep -q "Up"; then
    echo "📦 PostgreSQLバックアップ中..."

    # SQLダンプの作成
    docker-compose exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" | \
        gzip > "$BACKUP_DIR/postgres_backup_$DATE.sql.gz"

    echo "✅ PostgreSQLバックアップ完了: $BACKUP_DIR/postgres_backup_$DATE.sql.gz"
else
    echo "❌ PostgreSQLコンテナが起動していません"
    exit 1
fi

# Redisバックアップ
if docker-compose ps redis | grep -q "Up"; then
    echo "📦 Redisバックアップ中..."

    # RDBファイルの保存
    docker-compose exec -T redis redis-cli BGSAVE
    sleep 2

    # RDBファイルのコピー
    docker cp $(docker-compose ps -q redis):/data/dump.rdb "$BACKUP_DIR/redis_backup_$DATE.rdb"

    echo "✅ Redisバックアップ完了: $BACKUP_DIR/redis_backup_$DATE.rdb"
else
    echo "⚠️ Redisコンテナが起動していません（スキップ）"
fi

# IPFSデータバックアップ（オプション）
if docker-compose ps ipfs | grep -q "Up"; then
    echo "📦 IPFSバックアップ中..."

    # IPFSデータディレクトリのアーカイブ
    docker run --rm \
        -v "$(pwd)":/backup \
        -v csi_web_platform_ipfs_data:/ipfs_data:ro \
        alpine:latest \
        tar -czf "/backup/$BACKUP_DIR/ipfs_backup_$DATE.tar.gz" -C /ipfs_data .

    echo "✅ IPFSバックアップ完了: $BACKUP_DIR/ipfs_backup_$DATE.tar.gz"
else
    echo "⚠️ IPFSコンテナが起動していません（スキップ）"
fi

# 古いバックアップの削除（7日以上前）
echo "🧹 古いバックアップファイルの削除中..."
find "$BACKUP_DIR" -type f -name "*backup_*" -mtime +7 -delete
echo "✅ 古いバックアップファイルを削除しました"

# バックアップファイルのサイズ確認
echo "📊 バックアップファイル情報:"
ls -lh "$BACKUP_DIR"/*$DATE*

echo "🎉 バックアップが完了しました！"
echo "📍 バックアップ場所: $BACKUP_DIR/"