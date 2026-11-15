set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
git clone https://github.com/wifisensing/PicoScenes-Python-Toolbox.git "$CSI_ZKP_ROOT/sources/PicoScenes-Python-Toolbox"
cd "$CSI_ZKP_ROOT/sources/PicoScenes-Python-Toolbox"
git checkout --detach f676855accedf79e848bf2f1d10ee5c1f649a33a
git submodule update --init --recursive
git rev-parse HEAD
git submodule status --recursive
