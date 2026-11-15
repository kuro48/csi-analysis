set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
python3 -m pip install 'numpy==1.26.4'
python3 -c 'import numpy as np; print("numpy", np.__version__); a=np.array([3+4j]); print("complex array smoke test", np.abs(a)); assert np.abs(a)[0] == 5'
