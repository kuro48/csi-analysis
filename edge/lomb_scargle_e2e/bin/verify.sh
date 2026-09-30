#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
NODE_BIN="${NODE_BIN:-node}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
RESULT="${1:-}"
if [[ -z "$RESULT" || ! -f "$RESULT" ]]; then
  echo "usage: $0 PROOF_RESULT.json" >&2
  exit 2
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csi-lomb-verify.XXXXXX")"
trap 'rm -rf -- "$WORK_DIR"' EXIT INT TERM

python3 - "$RESULT" "$WORK_DIR" <<'PY'
import json
import sys
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())
work = Path(sys.argv[2])
(work / "proof.json").write_text(json.dumps(source["proof"], separators=(",", ":")))
(work / "public.json").write_text(json.dumps(source["publicSignals"], separators=(",", ":")))
PY

"$NODE_BIN" "$PACKAGE_DIR/vendor/runtime/node_modules/snarkjs/build/cli.cjs" groth16 verify \
  "$PACKAGE_DIR/artifacts/verification_key.json" \
  "$WORK_DIR/public.json" \
  "$WORK_DIR/proof.json"
