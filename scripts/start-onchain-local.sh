#!/usr/bin/env bash
# Isolated local EVM + API + UI. Never connects to a public chain.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for item in .venv/bin/python frontend/node_modules/next/dist/bin/next backend/contracts/node_modules/ganache/dist/node/cli.js zkp/node_modules/.bin/snarkjs; do
  [ -f "$item" ] || { echo "Missing $item. Follow docs/ONCHAIN_VERIFICATION.md first."; exit 1; }
done
for port in 18545 8000 3000; do
  if curl --silent --max-time 1 "http://127.0.0.1:$port" >/dev/null; then
    echo "Port $port is already in use. Stop the existing local service first."; exit 1
  fi
done
umask 077
mkdir -p .local/onchain
export ETHEREUM_RPC_URL=http://127.0.0.1:18545
export ONCHAIN_CHAIN_ID=31337 ONCHAIN_LOCAL_UNLOCKED=true ONCHAIN_CONFIRMATIONS=1
export DEBUG=true PUBLIC_MODE=false ZKP_AUTO_COMPILE=false
export DATABASE_URL=postgresql://localhost/csi_local_unused
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export OPERATOR_API_TOKEN="$(openssl rand -hex 32)"
printf '%s' "$OPERATOR_API_TOKEN" > .local/onchain/operator-token
export ONCHAIN_MANIFEST="$ROOT/backend/contracts/build/onchain/deployment-31337.json"
export API_INTERNAL_URL=http://127.0.0.1:8000 NEXT_PUBLIC_API_URL=""
unset BLOCKCHAIN_PRIVATE_KEY ZKPROOF_CONTRACT_ADDRESS ZKPROOF_VERIFIER_CONTRACT_ADDRESS
CHAIN_PID="" API_PID="" UI_PID="" WORKER_PID=""
cleanup() { for pid in "$UI_PID" "$WORKER_PID" "$API_PID" "$CHAIN_PID"; do [ -z "$pid" ] || kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM
node backend/contracts/node_modules/ganache/dist/node/cli.js --server.host 127.0.0.1 --server.port 18545 --chain.chainId 31337 > .local/onchain/chain.log 2>&1 &
CHAIN_PID=$!
ready=false
for attempt in {1..30}; do
  if curl --silent --fail -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' "$ETHEREUM_RPC_URL" >/dev/null; then ready=true; break; fi
  sleep 1
done
[ "$ready" = true ] || { echo "Local EVM failed to start. See .local/onchain/chain.log"; exit 1; }
(cd backend/contracts && npm run build && npm run deploy)
if [ "${OBSERVATIONS_ENABLED:-false}" = true ]; then
  export OBSERVATION_RECORDER_ADDRESS
  OBSERVATION_RECORDER_ADDRESS=$(node backend/contracts/scripts/create-recorder.mjs "$ROOT/.local/onchain/observation-recorder.key")
  node backend/contracts/scripts/fund-local-recorder.mjs
  node backend/contracts/scripts/deploy-observations.mjs
  export OBSERVATION_MANIFEST="$ROOT/backend/contracts/build/onchain/observations-31337.json"
  # The EVM is ephemeral, so each run gets a new catalog/queue. No old data is deleted.
  export OBSERVATION_DATA_DIR="$ROOT/.local/onchain/observations-$(date -u +%Y%m%dT%H%M%SZ)"
  (cd backend && OBSERVATION_RECORDER_KEY_FILE="$ROOT/.local/onchain/observation-recorder.key" exec ../.venv/bin/python -m app.services.observation_worker) > .local/onchain/worker.log 2>&1 &
  WORKER_PID=$!
  echo "Patient results: http://127.0.0.1:3000/patients"
  echo "Capture administration: http://127.0.0.1:3000/capture"
  echo "Observation data: $OBSERVATION_DATA_DIR"
fi
(cd backend && exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) > .local/onchain/api.log 2>&1 &
API_PID=$!
(cd frontend && exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000) > .local/onchain/ui.log 2>&1 &
UI_PID=$!
echo "Verification UI: http://127.0.0.1:3000/verify"
echo "CSI analysis token: .local/onchain/operator-token"
echo "Disposable test accounts: .local/onchain/chain.log (NEVER fund with real assets)"
echo "Ctrl-C stops the local stack. Chain state is ephemeral. Research DB screens require a separate DB."
wait
