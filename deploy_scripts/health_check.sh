#!/bin/bash

################################################################################
# Clarity Act Pair Trading v3.0 - Health Check Script
# 本番環境ヘルスチェックスクリプト
#
# 機能:
# - Hyperliquid API 接続確認
# - Congress.gov 接続確認
# - プロセス確認
# - ディスク容量確認
# - ログファイル確認
# - エラーアラート
################################################################################

set -euo pipefail

# 設定値
PROJECT_DIR="${PROJECT_DIR:-$HOME/trade}"
LOG_DIR="$PROJECT_DIR/logs"
DATA_DIR="$PROJECT_DIR/data"
VENV_DIR="$PROJECT_DIR/venv"
HEALTH_LOG="$LOG_DIR/health_check_$(date +%Y%m%d).log"

# 色付き出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘルスチェック結果
HEALTH_STATUS="OK"
ALERT_COUNT=0

# ログ関数
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$HEALTH_LOG"
}

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1" | tee -a "$HEALTH_LOG"
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$HEALTH_LOG"
    ALERT_COUNT=$((ALERT_COUNT + 1))
    HEALTH_STATUS="WARN"
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1" | tee -a "$HEALTH_LOG"
    ALERT_COUNT=$((ALERT_COUNT + 1))
    HEALTH_STATUS="FAIL"
}

# Hyperliquid API 接続確認
check_hyperliquid() {
    log "Hyperliquid API 接続をチェック中..."

    source "$VENV_DIR/bin/activate" 2>/dev/null || true

    python3 << 'PYTHON_CHECK'
import os
import sys
import requests
from datetime import datetime

try:
    # Hyperliquid mainnet API
    response = requests.get("https://api.hyperliquid.xyz/info", timeout=5)
    if response.status_code == 200:
        print(f"Hyperliquid API: OK (status {response.status_code})")
    else:
        print(f"Hyperliquid API: WARNING (status {response.status_code})")
except Exception as e:
    print(f"Hyperliquid API: FAIL ({e})")
PYTHON_CHECK

    if [ $? -eq 0 ]; then
        check_pass "Hyperliquid API 接続確認"
    else
        check_fail "Hyperliquid API 接続確認"
    fi
}

# Congress.gov API 接続確認
check_congress_api() {
    log "Congress.gov API 接続をチェック中..."

    if timeout 5 curl -s "https://api.congress.gov/v3/bill" \
        -H "Format: json" > /dev/null 2>&1; then
        check_pass "Congress.gov API 接続確認"
    else
        check_warn "Congress.gov API 接続確認 (タイムアウトまたはエラー)"
    fi
}

# プロセス確認
check_processes() {
    log "Python プロセスをチェック中..."

    # 仮想環境を有効化
    source "$VENV_DIR/bin/activate" 2>/dev/null || true

    # qwen_unified_live.py が実行中か確認
    if pgrep -f "qwen_unified_live.py" > /dev/null 2>&1; then
        check_pass "Main Bot (qwen_unified_live.py) が実行中"
    else
        check_warn "Main Bot (qwen_unified_live.py) が実行されていません"
    fi

    # whale_monitor.py が実行中か確認
    if pgrep -f "whale_monitor.py" > /dev/null 2>&1; then
        check_pass "Whale Monitor が実行中"
    else
        check_warn "Whale Monitor が実行されていません"
    fi

    # macro_filter.py が実行中か確認
    if pgrep -f "macro_filter.py" > /dev/null 2>&1; then
        check_pass "Macro Filter が実行中"
    else
        check_warn "Macro Filter が実行されていません"
    fi
}

# ディスク容量確認
check_disk_space() {
    log "ディスク容量をチェック中..."

    # プロジェクトディレクトリのディスク使用量
    DISK_USAGE=$(du -sh "$PROJECT_DIR" | awk '{print $1}')
    log "プロジェクトディレクトリサイズ: $DISK_USAGE"

    # ファイルシステムの空き容量
    ROOT_USAGE=$(df "$PROJECT_DIR" | tail -1 | awk '{print $5}' | tr -d '%')
    ROOT_AVAILABLE=$(df "$PROJECT_DIR" | tail -1 | awk '{print $4}')

    if [ "$ROOT_USAGE" -gt 90 ]; then
        check_fail "ディスク容量がほぼ満杯です ($ROOT_USAGE% 使用中)"
    elif [ "$ROOT_USAGE" -gt 80 ]; then
        check_warn "ディスク容量が不足しています ($ROOT_USAGE% 使用中)"
    else
        check_pass "ディスク容量: $ROOT_USAGE% 使用中 ($ROOT_AVAILABLE 利用可能)"
    fi

    # ログディレクトリのサイズ
    LOG_SIZE=$(du -sh "$LOG_DIR" 2>/dev/null | awk '{print $1}' || echo "0")
    log "ログディレクトリサイズ: $LOG_SIZE"
}

