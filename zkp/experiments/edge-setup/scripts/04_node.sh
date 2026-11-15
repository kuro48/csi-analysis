set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/downloads"
curl --fail --show-error --location --retry 3 --max-time 180 -O https://nodejs.org/dist/v22.23.3/node-v22.23.3-linux-x64.tar.xz
curl --fail --show-error --location --retry 3 --max-time 60 -o node-v22.23.3-SHASUMS256.txt https://nodejs.org/dist/v22.23.3/SHASUMS256.txt
grep ' node-v22.23.3-linux-x64.tar.xz$' node-v22.23.3-SHASUMS256.txt | sha256sum --check -
tar -xJf node-v22.23.3-linux-x64.tar.xz -C "$CSI_ZKP_ROOT/tools"
node --version
npm --version
command -v node npm
