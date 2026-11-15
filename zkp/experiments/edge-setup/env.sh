# Source this file before running the edge prover. No change to system Python/PicoScenes.
export CSI_ZKP_ROOT=/home/infonetworking/csi-zkp
export UV_PYTHON_INSTALL_DIR="$CSI_ZKP_ROOT/tools/python"
export UV_PYTHON_BIN_DIR="$CSI_ZKP_ROOT/tools/python-bin"
export UV_CACHE_DIR="$CSI_ZKP_ROOT/cache/uv"
export PATH="$CSI_ZKP_ROOT/venv/bin:$CSI_ZKP_ROOT/tools/node-v22.23.3-linux-x64/bin:$CSI_ZKP_ROOT/tools/uv:$PATH"
export NODE_OPTIONS=--max-old-space-size=4096
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export DELETE_SOURCE_AFTER_PROOF=0
