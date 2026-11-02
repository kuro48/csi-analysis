#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${FABRIC_WORK_DIR:-$ROOT/.local/fabric}"
ROLE="${1:?Usage: bridge.sh reader|writer}"
[[ "$ROLE" == reader || "$ROLE" == writer ]]
export FABRIC_GATEWAY_CONFIG="$WORK/gateway-$ROLE.json"
export FABRIC_BRIDGE_ROLE="$ROLE"
export FABRIC_BRIDGE_TOKEN="$(cat "$WORK/$ROLE.token")"
exec node "$ROOT/fabric/gateway-server.mjs"
