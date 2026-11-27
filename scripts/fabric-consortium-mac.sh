#!/usr/bin/env bash
# Reader-only API for the real Mac/GMKtec Fabric network; independent of Sepolia.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${FABRIC_CONSORTIUM_WORK_DIR:-$ROOT/.local/fabric-consortium/two-host}"
umask 077
export FABRIC_CONSORTIUM_WORK_DIR="$WORK"
export ADAPTIVE_FABRIC_MANIFEST="$WORK/release/deployment/manifest.json"
export ADAPTIVE_FABRIC_READER_URL="${ADAPTIVE_FABRIC_READER_URL:-https://mac-mini.tail2285b4.ts.net:18843}"
export FABRIC_BRIDGE_CA_FILE="$WORK/research/ca/tls/ca.crt"
export ADAPTIVE_FABRIC_READER_TOKEN="$(cat "$WORK/research/bridge/bridge.token")"
export OBSERVATION_DATA_DIR="$WORK/observations"
export DEBUG=false PUBLIC_MODE=true RESEARCH_MODE=false ENABLE_TEST_ENDPOINTS=false ZKP_AUTO_COMPILE=false
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://100.110.182.121:8085,http://mac-mini.tail2285b4.ts.net:8085,http://127.0.0.1:3015}"
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost/csi_fabric_unused}"
export PICOSCENES_PARSER=python PYTHONPATH="$ROOT/backend"
# Set empty values (rather than unset) to prevent dotenv reintroducing credentials.
export ONCHAIN_MANIFEST= OBSERVATION_MANIFEST= FABRIC_OBSERVATION_MANIFEST= ADAPTIVE_OBSERVATION_MANIFEST=
export FABRIC_WRITER_TOKEN= ADAPTIVE_FABRIC_WRITER_TOKEN= OBSERVATION_RECORDER_PRIVATE_KEY= BLOCKCHAIN_PRIVATE_KEY=
export OBSERVATION_RECORDER_KEY_FILE= ADAPTIVE_RECORDER_KEY_FILE= ADAPTIVE_SEPOLIA_DEPLOYER_KEY_FILE=
for name in jwt.key operator.token; do
  if [[ ! -f "$WORK/$name" ]]; then openssl rand -hex 32 > "$WORK/$name"; fi
done
export JWT_SECRET_KEY="$(cat "$WORK/jwt.key")" OPERATOR_API_TOKEN="$(cat "$WORK/operator.token")"
cd "$ROOT"
case "${1:-api}" in
  api) exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT:-8015}" ;;
  import) shift; exec "$ROOT/.venv/bin/python" scripts/staging/import_fabric_observation.py "$@" ;;
  *) echo 'Usage: fabric-consortium-mac.sh api|import [import arguments]' >&2; exit 1 ;;
esac
