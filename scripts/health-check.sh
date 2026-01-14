#!/bin/bash

# CSI Analysis Health Check Script
# このスクリプトはシステムの健全性をチェックし、問題があれば通知します

LOG_FILE="$HOME/Library/Logs/csi-health-check.log"
CLOUDFLARE_TUNNEL_URL="https://csi.kur048.com"
API_URL="https://api.csi.kur048.com/health"
LOCAL_BACKEND="http://localhost:8000/health"
LOCAL_FRONTEND="http://localhost:3000"

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# エラーカウンター
ERRORS=0

log "=== Health Check Started ==="

# 1. Docker コンテナのチェック
log "Checking Docker containers..."
if docker ps --format '{{.Names}}' | grep -q "csi_"; then
    RUNNING=$(docker ps --filter "name=csi_" --format '{{.Names}}' | wc -l | tr -d ' ')
    EXPECTED=6  # postgres, redis, backend, frontend, ipfs, ganache
    if [ "$RUNNING" -eq "$EXPECTED" ]; then
        log "✓ All Docker containers are running ($RUNNING/$EXPECTED)"
    else
        log "✗ Some Docker containers are not running ($RUNNING/$EXPECTED)"
        docker ps -a --filter "name=csi_" --format 'table {{.Names}}\t{{.Status}}' | tee -a "$LOG_FILE"
        ERRORS=$((ERRORS + 1))
    fi
else
    log "✗ No CSI Docker containers found"
    ERRORS=$((ERRORS + 1))
fi

# 2. Cloudflare Tunnel のチェック
log "Checking Cloudflare Tunnel..."
if pgrep -f "cloudflared tunnel run" > /dev/null; then
    log "✓ Cloudflare Tunnel process is running"

    # Tunnel経由でフロントエンドにアクセス可能かチェック
    if curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$CLOUDFLARE_TUNNEL_URL" | grep -q "200\|301\|302"; then
        log "✓ Cloudflare Tunnel is accessible"
    else
        log "✗ Cloudflare Tunnel is not accessible"
        ERRORS=$((ERRORS + 1))
    fi
else
    log "✗ Cloudflare Tunnel process is not running"
    ERRORS=$((ERRORS + 1))
fi

# 3. バックエンドAPIのチェック
log "Checking Backend API..."
if curl -s -f "$LOCAL_BACKEND" > /dev/null; then
    log "✓ Backend API is healthy"
else
    log "✗ Backend API is not responding"
    ERRORS=$((ERRORS + 1))
fi

# 4. フロントエンドのチェック
log "Checking Frontend..."
if curl -s -o /dev/null -w "%{http_code}" "$LOCAL_FRONTEND" | grep -q "200\|301\|302"; then
    log "✓ Frontend is responding"
else
    log "✗ Frontend is not responding"
    ERRORS=$((ERRORS + 1))
fi

# 5. データベース接続のチェック
log "Checking Database..."
if docker exec csi_postgres pg_isready -U csi_user -d csi_system > /dev/null 2>&1; then
    log "✓ PostgreSQL is ready"
else
    log "✗ PostgreSQL is not ready"
    ERRORS=$((ERRORS + 1))
fi

# 6. Redis接続のチェック
log "Checking Redis..."
if docker exec csi_redis redis-cli ping > /dev/null 2>&1; then
    log "✓ Redis is responding"
else
    log "✗ Redis is not responding"
    ERRORS=$((ERRORS + 1))
fi

# 結果サマリー
log "=== Health Check Completed ==="
if [ $ERRORS -eq 0 ]; then
    log "✓ All systems are healthy"
    exit 0
else
    log "✗ Found $ERRORS issue(s)"
    exit 1
fi
