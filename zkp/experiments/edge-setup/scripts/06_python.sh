set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
uv python install 3.11.14
uv python find --managed-python 3.11.14
uv venv --python 3.11.14 --managed-python "$CSI_ZKP_ROOT/venv"
python3 --version
python3 -c 'import sys, sysconfig; from pathlib import Path; print("executable:", sys.executable); p=Path(sysconfig.get_path("include"))/"Python.h"; print("headers:", p, "exists:", p.is_file()); assert p.is_file()'
/usr/bin/python3 --version
