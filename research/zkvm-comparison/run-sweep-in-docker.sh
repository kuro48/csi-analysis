#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BACKEND_CONTAINER="${CSI_BENCH_BACKEND_CONTAINER:-csi_backend}"
BACKEND_IMAGE="${CSI_BENCH_BACKEND_IMAGE:-csi-analysis-backend}"

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <input.csi> <output.json>" >&2
  exit 2
fi

INPUT_ARGUMENT=$1
OUTPUT_ARGUMENT=$2
INPUT_DIR=$(CDPATH= cd -- "$(dirname -- "$INPUT_ARGUMENT")" && pwd)
INPUT_FILE="$INPUT_DIR/$(basename -- "$INPUT_ARGUMENT")"

if [ ! -f "$INPUT_FILE" ]; then
  echo "CSI file not found: $INPUT_FILE" >&2
  exit 2
fi
case "$INPUT_FILE" in
  *.csi) ;;
  *)
    echo "input must have the .csi extension: $INPUT_FILE" >&2
    exit 2
    ;;
esac
case "$OUTPUT_ARGUMENT" in
  *.json) ;;
  *)
    echo "output must have the .json extension: $OUTPUT_ARGUMENT" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname -- "$OUTPUT_ARGUMENT")"
OUTPUT_DIR=$(CDPATH= cd -- "$(dirname -- "$OUTPUT_ARGUMENT")" && pwd)
OUTPUT_NAME=$(basename -- "$OUTPUT_ARGUMENT")

docker run --rm \
  --platform linux/amd64 \
  --volumes-from "$BACKEND_CONTAINER" \
  --volume "$REPO_ROOT:/workspace:ro" \
  --volume "$INPUT_FILE:/input/input.csi:ro" \
  --volume "$OUTPUT_DIR:/results" \
  --env PYTHONPATH=/app \
  --entrypoint python \
  "$BACKEND_IMAGE" \
  /workspace/research/zkvm-comparison/sweep.py \
  --csi-file /input/input.csi \
  --output "/results/$OUTPUT_NAME"
