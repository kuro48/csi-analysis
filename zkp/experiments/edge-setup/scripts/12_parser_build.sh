set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
cd "$CSI_ZKP_ROOT/sources/PicoScenes-Python-Toolbox"
/usr/bin/time -v python3 -m pip install --no-build-isolation .
cd "$CSI_ZKP_ROOT"
python3 -c 'import picoscenes; from picoscenes import Picoscenes; print("picoscenes module:", picoscenes.__file__); print("parser class:", Picoscenes)'
python3 -m pip check
