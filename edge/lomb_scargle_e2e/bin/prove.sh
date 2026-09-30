#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
NODE_BIN="${NODE_BIN:-node}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
SOURCE="${1:-}"
OUTPUT="${2:-$PWD/lomb_scargle_proof.json}"

if [[ -z "$SOURCE" ]]; then
  echo "usage: $0 INPUT.csi|INPUT.npz|INPUT.json [OUTPUT.json]" >&2
  exit 2
fi
if [[ ! -f "$SOURCE" ]]; then
  echo "input file not found: $SOURCE" >&2
  exit 2
fi

for required in \
  "$PACKAGE_DIR/artifacts/csi_lomb_scargle_end_to_end.wasm" \
  "$PACKAGE_DIR/artifacts/csi_lomb_scargle_end_to_end_final.zkey" \
  "$PACKAGE_DIR/artifacts/verification_key.json" \
  "$PACKAGE_DIR/artifacts/generate_witness.js" \
  "$PACKAGE_DIR/artifacts/witness_calculator.js" \
  "$PACKAGE_DIR/vendor/runtime/node_modules/snarkjs/build/cli.cjs"; do
  if [[ ! -f "$required" ]]; then
    echo "package is incomplete: missing $required" >&2
    exit 3
  fi
done

if ! command -v "$NODE_BIN" >/dev/null 2>&1; then
  echo "Node.js is required (set NODE_BIN if it is not named node)" >&2
  exit 3
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required (set PYTHON_BIN if it is not named python3)" >&2
  exit 3
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/csi-lomb-e2e.XXXXXX")"
cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT INT TERM

INPUT_JSON="$WORK_DIR/input.json"
METADATA_JSON="$WORK_DIR/input_metadata.json"
case "${SOURCE##*.}" in
  json)
    cp -- "$SOURCE" "$INPUT_JSON"
    ;;
  csi|npz)
    "$PYTHON_BIN" "$PACKAGE_DIR/bin/prepare_input.py" "$SOURCE" "$INPUT_JSON" --metadata "$METADATA_JSON"
    ;;
  *)
    echo "supported inputs are .csi, .npz, and canonical .json" >&2
    exit 2
    ;;
esac

STARTED="$(date +%s)"
"$NODE_BIN" "$PACKAGE_DIR/artifacts/generate_witness.js" \
  "$PACKAGE_DIR/artifacts/csi_lomb_scargle_end_to_end.wasm" \
  "$INPUT_JSON" \
  "$WORK_DIR/witness.wtns"
WITNESS_DONE="$(date +%s)"

"$NODE_BIN" "$PACKAGE_DIR/vendor/runtime/node_modules/snarkjs/build/cli.cjs" groth16 prove \
  "$PACKAGE_DIR/artifacts/csi_lomb_scargle_end_to_end_final.zkey" \
  "$WORK_DIR/witness.wtns" \
  "$WORK_DIR/proof.json" \
  "$WORK_DIR/public.json"
PROOF_DONE="$(date +%s)"

"$NODE_BIN" "$PACKAGE_DIR/vendor/runtime/node_modules/snarkjs/build/cli.cjs" groth16 verify \
  "$PACKAGE_DIR/artifacts/verification_key.json" \
  "$WORK_DIR/public.json" \
  "$WORK_DIR/proof.json"
VERIFY_DONE="$(date +%s)"

"$PYTHON_BIN" "$PACKAGE_DIR/bin/build_result.py" \
  --proof "$WORK_DIR/proof.json" \
  --public "$WORK_DIR/public.json" \
  --output "$OUTPUT"

echo "proof written: $OUTPUT"
echo "witness_seconds=$((WITNESS_DONE - STARTED)) proof_seconds=$((PROOF_DONE - WITNESS_DONE)) verify_seconds=$((VERIFY_DONE - PROOF_DONE))"

if [[ "${DELETE_SOURCE_AFTER_PROOF:-0}" == "1" && "${SOURCE##*.}" != "json" ]]; then
  rm -- "$SOURCE"
  echo "source deleted after successful proof: $SOURCE"
fi