# ログファイル確認
check_log_files() {
    log "ログファイルをチェック中..."

    # 最新のログを確認
    LATEST_LOGS=(
        "$LOG_DIR/main_bot.log"
        "$LOG_DIR/whale_monitor.log"
        "$LOG_DIR/macro_filter.log"
    )

    for LOG_FILE in "${LATEST_LOGS[@]}"; do
        if [ -f "$LOG_FILE" ]; then
            # ファイルの最終更新時刻
            LAST_MODIFIED=$(stat -f %m "$LOG_FILE" 2>/dev/null || stat -c %Y "$LOG_FILE" 2>/dev/null || date +%s)
            CURRENT_TIME=$(date +%s)
            TIME_DIFF=$((CURRENT_TIME - LAST_MODIFIED))

            # 30分（1800秒）以上更新がない場合は警告
            if [ $TIME_DIFF -gt 1800 ]; then
                check_warn "$(basename $LOG_FILE) は 30分以上更新されていません"
            else
                check_pass "$(basename $LOG_FILE) は最近更新されています"
            fi

            # ログファイルのエラー行数
            ERROR_COUNT=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo 0)
            if [ "$ERROR_COUNT" -gt 10 ]; then
                check_warn "$(basename $LOG_FILE) に $ERROR_COUNT 件のエラーが含まれています"
            fi
        else
            check_warn "ログファイルが見つかりません: $(basename $LOG_FILE)"
        fi
    done
}

# 設定ファイル確認
check_config_files() {
    log "設定ファイルをチェック中..."

    if [ -f "$PROJECT_DIR/.env" ]; then
        check_pass ".env ファイルが存在します"

        # API キーが設定されているか確認
        if grep -q "HYPERLIQUID_API_KEY=your_" "$PROJECT_DIR/.env" 2>/dev/null; then
            check_fail "HYPERLIQUID_API_KEY がまだデフォルト値です"
        else
            check_pass "HYPERLIQUID_API_KEY が設定されています"
        fi
    else
        check_fail ".env ファイルが見つかりません"
    fi

    # requirements.txt の確認
    if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
        check_warn "requirements.txt が見つかりません"
    else
        check_pass "requirements.txt が存在します"
    fi
}

# cron ジョブ確認
check_cron_jobs() {
    log "cron ジョブをチェック中..."

    if crontab -l 2>/dev/null | grep -q "qwen_unified_live.py"; then
        CRON_ENTRIES=$(crontab -l 2>/dev/null | grep -c "qwen_unified\|whale_monitor\|macro_filter" || echo 0)
        check_pass "cron ジョブが設定されています ($CRON_ENTRIES 件)"
    else
        check_warn "cron ジョブが設定されていません"
    fi
}

# システム情報
print_system_info() {
    log "システム情報:"
    log "  ホスト名: $(hostname)"
    log "  OS: $(uname -s)"
    log "  アップタイム: $(uptime | awk -F'load average' '{print $1}' | xargs)"
    log "  メモリ使用量: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
    log "  プロセス数: $(ps -e | wc -l)"

    # Python バージョン
    source "$VENV_DIR/bin/activate" 2>/dev/null || true
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    log "  Python バージョン: $PYTHON_VERSION"
}

# メイン処理
main() {
    log "=========================================="
    log "Clarity Act Pair Trading v3.0 - Health Check"
    log "=========================================="
    log "実行時刻: $(date '+%Y-%m-%d %H:%M:%S')"
    log "プロジェクトディレクトリ: $PROJECT_DIR"
    log ""

    # 各チェック実行
    print_system_info
    log ""

    check_hyperliquid
    log ""

    check_congress_api
    log ""

    check_processes
    log ""

    check_disk_space
    log ""

    check_log_files
    log ""

    check_config_files
    log ""

    check_cron_jobs
    log ""

    # ヘルスチェック結果
    log "=========================================="
    log "ヘルスチェック結果: $HEALTH_STATUS (アラート: $ALERT_COUNT 件)"
    log "=========================================="

    # Slack アラート（設定されている場合）
    if [ -n "${SLACK_WEBHOOK_URL:-}" ] && [ "$HEALTH_STATUS" != "OK" ]; then
        send_slack_alert
    fi

    return $([ "$HEALTH_STATUS" = "OK" ] && echo 0 || echo 1)
}

# Slack アラート送信
send_slack_alert() {
    log "Slack アラートを送信中..."

    PAYLOAD=$(cat <<EOF
{
    "text": "Clarity Act Health Check Alert",
    "attachments": [
        {
            "color": "$([ "$HEALTH_STATUS" = "FAIL" ] && echo "danger" || echo "warning")",
            "fields": [
                {
                    "title": "Status",
                    "value": "$HEALTH_STATUS",
                    "short": true
                },
                {
                    "title": "Alerts",
                    "value": "$ALERT_COUNT",
                    "short": true
                },
                {
                    "title": "Hostname",
                    "value": "$(hostname)",
                    "short": true
                },
                {
                    "title": "Time",
                    "value": "$(date '+%Y-%m-%d %H:%M:%S')",
                    "short": true
                }
            ]
        }
    ]
}
EOF
    )

    curl -X POST "$SLACK_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "$PAYLOAD" > /dev/null 2>&1 || true
}

# ヘルスチェックレポート生成
generate_health_report() {
    log ""
    log "ヘルスチェックレポートを生成中..."

    REPORT_FILE="$LOG_DIR/health_report_$(date +%Y%m%d_%H%M%S).json"

    cat > "$REPORT_FILE" << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "status": "$HEALTH_STATUS",
    "alert_count": $ALERT_COUNT,
    "checks": {
        "hyperliquid_api": "pending",
        "congress_api": "pending",
        "processes": "pending",
        "disk_space": "pending",
        "log_files": "pending",
        "config_files": "pending",
        "cron_jobs": "pending"
    }
}
EOF

    log "レポートを保存しました: $REPORT_FILE"
}

# メイン実行
mkdir -p "$LOG_DIR"
main
RESULT=$?

generate_health_report

exit $RESULT
