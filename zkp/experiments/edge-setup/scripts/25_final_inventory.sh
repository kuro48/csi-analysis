set -euxo pipefail
source /home/infonetworking/csi-zkp/env.sh
python3 "$CSI_ZKP_ROOT/scripts/final_inventory.py"
python3 -m pip check
python3 "$CSI_ZKP_ROOT/packages/lomb_scargle_e2e/bin/verify_manifest.py"
du -sh "$CSI_ZKP_ROOT" "$CSI_ZKP_ROOT"/tools/* "$CSI_ZKP_ROOT/venv" "$CSI_ZKP_ROOT/packages" "$CSI_ZKP_ROOT/results"
df -h /
free -h
ps -C PicoScenes -o pid,etime,%cpu,%mem,comm
sha256sum /home/infonetworking/csi_data/main/*.csi /home/infonetworking/rx_2_260616_113124.csi
find "$CSI_ZKP_ROOT" -maxdepth 2 -type d -not -path '*/cache/*' -not -path '*/.git/*'
