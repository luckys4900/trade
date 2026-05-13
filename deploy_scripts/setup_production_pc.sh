#!/bin/bash

################################################################################
# Clarity Act Pair Trading v3.0 - Production PC Setup Script
# 本番PC初期セットアップスクリプト
#
# 機能:
# - Python 環境セットアップ
# - 依存関係インストール
# - Hyperliquid API 設定
# - ディレクトリ構成作成
# - cron 自動実行設定
################################################################################

set -euo pipefail

# 設定値
PYTHON_VERSION="3.9"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$HOME/trade}"
LOG_DIR="$PROJECT_DIR/logs"
DATA_DIR="$PROJECT_DIR/data"
VENV_DIR="$PROJECT_DIR/venv"

# 色付き出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ログ関数
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 前提条件チェック
check_prerequisites() {
    log "前提条件をチェック中..."

    # Python のチェック
    if ! command -v python3 &> /dev/null; then
        error "Python3 がインストールされていません"
    fi

    INSTALLED_PYTHON=$(python3 --version | awk '{print $2}' | cut -d. -f1,2)
    log "Python バージョン: $INSTALLED_PYTHON"

    # git のチェック
    if ! command -v git &> /dev/null; then
        error "git がインストールされていません"
    fi

    success "前提条件チェック完了"
}

# ディレクトリ構成作成
setup_directories() {
    log "ディレクトリ構成を作成中..."

    mkdir -p "$PROJECT_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$DATA_DIR"
    mkdir -p "$PROJECT_DIR/backups"
    mkdir -p "$PROJECT_DIR/deploy_scripts"
    mkdir -p "$PROJECT_DIR/.github/workflows"

    # ログディレクトリに .gitkeep を作成
    touch "$LOG_DIR/.gitkeep"

    success "ディレクトリ構成作成完了"
}

# Python 仮想環境セットアップ
setup_venv() {
    log "Python 仮想環境をセットアップ中..."

    if [ -d "$VENV_DIR" ]; then
        warning "仮想環境は既に存在します: $VENV_DIR"
    else
        python3 -m venv "$VENV_DIR" || error "仮想環境の作成に失敗しました"
    fi

    # 仮想環境をアクティベート
    source "$VENV_DIR/bin/activate" || error "仮想環境のアクティベートに失敗しました"

    # pip をアップグレード
    pip install --upgrade pip setuptools wheel || error "pip のアップグレードに失敗しました"

    success "仮想環境セットアップ完了"
}

# 依存関係インストール
install_dependencies() {
    log "依存関係をインストール中..."

    # 仮想環境をアクティベート
    source "$VENV_DIR/bin/activate" || error "仮想環境のアクティベートに失敗しました"

    # requirements.txt の確認
    if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
        warning "requirements.txt が見つかりません。デフォルト依存関係をインストール..."

        # 基本的な依存関係
        cat > "$PROJECT_DIR/requirements.txt" << 'EOF'
# Core Trading
requests>=2.28.0
websockets>=11.0
numpy>=1.24.0
pandas>=1.5.0

# Hyperliquid API
hyperliquid>=0.1.0

# Data Processing
python-dateutil>=2.8.0
pytz>=2023.3

# Configuration
python-dotenv>=1.0.0
pyyaml>=6.0

# Monitoring
psutil>=5.9.0

# Testing
pytest>=7.0
pytest-cov>=4.0

# Logging
python-json-logger>=2.0.4
EOF
    fi

    pip install -r "$PROJECT_DIR/requirements.txt" || error "依存関係のインストールに失敗しました"

    success "依存関係インストール完了"
}

# Hyperliquid API 設定
setup_hyperliquid() {
    log "Hyperliquid API 設定をセットアップ中..."

    if [ -f "$PROJECT_DIR/.env" ]; then
        warning ".env ファイルは既に存在します"
        return
    fi

    # .env ファイルを作成
    cat > "$PROJECT_DIR/.env" << EOF
# Hyperliquid Trading API (本番環境)
HYPERLIQUID_API_KEY=your_api_key_here
HYPERLIQUID_SECRET_KEY=your_secret_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here

# Trading Configuration
TRADING_ENV=production
BASE_POSITION_SIZE=1.0
MAX_POSITION_SIZE=10.0
RISK_LIMIT=0.02

# Production Environment
PRODUCTION_HOST=$(hostname)
PRODUCTION_DATA_DIR=$DATA_DIR
PRODUCTION_LOG_DIR=$LOG_DIR

# Monitoring
ENABLE_HEALTH_CHECKS=true
ALERT_EMAIL=
SLACK_WEBHOOK_URL=
EOF

    chmod 600 "$PROJECT_DIR/.env" || warning ".env ファイルのパーミッション設定に失敗しました"

    log ".env ファイルを作成しました。API キーを設定してください:"
    log "  vi $PROJECT_DIR/.env"

    success "Hyperliquid API 設定作成完了"
}

