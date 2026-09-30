#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$PACKAGE_DIR"

chmod +x bin/*.sh bin/*.py

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node.js 18 or newer is required" >&2
  exit 1
fi
NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "ERROR: Node.js 18 or newer is required (found $(node --version))" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3.10 or newer is required" >&2
  exit 1
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"ERROR: Python 3.10 or newer is required (found {sys.version.split()[0]})")
PY

python3 bin/verify_manifest.py

echo "Environment OK: node=$(node --version) python=$(python3 --version 2>&1)"
echo "Run ./bin/self_test.sh to generate and verify a complete local proof."

if [[ "${1:-}" == "--self-test" ]]; then
  ./bin/self_test.sh
fi
