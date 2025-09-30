#!/bin/bash

# CSI Web Platform Docker停止スクリプト

set -e

echo "🛑 CSI Web Platform を停止しています..."

# サービスの停止
echo "🔄 サービスを停止中..."
docker-compose down

echo "✅ 全サービスが停止されました。"

# オプション: ボリュームも削除
read -p "🗑️  データベースボリュームも削除しますか? (データが失われます) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  ボリューム削除中..."
    docker-compose down --volumes
    echo "✅ ボリュームが削除されました。"
fi