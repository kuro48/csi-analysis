#!/usr/bin/env bash
# Dedicated Sepolia-only application on Mac. No local-chain defaults or shared queue.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${SEPOLIA_MAC_WORK_DIR:-$ROOT/.local/sepolia-mac}"
ROLE="${1:?prepare|check|deploy|seed|verify|api|worker}"
umask 077
mkdir -p "$WORK"
export SEPOLIA_MAC_WORK_DIR="$WORK"
export ADAPTIVE_ARTIFACT_MANIFEST="${ADAPTIVE_ARTIFACT_MANIFEST:-$ROOT/.local/circom-adaptive-4004/artifacts.json}"
export ADAPTIVE_DEPLOY_DIR="${ADAPTIVE_DEPLOY_DIR:-$ROOT/.local/adaptive-evm/11155111}"
export ADAPTIVE_OBSERVATION_MANIFEST="$ADAPTIVE_DEPLOY_DIR/manifest.json"
export ADAPTIVE_ETHEREUM_RPC_URL="${ADAPTIVE_ETHEREUM_RPC_URL:-https://ethereum-sepolia-rpc.publicnode.com}"
export ETHEREUM_RPC_URL="$ADAPTIVE_ETHEREUM_RPC_URL" ONCHAIN_CHAIN_ID=11155111
export ADAPTIVE_ONCHAIN_CONFIRMATIONS="${ADAPTIVE_ONCHAIN_CONFIRMATIONS:-2}"
export ONCHAIN_CONFIRMATIONS="$ADAPTIVE_ONCHAIN_CONFIRMATIONS"
export OBSERVATION_DATA_DIR="$WORK/observations"
export DEBUG=false PUBLIC_MODE=true RESEARCH_MODE=false ENABLE_TEST_ENDPOINTS=false ZKP_AUTO_COMPILE=false
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://127.0.0.1:3014,http://localhost:3014}"
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/csi_sepolia_unused}"
export PICOSCENES_PARSER=python PYTHONPATH="$ROOT/backend"
# Observation UI uses its dedicated SQLite store. Legacy SQL routes are unused.
unset ONCHAIN_MANIFEST OBSERVATION_MANIFEST FABRIC_OBSERVATION_MANIFEST ADAPTIVE_FABRIC_MANIFEST
unset FABRIC_WRITER_TOKEN ADAPTIVE_FABRIC_WRITER_TOKEN OBSERVATION_RECORDER_PRIVATE_KEY BLOCKCHAIN_PRIVATE_KEY
unset OBSERVATION_RECORDER_KEY_FILE
for name in jwt.key operator.token; do
  if [[ ! -f "$WORK/$name" ]]; then openssl rand -hex 32 > "$WORK/$name"; fi
done
export JWT_SECRET_KEY="$(cat "$WORK/jwt.key")" OPERATOR_API_TOKEN="$(cat "$WORK/operator.token")"
cd "$ROOT"
case "$ROLE" in
  prepare)
    ADAPTIVE_DEPLOY_DIR="$WORK/build" ADAPTIVE_BUILD_ONLY=true ONCHAIN_DEPLOY_PUBLIC=true \
      node backend/contracts/scripts/deploy-adaptive-observations.mjs
    node backend/contracts/scripts/check-sepolia-proof.mjs "$WORK/proof-readiness.json"
    ;;
  check) exec node backend/contracts/scripts/check-staging.mjs "$WORK/readiness.json" ;;
  deploy)
    OBSERVATION_DEBUG_INPUTS=true node backend/contracts/scripts/deploy-adaptive-sepolia.mjs
    ;;
  seed)
    node backend/contracts/scripts/check-sepolia-proof.mjs "$WORK/proof-readiness.json"
    exec "$ROOT/.venv/bin/python" scripts/sepolia_smoke.py seed
    ;;
  verify) exec "$ROOT/.venv/bin/python" scripts/sepolia_smoke.py verify ;;
  api)
    unset ADAPTIVE_RECORDER_KEY_FILE ADAPTIVE_SEPOLIA_DEPLOYER_KEY_FILE
    exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8014}"
    ;;
  worker)
    export ADAPTIVE_RECORDER_KEY_FILE="${ADAPTIVE_RECORDER_KEY_FILE:-$ROOT/.local/sepolia-adaptive/recorder.key}"
    unset ADAPTIVE_SEPOLIA_DEPLOYER_KEY_FILE
    exec "$ROOT/.venv/bin/python" -m app.services.observation_worker
    ;;
  *) echo 'Usage: sepolia-mac.sh prepare|check|deploy|seed|verify|api|worker' >&2; exit 1 ;;
esac
