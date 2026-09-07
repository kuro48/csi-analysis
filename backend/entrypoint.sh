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
from app.models import CSIData, BaseCSI

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
set +e
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
set -e

if [ $status -eq 2 ]; then
  echo "ZKProofRegistry contract missing or invalid. Deploying..."
  set +e
  python contracts/deploy_zkproof_contract.py
  deploy_status=$?
  set -e
  if [ $deploy_status -ne 0 ]; then
    echo "WARNING: ZKProofRegistry auto-deploy failed. Continuing without blockchain auto-deploy."
  fi
elif [ $status -eq 3 ]; then
  echo "Failed to connect to Ethereum node for contract check."
else
  echo "ZKProofRegistry contract is available."
fi

# 5-1 と Lomb-Scargle 比較経路の証明書回路を事前準備する。
if [ "${ZKP_AUTO_COMPILE:-TRUE}" = "TRUE" ] || [ "${ZKP_AUTO_COMPILE:-true}" = "true" ]; then
  ZKP_DIR="${ZKP_DIR:-/zkp}"
  CERT_WASM="$ZKP_DIR/build/csi_breathing_certificate_js/csi_breathing_certificate.wasm"
  CERT_ZKEY="$ZKP_DIR/keys/csi_breathing_certificate_final.zkey"
  PTAU_FILE="$ZKP_DIR/keys/powersOfTau28_hez_final_19.ptau"

  if [ ! -f "$CERT_WASM" ] || [ ! -f "$CERT_ZKEY" ]; then
    echo "Preparing breathing certificate circuit..."
    set +e
    if [ ! -d "$ZKP_DIR/node_modules" ]; then
      npm install --prefix "$ZKP_DIR"
    fi
    if [ ! -f "$PTAU_FILE" ]; then
      PTAU_URL="https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_19.ptau"
      wget -q -O "$PTAU_FILE" "$PTAU_URL" || curl -sL -o "$PTAU_FILE" "$PTAU_URL"
    fi
    (cd "$ZKP_DIR" \
      && npm run generate:breathing_certificate \
      && npm run compile:breathing_certificate \
      && npm run setup:breathing_certificate) \
      && echo "Breathing certificate circuit is ready." \
      || echo "WARNING: Breathing certificate circuit setup failed."
    set -e
  else
    echo "Breathing certificate circuit is already compiled."
  fi

  LOMB_WASM="$ZKP_DIR/build/csi_lomb_scargle_normality_js/csi_lomb_scargle_normality.wasm"
  LOMB_ZKEY="$ZKP_DIR/keys/csi_lomb_scargle_normality_final.zkey"
  LOMB_CIRCUIT="$ZKP_DIR/circuits/csi_lomb_scargle_normality.circom"
  LOMB_BASIS_CIRCUIT="$ZKP_DIR/circuits/lomb_scargle_timestamp_basis.circom"
  if [ ! -f "$LOMB_WASM" ] || [ ! -f "$LOMB_ZKEY" ] \
    || [ "$LOMB_CIRCUIT" -nt "$LOMB_WASM" ] || [ "$LOMB_BASIS_CIRCUIT" -nt "$LOMB_WASM" ]; then
    echo "Preparing Lomb-Scargle normality circuit..."
    set +e
    if [ ! -d "$ZKP_DIR/node_modules" ]; then
      npm install --prefix "$ZKP_DIR"
    fi
    if sh "$ZKP_DIR/scripts/fetch_ptau24.sh"; then
      LOMB_PTAU_READY=true
    else
      echo "WARNING: Could not obtain the 2^24 Powers of Tau file."
      echo "A phase-2 Powers of Tau file with power 24 or greater is required,"
      echo "or set LOMB_PTAU_URL to a trusted production ceremony file."
      LOMB_PTAU_READY=false
    fi
    ([ "$LOMB_PTAU_READY" = "true" ] \
      && cd "$ZKP_DIR" \
      && npm run generate:lomb_scargle \
      && npm run compile:lomb_scargle \
      && npm run setup:lomb_scargle) \
      && echo "Lomb-Scargle normality circuit is ready." \
      || echo "WARNING: Lomb-Scargle normality circuit setup failed."
    set -e
  else
    echo "Lomb-Scargle normality circuit is already compiled."
  fi
fi

# Uvicornサーバーを起動
echo "Starting Uvicorn server..."
if [ "${BACKEND_RELOAD:-false}" = "true" ] || [ "${BACKEND_RELOAD:-false}" = "TRUE" ]; then
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
