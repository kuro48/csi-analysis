set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/downloads"
curl --fail --show-error --location --retry 3 --max-time 180 -O https://github.com/astral-sh/uv/releases/download/0.13.1/uv-x86_64-unknown-linux-gnu.tar.gz
curl --fail --show-error --location --retry 3 --max-time 60 -O https://github.com/astral-sh/uv/releases/download/0.13.1/uv-x86_64-unknown-linux-gnu.tar.gz.sha256
sha256sum --check uv-x86_64-unknown-linux-gnu.tar.gz.sha256
mkdir -p "$CSI_ZKP_ROOT/tools/uv"
tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C "$CSI_ZKP_ROOT/tools/uv"
uv --version