# cron スケジュール設定
setup_cron() {
    log "cron スケジュール設定をセットアップ中..."

    # 仮想環境のパス
    PYTHON_BIN="$VENV_DIR/bin/python3"

    # 既存の cron ジョブを確認
    CRON_JOB_MAIN="*/1 * * * * cd $PROJECT_DIR && $PYTHON_BIN data/qwen_unified_live.py >> $LOG_DIR/main_bot.log 2>&1"
    CRON_JOB_WHALE="*/15 * * * * cd $PROJECT_DIR && $PYTHON_BIN whale_monitor.py >> $LOG_DIR/whale_monitor.log 2>&1"
    CRON_JOB_MACRO="0 * * * * cd $PROJECT_DIR && $PYTHON_BIN macro_filter.py >> $LOG_DIR/macro_filter.log 2>&1"
    CRON_JOB_HEALTH="0 */6 * * * cd $PROJECT_DIR && $PYTHON_BIN deploy_scripts/health_check.sh >> $LOG_DIR/health_check.log 2>&1"

    # cron ジョブをインストール（既存の場合はスキップ）
    if ! crontab -l 2>/dev/null | grep -q "qwen_unified_live.py"; then
        log "cron ジョブをインストール中..."

        (
            crontab -l 2>/dev/null || true
            echo "# Clarity Act Pair Trading - Automated Jobs (v3.0)"
            echo "$CRON_JOB_MAIN"
            echo "$CRON_JOB_WHALE"
            echo "$CRON_JOB_MACRO"
            echo "$CRON_JOB_HEALTH"
        ) | crontab - || error "cron ジョブのインストールに失敗しました"

        success "cron ジョブをインストール完了"
    else
        warning "cron ジョブは既にインストールされています"
    fi

    # cron ログ確認
    log "cron ジョブ一覧:"
    crontab -l 2>/dev/null | grep -E "qwen_unified|whale_monitor|macro_filter|health_check" || true
}

# systemd サービス設定（オプション）
setup_systemd() {
    log "systemd サービス設定をセットアップ中..."

    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_USER_DIR"

    # Main Bot Service
    cat > "$SYSTEMD_USER_DIR/trade-main.service" << EOF
[Unit]
Description=Clarity Act Pair Trading - Main Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin"
ExecStart=$PYTHON_BIN data/qwen_unified_live.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/main_bot.log
StandardError=append:$LOG_DIR/main_bot_error.log

[Install]
WantedBy=default.target
EOF

    log "systemd サービスファイルを作成しました:"
    log "  $SYSTEMD_USER_DIR/trade-main.service"
    log ""
    log "有効化するには以下を実行:"
    log "  systemctl --user enable trade-main.service"
    log "  systemctl --user start trade-main.service"
    log ""
    log "ステータス確認:"
    log "  systemctl --user status trade-main.service"
    log "  journalctl --user -u trade-main.service -f"

    success "systemd サービス設定作成完了"
}

# セットアップスクリプト生成
generate_startup_scripts() {
    log "スタートアップスクリプトを生成中..."

    # startup.sh
    cat > "$PROJECT_DIR/startup.sh" << 'EOF'
#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
source "$VENV_DIR/bin/activate"
cd "$PROJECT_DIR"
python3 data/qwen_unified_live.py &
python3 whale_monitor.py &
python3 macro_filter.py &
wait
EOF

    chmod +x "$PROJECT_DIR/startup.sh"

    success "スタートアップスクリプト生成完了: $PROJECT_DIR/startup.sh"
}

# 設定検証
validate_setup() {
    log "セットアップを検証中..."

    # ディレクトリの確認
    for dir in "$PROJECT_DIR" "$LOG_DIR" "$DATA_DIR" "$VENV_DIR"; do
        if [ ! -d "$dir" ]; then
            error "ディレクトリが見つかりません: $dir"
        fi
    done

    # Python 環境の確認
    source "$VENV_DIR/bin/activate" 2>/dev/null || true
    if ! python3 -c "import sys; print(f'Python {sys.version}')" > /dev/null 2>&1; then
        error "Python 環境が正常に設定されていません"
    fi

    success "セットアップ検証完了"
}

# メイン処理
main() {
    log "=========================================="
    log "Clarity Act Pair Trading v3.0 - Production Setup"
    log "=========================================="
    log "プロジェクトディレクトリ: $PROJECT_DIR"
    log ""

    check_prerequisites
    setup_directories
    setup_venv
    install_dependencies
    setup_hyperliquid
    generate_startup_scripts
    setup_cron
    setup_systemd
    validate_setup

    log ""
    log "=========================================="
    success "セットアップ完了！"
    log "=========================================="
    log ""
    log "次のステップ:"
    log "  1. .env ファイルを編集して API キーを設定:"
    log "     vi $PROJECT_DIR/.env"
    log ""
    log "  2. 仮想環境をアクティベート:"
    log "     source $VENV_DIR/bin/activate"
    log ""
    log "  3. システムを起動:"
    log "     $PROJECT_DIR/startup.sh"
    log ""
    log "  4. ステータス確認:"
    log "     crontab -l"
    log ""
}

# 使用法表示
usage() {
    cat << EOF
使用法: $0 [OPTIONS]

オプション:
  --project-dir PATH  プロジェクトディレクトリを指定 (デフォルト: \$HOME/trade)
  --skip-cron         cron 設定をスキップ
  --skip-systemd      systemd 設定をスキップ
  -h, --help          このヘルプを表示

例:
  $0                                    # デフォルト設定
  $0 --project-dir /opt/trade           # 別のディレクトリを指定
  $0 --skip-cron --skip-systemd        # cron と systemd をスキップ

EOF
}

# コマンドラインオプション処理
SKIP_CRON=false
SKIP_SYSTEMD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --project-dir)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --skip-cron)
            SKIP_CRON=true
            shift
            ;;
        --skip-systemd)
            SKIP_SYSTEMD=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "不明なオプション: $1"
            ;;
    esac
done

# VENV_DIR を再計算
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
DATA_DIR="$PROJECT_DIR/data"

# 条件付き実行
main

if [ "$SKIP_CRON" = true ]; then
    warning "cron 設定をスキップしました"
else
    setup_cron
fi

if [ "$SKIP_SYSTEMD" = true ]; then
    warning "systemd 設定をスキップしました"
else
    setup_systemd
fi
