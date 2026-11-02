#!/usr/bin/env bash
# Local API/worker launcher for the existing UI. Production configuration: docs/FABRIC_COMPARISON.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${FABRIC_WORK_DIR:-$ROOT/.local/fabric}"
ROLE="${1:?Usage: app.sh api|worker}"
[[ "$ROLE" == api || "$ROLE" == worker ]]
umask 077
export DEBUG="${DEBUG:-true}" ZKP_AUTO_COMPILE=false
export OBSERVATION_DATA_DIR="${OBSERVATION_DATA_DIR:-$WORK/observations}"
export FABRIC_OBSERVATION_MANIFEST="$WORK/deployment/manifest.json"
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/csi_local_unused}"
if [[ ! -f "$WORK/jwt.key" ]]; then openssl rand -hex 32 > "$WORK/jwt.key"; fi
if [[ ! -f "$WORK/operator.token" ]]; then openssl rand -hex 32 > "$WORK/operator.token"; fi
export JWT_SECRET_KEY="$(cat "$WORK/jwt.key")"
export OPERATOR_API_TOKEN="$(cat "${OPERATOR_TOKEN_FILE:-$WORK/operator.token}")"
cd "$ROOT/backend"
if [[ "$ROLE" == api ]]; then
 export FABRIC_READER_TOKEN="$(cat "$WORK/reader.token")"
 unset FABRIC_WRITER_TOKEN OBSERVATION_RECORDER_PRIVATE_KEY OBSERVATION_RECORDER_KEY_FILE BLOCKCHAIN_PRIVATE_KEY
 exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8000}"
else
 export FABRIC_WRITER_TOKEN="$(cat "$WORK/writer.token")"
 exec "$ROOT/.venv/bin/python" -m app.services.observation_worker
fi
