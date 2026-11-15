set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/downloads"
sha256sum --check csi-lomb-e2e-edge-20261019.tar.gz.sha256
test ! -e "$CSI_ZKP_ROOT/packages/lomb_scargle_e2e"
tar -xzf csi-lomb-e2e-edge-20261019.tar.gz -C "$CSI_ZKP_ROOT/packages"
cd "$CSI_ZKP_ROOT/packages/lomb_scargle_e2e"
./install.sh
node -p '"snarkjs " + require("./vendor/runtime/node_modules/snarkjs/package.json").version'
sha256sum artifacts/csi_lomb_scargle_end_to_end.wasm artifacts/csi_lomb_scargle_end_to_end_final.zkey artifacts/verification_key.json
du -sh . artifacts vendor/runtime
