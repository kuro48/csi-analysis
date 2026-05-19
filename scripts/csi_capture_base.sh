#!/bin/bash
# =============================================================================
# csi_capture_base.sh
# ベースCSI（人がいない環境）をPicoScenesで取得しサーバーに登録する
#
# 使い方:
#   bash csi_capture_base.sh
#
# 環境変数で設定を上書き可能:
#   CSI_NIC=wlan0 CSI_CHANNEL=6 CSI_SERVER_URL=http://192.168.1.10:8000 bash csi_capture_base.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=csi_config.sh
source "${SCRIPT_DIR}/csi_config.sh"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="${BASE_CSI_DIR}/csi_${TIMESTAMP}"
CSI_FILE="${OUTPUT_FILE}.csi"

# ============================================================
# メイン処理
# ============================================================

echo "================================================"
echo " PicoScenes CSI Capture - BASE (no person)"
echo " NIC Index: ${NIC_INDEX}"
echo " Duration : ${BASE_CSI_DURATION}s"
echo " Output   : ${CSI_FILE}"
echo " Upload   : ${BASE_CSI_UPLOAD_URL}"
echo "================================================"
echo ""
echo "!!! 注意: 計測エリアに人がいないことを確認してから Enter を押してください !!!"
read -r -p "準備ができたら Enter キーを押してください..."
echo ""

mkdir -p "$BASE_CSI_DIR"

# Step 1: CSI取得（PicoScenesがNICモードを自動管理）
run_picoscenes "$OUTPUT_FILE" "$BASE_CSI_DURATION"

# Step 2: ファイル確認
check_csi_file "$CSI_FILE"

# Step 3: アップロード（base-csi エンドポイントは認証不要）
upload_csi "$BASE_CSI_UPLOAD_URL" "$CSI_FILE"

echo ""
echo "================================================"
echo " Base CSI 登録完了!"
echo " File    : ${CSI_FILE}"
echo " Server  : ${BASE_CSI_UPLOAD_URL}"
echo "================================================"
