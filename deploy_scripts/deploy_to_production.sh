#!/bin/bash

################################################################################
# Clarity Act Pair Trading v3.0 - Production Deployment Script
# 本番環境デプロイメントスクリプト
#
# 機能:
# - リモート最新版をプル
# - ローカル差分の検出
# - 本番PCへのSSH接続確認
# - rsync によるファイル同期
# - バージョン確認
# - ロールバック対応
################################################################################

set -euo pipefail

# 設定値
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/deploy_${TIMESTAMP}.log"

# 色付き出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログディレクトリ作成
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

# ログ関数
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# 環境変数読み込み
load_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        # .env ファイルから本番PC設定を読み込む
        export $(grep -v '^#' "$PROJECT_ROOT/.env" | grep PRODUCTION | xargs)
    else
        warning ".env ファイルが見つかりません。.env.example をコピーしてください。"
    fi
}

# Git リポジトリの状態確認
check_git_status() {
    log "Git リポジトリ状態を確認中..."
    cd "$PROJECT_ROOT"

    # リモートを確認
    if ! git remote -v | grep -q "origin"; then
        error "リモート 'origin' が設定されていません"
    fi

    # 最新版をフェッチ
    log "リモート最新版をフェッチ中..."
    git fetch origin || error "リモートフェッチに失敗しました"

    # ローカルコミットが未プッシュの場合
    UNPUSHED=$(git rev-list origin/master..master 2>/dev/null | wc -l)
    if [ "$UNPUSHED" -gt 0 ]; then
        warning "ローカルに未プッシュコミット $UNPUSHED 件あります"
    fi

    success "Git 状態確認完了"
}

# 差分検出
detect_changes() {
    log "ローカル/リモート差分を検出中..."

    cd "$PROJECT_ROOT"

    # 変更されたファイルリスト
    CHANGED_FILES=$(git diff --name-only origin/master 2>/dev/null || echo "")

    if [ -z "$CHANGED_FILES" ]; then
        log "差分ファイルはありません"
    else
        log "以下のファイルが変更されています:"
        echo "$CHANGED_FILES" | sed 's/^/  /' | tee -a "$LOG_FILE"
    fi

    # 差分リストをファイルに保存
    echo "$CHANGED_FILES" > "$BACKUP_DIR/changes_${TIMESTAMP}.txt"
}

# バージョンを取得
get_version() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        grep "^VERSION_TAG=" "$PROJECT_ROOT/.env" | cut -d'=' -f2
    else
        echo "v3.0.0-unknown"
    fi
}

# 本番PC接続確認
check_production_connection() {
    if [ -z "${PRODUCTION_HOST:-}" ]; then
        warning "本番PC ホストが設定されていません (.env ファイルを確認)"
        return 1
    fi

    log "本番PC ($PRODUCTION_HOST) への接続を確認中..."

    if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        "${PRODUCTION_USER}@${PRODUCTION_HOST}" "echo 'Connection OK'" > /dev/null 2>&1; then
        success "本番PC への接続確認完了"
        return 0
    else
        error "本番PC への接続に失敗しました"
    fi
}

# バックアップ作成
create_backup() {
    if [ -z "${PRODUCTION_HOST:-}" ]; then
        log "本番PC設定がないためバックアップをスキップします"
        return
    fi

    log "本番PC からバックアップを作成中..."

    REMOTE_BACKUP_DIR="/tmp/trade_backup_${TIMESTAMP}"

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" \
        "mkdir -p $REMOTE_BACKUP_DIR && \
         cp -r ${PRODUCTION_DATA_DIR:-/home/user/trade/data} $REMOTE_BACKUP_DIR/ 2>/dev/null || true"

    # ローカルにもバックアップをコピー
    rsync -av --delete \
        "${PRODUCTION_USER}@${PRODUCTION_HOST}:$REMOTE_BACKUP_DIR/" \
        "$BACKUP_DIR/remote_backup_${TIMESTAMP}/" \
        2>&1 | tee -a "$LOG_FILE" || warning "リモートバックアップコピーに失敗しました"

    success "バックアップ作成完了: $BACKUP_DIR/remote_backup_${TIMESTAMP}/"
}

