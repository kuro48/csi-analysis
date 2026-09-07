#!/bin/sh
# Lomb-Scargle回路用の2^24 phase-2 Powers of Tau（約19GB）を取得する。
# 途中で切れても再実行すればレジュームする。
set -eu

ZKP_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
KEYS_DIR="${LOMB_PTAU_DIR:-$ZKP_ROOT/keys}"
PTAU_FILE="$KEYS_DIR/powersOfTau28_hez_final_24.ptau"
PTAU_SIZE="${LOMB_PTAU_SIZE:-19327446162}"
PTAU_URL="${LOMB_PTAU_URL:-https://pse-trusted-setup-ppot.s3.eu-central-1.amazonaws.com/pot28_0080/ppot_0080_24.ptau}"

mkdir -p "$KEYS_DIR"

# complete / incomplete を返す。中断した旧ダウンロードの残骸で規定サイズを
# 超えることがあるため、揃っていれば末尾を切り詰める。
# バインドマウント上ではtruncate直後のサイズ報告が遅れるため、
# 過大なサイズは不足と区別して扱う。
ptau_state() {
  if [ ! -f "$PTAU_FILE" ] || [ -f "$PTAU_FILE.aria2" ]; then
    echo incomplete
    return
  fi
  _size="$(wc -c < "$PTAU_FILE")"
  if [ "$_size" -lt "$PTAU_SIZE" ]; then
    echo incomplete
    return
  fi
  if [ "$_size" -gt "$PTAU_SIZE" ]; then
    truncate -s "$PTAU_SIZE" "$PTAU_FILE"
  fi
  echo complete
}

if [ "$(ptau_state)" = complete ]; then
  echo "2^24 Powers of Tau is already present: $PTAU_FILE"
  exit 0
fi

echo "Downloading 2^24 Powers of Tau (about 19GB) from $PTAU_URL"
if command -v aria2c >/dev/null 2>&1; then
  aria2c --continue=true --allow-overwrite=true --auto-file-renaming=false \
    --file-allocation=none --split=16 --max-connection-per-server=16 \
    --dir="$KEYS_DIR" --out="$(basename "$PTAU_FILE")" "$PTAU_URL"
else
  curl --fail --show-error --location --continue-at - \
    --output "$PTAU_FILE" "$PTAU_URL"
fi

if [ "$(ptau_state)" != complete ]; then
  echo "ERROR: 2^24 Powers of Tau download is incomplete" \
    "($(wc -c < "$PTAU_FILE" 2>/dev/null || echo 0)/$PTAU_SIZE bytes)." >&2
  echo "Re-run to resume, or set LOMB_PTAU_URL to another trusted phase-2 ceremony file." >&2
  exit 1
fi

echo "2^24 Powers of Tau is ready: $PTAU_FILE"
