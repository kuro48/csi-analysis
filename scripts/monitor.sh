#!/bin/bash

# CSI Analysis Monitoring Script
# このスクリプトは定期的にシステムを監視し、問題があれば自動復旧を試みます

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$HOME/Library/Logs/csi-monitor.log"

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Monitor Check Started ==="

# Dockerコンテナの自動復旧
check_and_restart_docker() {
    log "Checking Docker containers..."
    RUNNING=$(docker ps --filter "name=csi_" --format '{{.Names}}' | wc -l | tr -d ' ')
    EXPECTED=6

    if [ "$RUNNING" -lt "$EXPECTED" ]; then
        log "⚠ Only $RUNNING/$EXPECTED containers running. Restarting..."
        cd "$PROJECT_DIR" || exit 1
        docker-compose up -d
        sleep 10

        NEW_RUNNING=$(docker ps --filter "name=csi_" --format '{{.Names}}' | wc -l | tr -d ' ')
        if [ "$NEW_RUNNING" -eq "$EXPECTED" ]; then
            log "✓ Successfully restarted Docker containers"
        else
            log "✗ Failed to restart all containers ($NEW_RUNNING/$EXPECTED)"
        fi
    else
        log "✓ Docker containers are healthy"
    fi
}

# Cloudflare Tunnelの自動復旧
check_and_restart_tunnel() {
    log "Checking Cloudflare Tunnel..."

    if ! pgrep -f "cloudflared tunnel run" > /dev/null; then
        log "⚠ Cloudflare Tunnel is not running. Attempting to restart via launchd..."
        launchctl unload "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist" 2>/dev/null
        sleep 2
        launchctl load "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
        sleep 5

        if pgrep -f "cloudflared tunnel run" > /dev/null; then
            log "✓ Successfully restarted Cloudflare Tunnel"
        else
            log "✗ Failed to restart Cloudflare Tunnel"
        fi
    else
        # Tunnelが動いていてもアクセスできない場合は再起動
        if ! curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://csi.kur048.com" | grep -q "200\|301\|302"; then
            log "⚠ Tunnel is running but not accessible. Restarting..."
            launchctl unload "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist" 2>/dev/null
            sleep 2
            launchctl load "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
            sleep 5
        else
            log "✓ Cloudflare Tunnel is healthy"
        fi
    fi
}

# メイン監視ループ
check_and_restart_docker
check_and_restart_tunnel

log "=== Monitor Check Completed ==="
