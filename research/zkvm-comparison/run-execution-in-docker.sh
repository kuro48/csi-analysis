#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
RESULTS_DIR="$SCRIPT_DIR/results"
BACKEND_CONTAINER="${CSI_BENCH_BACKEND_CONTAINER:-csi_backend}"
BACKEND_IMAGE="${CSI_BENCH_BACKEND_IMAGE:-csi-analysis-backend}"

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <input.csi> [benchmark options]" >&2
  exit 2
fi

INPUT_ARGUMENT=$1
shift
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

mkdir -p "$RESULTS_DIR"

docker run --rm \
  --platform linux/amd64 \
  --volumes-from "$BACKEND_CONTAINER" \
  --volume "$REPO_ROOT:/workspace:ro" \
  --volume "$INPUT_FILE:/input/input.csi:ro" \
  --volume "$RESULTS_DIR:/results" \
  --env PYTHONPATH=/app \
  --entrypoint python \
  "$BACKEND_IMAGE" \
  /workspace/research/zkvm-comparison/benchmark.py execution \
  --csi-file /input/input.csi \
  "$@"
