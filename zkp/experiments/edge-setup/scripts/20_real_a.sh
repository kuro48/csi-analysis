set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/packages/lomb_scargle_e2e"
test ! -e "$CSI_ZKP_ROOT/results/real_20261005_115619.json"
/usr/bin/time -v ./bin/prove.sh /home/infonetworking/csi_data/main/csi_20261005_115619.csi "$CSI_ZKP_ROOT/results/real_20261005_115619.json"
