#!/usr/bin/env bash
# Local API/worker launcher. Existing observation settings may also be supplied.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${ADAPTIVE_WORK_DIR:-$ROOT/.local/circom-adaptive-4004}"
FABRIC_WORK="${ADAPTIVE_FABRIC_WORK_DIR:-$ROOT/.local/fabric-adaptive}"
ROLE="${1:?Usage: adaptive-observation-app.sh api|worker}"
[[ "$ROLE" == api || "$ROLE" == worker ]]
umask 077
mkdir -p "$WORK"
for name in jwt.key operator.token; do
  if [[ ! -f "$WORK/$name" ]]; then openssl rand -hex 32 > "$WORK/$name"; fi
done
export DEBUG="${DEBUG:-true}" ZKP_AUTO_COMPILE=false
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/csi_local_unused}"
export JWT_SECRET_KEY="$(cat "$WORK/jwt.key")"
export OPERATOR_API_TOKEN="$(cat "${OPERATOR_TOKEN_FILE:-$WORK/operator.token}")"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://127.0.0.1:3011,http://localhost:3011}"
export OBSERVATION_DATA_DIR="${OBSERVATION_DATA_DIR:-$WORK/observations}"
export OBSERVATION_MANIFEST="${OBSERVATION_MANIFEST:-$ROOT/backend/contracts/build/onchain/observations-1337.json}"
export ETHEREUM_RPC_URL="${ETHEREUM_RPC_URL:-http://127.0.0.1:8545}"
export ONCHAIN_CONFIRMATIONS="${ONCHAIN_CONFIRMATIONS:-1}"
export FABRIC_OBSERVATION_MANIFEST="${FABRIC_OBSERVATION_MANIFEST:-$ROOT/.local/fabric/deployment/manifest.json}"
export ADAPTIVE_ARTIFACT_MANIFEST="${ADAPTIVE_ARTIFACT_MANIFEST:-$WORK/artifacts.json}"
export ADAPTIVE_FABRIC_MANIFEST="${ADAPTIVE_FABRIC_MANIFEST:-$FABRIC_WORK/deployment/manifest.json}"
export ADAPTIVE_OBSERVATION_MANIFEST="${ADAPTIVE_OBSERVATION_MANIFEST:-$ROOT/.local/adaptive-evm/1337/manifest.json}"
export ADAPTIVE_ETHEREUM_RPC_URL="${ADAPTIVE_ETHEREUM_RPC_URL:-http://127.0.0.1:8545}"
export ADAPTIVE_ONCHAIN_CONFIRMATIONS="${ADAPTIVE_ONCHAIN_CONFIRMATIONS:-1}"
cd "$ROOT/backend"
if [[ "$ROLE" == api ]]; then
  if [[ -f "$FABRIC_WORK/reader.token" ]]; then export ADAPTIVE_FABRIC_READER_TOKEN="$(cat "$FABRIC_WORK/reader.token")"; fi
  if [[ -f "$ROOT/.local/fabric/reader.token" ]]; then export FABRIC_READER_TOKEN="$(cat "$ROOT/.local/fabric/reader.token")"; fi
  unset ADAPTIVE_FABRIC_WRITER_TOKEN FABRIC_WRITER_TOKEN ADAPTIVE_RECORDER_KEY_FILE
  unset OBSERVATION_RECORDER_KEY_FILE OBSERVATION_RECORDER_PRIVATE_KEY BLOCKCHAIN_PRIVATE_KEY
  exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8011}"
else
  if [[ -f "$FABRIC_WORK/writer.token" ]]; then export ADAPTIVE_FABRIC_WRITER_TOKEN="$(cat "$FABRIC_WORK/writer.token")"; fi
  if [[ -f "$ROOT/.local/fabric/writer.token" ]]; then export FABRIC_WRITER_TOKEN="$(cat "$ROOT/.local/fabric/writer.token")"; fi
  export ADAPTIVE_RECORDER_KEY_FILE="${ADAPTIVE_RECORDER_KEY_FILE:-$WORK/recorder.key}"
  export OBSERVATION_RECORDER_KEY_FILE="${OBSERVATION_RECORDER_KEY_FILE:-$WORK/recorder.key}"
  exec "$ROOT/.venv/bin/python" -m app.services.observation_worker
fi
