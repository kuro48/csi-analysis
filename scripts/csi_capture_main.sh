#!/bin/bash
# =============================================================================
# csi_capture_main.sh
# メインCSI（人がいる環境）をPicoScenesで取得しサーバーにアップロードする
#
# 使い方:
#   bash csi_capture_main.sh
#   bash csi_capture_main.sh --session-id ses_20260101_001
#
# 環境変数で設定を上書き可能:
#   CSI_NIC=wlan0 CSI_CHANNEL=6 CSI_SERVER_URL=http://192.168.1.10:8000 bash csi_capture_main.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=csi_config.sh
source "${SCRIPT_DIR}/csi_config.sh"

# ============================================================
# 引数パース
# ============================================================
SESSION_ID=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --session-id)
            SESSION_ID="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--session-id <id>]"
            exit 1
            ;;
    esac
done

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="${MAIN_CSI_DIR}/csi_${TIMESTAMP}"
CSI_FILE="${OUTPUT_FILE}.csi"

# collection_start_time を ISO8601 形式で生成（例: 2026-01-01T12:00:00+09:00）
COLLECTION_START_TIME=$(date -Iseconds)

# ============================================================
# メイン処理
# ============================================================

echo "================================================"
echo " PicoScenes CSI Capture - MAIN (with person)"
echo " NIC Index  : ${NIC_INDEX}"
echo " Duration   : ${MAIN_CSI_DURATION}s"
echo " Session ID : ${SESSION_ID:-<auto>}"
echo " Output     : ${CSI_FILE}"
echo " Upload     : ${MAIN_CSI_UPLOAD_URL}"
echo "================================================"
echo ""
echo "!!! 注意: 計測対象者を計測エリアに配置してから Enter を押してください !!!"
read -r -p "準備ができたら Enter キーを押してください..."
echo ""

mkdir -p "$MAIN_CSI_DIR"

# Step 1: CSI取得（PicoScenesがNICモードを自動管理）
run_picoscenes "$OUTPUT_FILE" "$MAIN_CSI_DURATION"

# Step 2: ファイル確認
check_csi_file "$CSI_FILE"

# Step 3: アップロード用フォームフィールドを組み立て
EXTRA_FORM_ARGS=(
    -F "collection_start_time=${COLLECTION_START_TIME}"
    -F "collection_duration=${MAIN_CSI_DURATION}"
)
if [[ -n "$SESSION_ID" ]]; then
    EXTRA_FORM_ARGS+=(-F "session_id=${SESSION_ID}")
fi

# Step 4: アップロード
upload_csi "$MAIN_CSI_UPLOAD_URL" "$CSI_FILE" "${EXTRA_FORM_ARGS[@]}"

echo ""
echo "================================================"
echo " Main CSI アップロード完了!"
echo " File    : ${CSI_FILE}"
echo " Server  : ${MAIN_CSI_UPLOAD_URL}"
echo " Start   : ${COLLECTION_START_TIME}"
echo " Duration: ${MAIN_CSI_DURATION}s"
echo "================================================"
