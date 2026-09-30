#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csi-lomb-self-test.XXXXXX")"
trap 'rm -rf -- "$WORK_DIR"' EXIT INT TERM

python3 "$PACKAGE_DIR/bin/make_self_test_input.py" "$WORK_DIR/input.json"
"$PACKAGE_DIR/bin/prove.sh" "$WORK_DIR/input.json" "$WORK_DIR/result.json"
"$PACKAGE_DIR/bin/verify.sh" "$WORK_DIR/result.json"

python3 - "$WORK_DIR/result.json" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())["result"]
assert result["isNormal"] is True, result
assert result["selectedSubcarrier"] == 0, result
assert abs(result["estimatedBpm"] - 15.33) < 1.0, result
assert abs(result["globalPeakBpm"] - 15.33) < 1.0, result
print("self-test passed")
print(json.dumps(result, ensure_ascii=False, indent=2))
PY
