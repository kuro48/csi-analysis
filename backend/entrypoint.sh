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

# FullSimilarityVerifierが未デプロイ/無効なら自動デプロイ
echo "Checking FullSimilarityVerifier deployment..."
set +e
python - <<'PY'
import json
import os
from pathlib import Path
from web3 import Web3

rpc_url = os.getenv("ETHEREUM_RPC_URL", "http://ganache:8545")
address = os.getenv("ZKPROOF_VERIFIER_CONTRACT_ADDRESS", "")
artifact = Path("/app/contracts/build/FullSimilarityVerifier.json")

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
verifier_status=$?
set -e

if [ $verifier_status -eq 2 ]; then
  VERIFIER_SOL="/zkp/build/full_similarity_verifier.sol"
  ZKEY_FILE="/zkp/keys/csi_full_similarity_final.zkey"
  if [ ! -f "$VERIFIER_SOL" ] && [ -f "$ZKEY_FILE" ]; then
    echo "Generating FullSimilarityVerifier solidity..."
    snarkjs zkey export solidityverifier "$ZKEY_FILE" "$VERIFIER_SOL"
  fi

  if [ -f "$VERIFIER_SOL" ]; then
    echo "FullSimilarityVerifier contract missing or invalid. Deploying..."
    set +e
    python contracts/deploy_full_similarity_verifier.py
    verifier_deploy_status=$?
    set -e
    if [ $verifier_deploy_status -ne 0 ]; then
      echo "WARNING: FullSimilarityVerifier auto-deploy failed. Continuing without verifier auto-deploy."
    fi
  else
    echo "FullSimilarityVerifier solidity not found. Skipping deploy."
  fi
elif [ $verifier_status -eq 3 ]; then
  echo "Failed to connect to Ethereum node for verifier check."
else
  echo "FullSimilarityVerifier contract is available."
fi

# ZKP回路の事前コンパイル（Wavelet・MUSIC）
if [ "${ZKP_AUTO_COMPILE:-TRUE}" = "TRUE" ] || [ "${ZKP_AUTO_COMPILE:-true}" = "true" ]; then
  ZKP_DIR="${ZKP_DIR:-/zkp}"
  WAVELET_WASM="$ZKP_DIR/build/csi_wavelet_similarity_js/csi_wavelet_similarity.wasm"
  WAVELET_ZKEY="$ZKP_DIR/keys/csi_wavelet_similarity_final.zkey"
  MUSIC_WASM="$ZKP_DIR/build/csi_music_similarity_js/csi_music_similarity.wasm"
  MUSIC_ZKEY="$ZKP_DIR/keys/csi_music_similarity_final.zkey"
  PTAU_FILE="$ZKP_DIR/keys/powersOfTau28_hez_final_19.ptau"

  NEED_WAVELET=false
  NEED_MUSIC=false
  [ ! -f "$WAVELET_WASM" ] || [ ! -f "$WAVELET_ZKEY" ] && NEED_WAVELET=true
  [ ! -f "$MUSIC_WASM" ]   || [ ! -f "$MUSIC_ZKEY" ]   && NEED_MUSIC=true

  if $NEED_WAVELET || $NEED_MUSIC; then
    echo "ZKP circuits (wavelet/MUSIC) not found. Starting pre-compilation..."
    set +e

    # node_modules がなければ npm install
    if [ ! -d "$ZKP_DIR/node_modules" ]; then
      echo "Installing ZKP npm dependencies..."
      npm install --prefix "$ZKP_DIR"
    fi

    # ptauファイルがなければダウンロード（FFT回路でも共有）
    if [ ! -f "$PTAU_FILE" ]; then
      echo "Downloading Powers of Tau file (~200MB)..."
      PTAU_URL="https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_19.ptau"
      wget -q -O "$PTAU_FILE" "$PTAU_URL" \
        || curl -sL -o "$PTAU_FILE" "$PTAU_URL" \
        || { echo "WARNING: Failed to download ptau file. Circuit setup will fail."; }
    fi

    # Wavelet回路のコンパイル・セットアップ
    if $NEED_WAVELET; then
      echo "Compiling wavelet ZKP circuit..."
      (cd "$ZKP_DIR" && npm run compile:wavelet && npm run setup:wavelet) \
        && echo "Wavelet ZKP circuit is ready." \
        || echo "WARNING: Wavelet ZKP circuit compilation failed. Auto-compile will retry on first upload."
    else
      echo "Wavelet ZKP circuit is already compiled."
    fi

    # MUSIC回路のコンパイル・セットアップ（制約数が多いため数十分かかる場合あり）
    if $NEED_MUSIC; then
      echo "Compiling MUSIC ZKP circuit (this may take 10-60 minutes)..."
      (cd "$ZKP_DIR" && npm run compile:music && npm run setup:music) \
        && echo "MUSIC ZKP circuit is ready." \
        || echo "WARNING: MUSIC ZKP circuit compilation failed. Auto-compile will retry on first upload."
    else
      echo "MUSIC ZKP circuit is already compiled."
    fi

    set -e
  else
    echo "All ZKP circuits (wavelet/MUSIC) are already compiled. Skipping."
  fi
fi

# Uvicornサーバーを起動
echo "Starting Uvicorn server..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
