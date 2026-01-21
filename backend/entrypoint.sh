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

# ZKProofRegistryコントラクトが未デプロイ/無効なら自動デプロイ
echo "Checking ZKProofRegistry deployment..."
python - <<'PY'
import json
import os
from pathlib import Path
from web3 import Web3

rpc_url = os.getenv("ETHEREUM_RPC_URL", "http://ganache:8545")
address = os.getenv("ZKPROOF_CONTRACT_ADDRESS", "")
artifact = Path("/app/contracts/build/ZKProofRegistry.json")

if not address and artifact.exists():
    data = json.loads(artifact.read_text())
    address = data.get("address") or ""

if not address:
    raise SystemExit(2)

w3 = Web3(Web3.HTTPProvider(rpc_url))
if not w3.is_connected():
    raise SystemExit(3)

code = w3.eth.get_code(w3.to_checksum_address(address))
if not code or code in (b"", b"\x00"):
    raise SystemExit(2)
PY
status=$?

if [ $status -eq 2 ]; then
  echo "ZKProofRegistry contract missing or invalid. Deploying..."
  python contracts/deploy_zkproof_contract.py
elif [ $status -eq 3 ]; then
  echo "Failed to connect to Ethereum node for contract check."
else
  echo "ZKProofRegistry contract is available."
fi

# Uvicornサーバーを起動
echo "Starting Uvicorn server..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
