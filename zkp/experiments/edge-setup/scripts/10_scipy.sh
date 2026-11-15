set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
python3 -m pip install 'scipy==1.15.3'
python3 -c 'import scipy; from scipy.signal import lombscargle; print("scipy", scipy.__version__); print("Lomb-Scargle import:", callable(lombscargle))'
