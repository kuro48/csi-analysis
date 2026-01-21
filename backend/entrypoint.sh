#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# PostgreSQLが利用可能になるまで待機
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DATABASE_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is ready!"

# SQLAlchemyでテーブルを作成
echo "Creating database tables..."
python -c "
from app.core.database import Base, engine
# クラスを明示的にインポート
from app.models import User, CSIData, Session, BaseCSI

# 全てのテーブルを作成
Base.metadata.create_all(bind=engine)
print('Tables created successfully!')
"

# Alembicマイグレーションテーブルをスタンプ（既存のマイグレーションをスキップ）
echo "Stamping Alembic migrations..."
alembic stamp head

echo "Database setup completed successfully!"

# Ganacheが起動するまで待機（ブロックチェーン自動デプロイ用）
if [ -n "$ETHEREUM_RPC_URL" ]; then
  echo "Waiting for Ganache to be ready..."
  until curl -s -X POST "$ETHEREUM_RPC_URL" \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' >/dev/null 2>&1; do
    echo "Ganache is unavailable - sleeping"
    sleep 2
  done
  echo "Ganache is ready!"
fi

# ZKProofRegistryコントラクトが未デプロイなら自動デプロイ
if [ -z "$ZKPROOF_CONTRACT_ADDRESS" ]; then
  CONTRACT_ARTIFACT="/app/contracts/build/ZKProofRegistry.json"
  if [ -f "$CONTRACT_ARTIFACT" ]; then
    ADDRESS_IN_ARTIFACT=$(python - <<'PY'
import json
from pathlib import Path

artifact = Path("/app/contracts/build/ZKProofRegistry.json")
data = json.loads(artifact.read_text())
print(data.get("address") or "")
PY
)
  else
    ADDRESS_IN_ARTIFACT=""
  fi

  if [ -z "$ADDRESS_IN_ARTIFACT" ]; then
    echo "ZKProofRegistry contract not found. Deploying..."
    python contracts/deploy_zkproof_contract.py
  else
    echo "ZKProofRegistry contract already deployed (artifact found)."
  fi
fi

# Uvicornサーバーを起動
echo "Starting Uvicorn server..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
