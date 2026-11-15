set -euxo pipefail
date -Is
id -un
hostname
uname -srm
cat /etc/os-release
lscpu | grep -E 'Architecture:|CPU\(s\):|Model name:|Core\(s\)|Thread\(s\)|Socket\(s\)|CPU max'
free -h
df -h /
python3 --version
command -v PicoScenes gcc g++ make git curl
dpkg-query -W 'picoscenes*'
for tool in node npm circom snarkjs; do command -v "$tool" || true; done
python3 -m pip --version || true
test -f /usr/include/python3.10/Python.h && echo python_headers_present || echo python_headers_missing
sudo -n -l || true
ps -C PicoScenes -o pid,etime,%cpu,%mem,comm
find /home/infonetworking/csi_data -type f -name '*.csi' -printf '%s %p\n'
sha256sum /home/infonetworking/csi_data/main/*.csi /home/infonetworking/rx_2_260616_113124.csi
