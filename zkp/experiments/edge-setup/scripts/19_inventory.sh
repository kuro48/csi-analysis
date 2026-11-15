set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
python3 "$CSI_ZKP_ROOT/scripts/inspect_csi.py"
