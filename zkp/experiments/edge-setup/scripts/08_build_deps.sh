set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
python3 -m pip install 'setuptools==75.8.2' 'wheel==0.45.1' 'Cython==3.0.12'
python3 -c 'import setuptools, wheel, Cython; print("setuptools", setuptools.__version__); print("wheel", wheel.__version__); print("Cython", Cython.__version__)'
gcc --version | head -1
g++ --version | head -1
