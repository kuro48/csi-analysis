set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/packages/lomb_scargle_e2e"
/usr/bin/time -v ./bin/self_test.sh
