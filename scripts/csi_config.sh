#!/bin/bash
# =============================================================================
# csi_config.sh
# CSI取得スクリプト共通設定・関数
# このファイルは直接実行せず、他のスクリプトから source して使う
# =============================================================================

# ============================================================
# ハードウェア設定（環境に合わせて変更してください）
# ============================================================
NIC_INDEX="${CSI_NIC_INDEX:-2}"     # PicoScenesの -i オプションで指定するインターフェースID
                                    # array_status コマンドで確認可能

# ============================================================
# サーバー設定（環境に合わせて変更してください）
# ============================================================
SERVER_URL="${CSI_SERVER_URL:-http://api.csi.kur048.com}"
API_BASE="${SERVER_URL}/api/v2"

# ============================================================
# 計測時間設定
# ============================================================
BASE_CSI_DURATION="${CSI_BASE_DURATION:-60}"   # ベースCSI計測時間 [秒]
MAIN_CSI_DURATION="${CSI_MAIN_DURATION:-60}"   # メインCSI計測時間 [秒]

# ============================================================
# アップロード先URL
# ============================================================
BASE_CSI_UPLOAD_URL="${API_BASE}/base-csi/register-picoscenes"
MAIN_CSI_UPLOAD_URL="${API_BASE}/csi-data/upload-picoscenes"

# ============================================================
# ディレクトリ設定
# ============================================================
OUTPUT_BASE_DIR="${CSI_OUTPUT_DIR:-$HOME/csi_data}"
BASE_CSI_DIR="${OUTPUT_BASE_DIR}/base"
MAIN_CSI_DIR="${OUTPUT_BASE_DIR}/main"

# ============================================================
# 共通関数
# ============================================================

# PicoScenesでCSI取得
# 引数: <output_file_without_ext> <duration_sec>
# PicoScenesは全オプションを1つのクォート文字列として受け取る形式
# -q <秒>: 指定秒後に自動終了（--timeoutではなく-q）
# --output: 出力ファイル名（拡張子なし、PicoScenesが.csiを付与）
run_picoscenes() {
    local output_file="$1"
    local duration="$2"
    local log_file="/tmp/picoscenes_$(date +%Y%m%d_%H%M%S).log"

    echo "[Capture] Starting PicoScenes for ${duration}s..."
    echo "[Capture] Output : ${output_file}.csi"
    echo "[Capture] Log    : ${log_file}"

    PicoScenes "-d debug -i ${NIC_INDEX} --mode logger --output ${output_file} -q ${duration}" \
        > "$log_file" 2>&1 &

    local pid=$!
    echo "[Capture] PicoScenes PID: $pid"

    # 起動直後に即死していないか確認
    sleep 2
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "ERROR: PicoScenes が起動直後に終了しました。ログを確認してください:"
        cat "$log_file"
        return 1
    fi

    for ((i=2; i<=duration; i++)); do
        sleep 1
        printf "\r[Capture] Progress: %d/%d seconds" "$i" "$duration"
    done
    echo ""

    # -q で自動終了しない場合に備えて強制終了
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        wait "$pid" 2>/dev/null || true
    fi

    echo "[Capture] Capture finished."
    echo "[Capture] --- PicoScenes log ---"
    cat "$log_file"
    echo "[Capture] --------------------"
}

# CSIファイルの存在確認
# 引数: <csi_file_path>
check_csi_file() {
    local csi_file="$1"
    if [[ ! -f "$csi_file" ]]; then
        echo "ERROR: CSI file not found: ${csi_file}"
        echo "       PicoScenesのログを確認してください。"
        return 1
    fi
    local file_size
    file_size=$(du -h "$csi_file" | cut -f1)
    echo "[Check] Found: ${csi_file} (${file_size})"
    return 0
}

# HTTPアップロード
# 引数: <upload_url> <csi_file> [extra_curl_form_args...]
upload_csi() {
    local upload_url="$1"
    local csi_file="$2"
    shift 2
    local extra_args=("$@")

    echo "[Upload] Uploading to ${upload_url} ..."

    local http_status
    http_status=$(curl \
        --silent \
        --write-out "%{http_code}" \
        --output /tmp/csi_upload_response.txt \
        -X POST \
        -F "file=@${csi_file}" \
        "${extra_args[@]}" \
        "$upload_url")

    local response_body
    response_body=$(cat /tmp/csi_upload_response.txt)

    if [[ "$http_status" -ge 200 && "$http_status" -lt 300 ]]; then
        echo "[Upload] Success! HTTP ${http_status}"
        echo "[Upload] Response: ${response_body}"
        return 0
    else
        echo "ERROR: Upload failed. HTTP ${http_status}"
        echo "       Response: ${response_body}"
        return 1
    fi
}
