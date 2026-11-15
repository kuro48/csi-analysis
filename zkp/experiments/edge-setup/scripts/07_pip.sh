set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
uv pip install --python "$CSI_ZKP_ROOT/venv/bin/python3" 'pip==26.2.1'
python3 -m pip --version