# ファイル同期（rsync）
sync_to_production() {
    if [ -z "${PRODUCTION_HOST:-}" ]; then
        log "本番PC設定がないため同期をスキップします"
        return
    fi

    log "本番PC へファイルを同期中..."

    EXCLUDE_PATTERNS=(
        "--exclude=.git"
        "--exclude=.env"
        "--exclude=.env.production"
        "--exclude=.env.local"
        "--exclude=logs/"
        "--exclude=.claude/"
        "--exclude=__pycache__/"
        "--exclude=*.pyc"
        "--exclude=.DS_Store"
        "--exclude=.memsearch/milvus.db"
        "--exclude=backups/"
        "--exclude=data/robinhood_all_txs.json"
    )

    rsync -avz \
        "${EXCLUDE_PATTERNS[@]}" \
        --delete \
        --progress \
        "$PROJECT_ROOT/" \
        "${PRODUCTION_USER}@${PRODUCTION_HOST}:${PRODUCTION_DATA_DIR:-/home/user/trade/}/" \
        2>&1 | tee -a "$LOG_FILE" || error "rsync 同期に失敗しました"

    success "ファイル同期完了"
}

# バージョン確認
verify_version() {
    if [ -z "${PRODUCTION_HOST:-}" ]; then
        log "本番PC設定がないためバージョン確認をスキップします"
        return
    fi

    log "本番PC のバージョンを確認中..."

    REMOTE_VERSION=$(ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" \
        "grep '^VERSION_TAG=' ${PRODUCTION_DATA_DIR:-/home/user/trade/}.env 2>/dev/null | cut -d'=' -f2" || echo "unknown")

    LOCAL_VERSION=$(get_version)

    log "ローカルバージョン: $LOCAL_VERSION"
    log "本番PC バージョン: $REMOTE_VERSION"

    if [ "$LOCAL_VERSION" == "$REMOTE_VERSION" ]; then
        success "バージョン確認完了"
    else
        warning "バージョンが一致していません"
    fi
}

# ロールバック機能
rollback() {
    if [ -z "${PRODUCTION_HOST:-}" ]; then
        error "本番PC設定がないためロールバックできません"
    fi

    BACKUP_PATH="$1"

    if [ ! -d "$BACKUP_PATH" ]; then
        error "バックアップパスが見つかりません: $BACKUP_PATH"
    fi

    log "ロールバック中: $BACKUP_PATH"

    rsync -avz --delete \
        "$BACKUP_PATH/" \
        "${PRODUCTION_USER}@${PRODUCTION_HOST}:${PRODUCTION_DATA_DIR:-/home/user/trade/}/" \
        2>&1 | tee -a "$LOG_FILE"

    success "ロールバック完了"
}

# メイン処理
main() {
    log "=========================================="
    log "Clarity Act Pair Trading v3.0 - Production Deployment"
    log "=========================================="

    load_env
    check_git_status
    detect_changes

    if [ "${1:-}" == "--no-backup" ]; then
        log "バックアップをスキップします"
    else
        create_backup
    fi

    if [ "${1:-}" == "--dry-run" ]; then
        log "ドライラン: 実際の同期は実行されません"
        rsync --dry-run -avz \
            --exclude=.git \
            --exclude=.env \
            --exclude=logs/ \
            "$PROJECT_ROOT/" \
            "${PRODUCTION_USER}@${PRODUCTION_HOST}:${PRODUCTION_DATA_DIR:-/home/user/trade/}/"
    else
        check_production_connection || warning "本番PC への接続がないため同期をスキップします"
        sync_to_production
        verify_version
    fi

    log "=========================================="
    success "デプロイメント完了"
    log "ログファイル: $LOG_FILE"
    log "=========================================="
}

# 使用法表示
usage() {
    cat << EOF
使用法: $0 [OPTIONS]

オプション:
  --dry-run       ドライラン（実際には同期しない）
  --no-backup     バックアップをスキップ
  --rollback PATH 指定したバックアップからロールバック
  -h, --help      このヘルプを表示

例:
  $0                           # 通常のデプロイメント
  $0 --dry-run                 # ドライラン
  $0 --rollback ./backups/xxx  # ロールバック

EOF
}

# コマンドラインオプション処理
if [ $# -gt 0 ] && [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    usage
    exit 0
elif [ $# -gt 0 ] && [ "$1" == "--rollback" ]; then
    if [ $# -lt 2 ]; then
        error "--rollback にはパスが必要です"
    fi
    rollback "$2"
else
    main "$@"
fi
