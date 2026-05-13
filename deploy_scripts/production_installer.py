#!/usr/bin/env python3

"""
Clarity Act Pair Trading v3.0 - Production Installer
本番環境自動セットアップスクリプト

機能:
- 本番環境の初期セットアップ
- 自動化スクリプト生成
- cron 設定
- ログディレクトリ作成
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ProductionInstaller:
    """本番環境インストーラー"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.venv_dir = project_root / 'venv'
        self.data_dir = project_root / 'data'
        self.logs_dir = project_root / 'logs'
        self.deploy_dir = project_root / 'deploy_scripts'
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def check_prerequisites(self) -> bool:
        """前提条件チェック"""
        logger.info("前提条件をチェック中...")

        # Python 3 の確認
        try:
            import sys
            if sys.version_info < (3, 9):
                logger.error(f"Python 3.9 以上が必要です（現在: {sys.version}）")
                return False
            logger.info(f"Python バージョン: {sys.version}")
        except Exception as e:
            logger.error(f"Python チェックエラー: {e}")
            return False

        # git の確認
        try:
            subprocess.run(['git', '--version'], capture_output=True, check=True)
        except:
            logger.warning("git がインストールされていません")

        return True

    def create_directories(self) -> bool:
        """ディレクトリ構成を作成"""
        logger.info("ディレクトリを作成中...")

        try:
            self.project_root.mkdir(parents=True, exist_ok=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            self.deploy_dir.mkdir(parents=True, exist_ok=True)

            # .gitkeep を作成
            (self.logs_dir / '.gitkeep').touch()

            logger.info("ディレクトリ作成完了")
            return True

        except Exception as e:
            logger.error(f"ディレクトリ作成エラー: {e}")
            return False

    def setup_venv(self) -> bool:
        """Python 仮想環境をセットアップ"""
        logger.info("Python 仮想環境をセットアップ中...")

        try:
            if self.venv_dir.exists():
                logger.warning(f"仮想環境は既に存在します: {self.venv_dir}")
            else:
                subprocess.run(
                    [sys.executable, '-m', 'venv', str(self.venv_dir)],
                    check=True
                )
                logger.info("仮想環境を作成しました")

            # pip をアップグレード
            python_bin = self.venv_dir / 'bin' / 'python3'
            subprocess.run(
                [str(python_bin), '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'],
                check=True,
                capture_output=True
            )
            logger.info("pip をアップグレードしました")

            return True

        except Exception as e:
            logger.error(f"仮想環境セットアップエラー: {e}")
            return False

    def install_dependencies(self) -> bool:
        """依存関係をインストール"""
        logger.info("依存関係をインストール中...")

        requirements_file = self.project_root / 'requirements.txt'

        # requirements.txt がない場合は作成
        if not requirements_file.exists():
            logger.warning("requirements.txt が見つかりません。デフォルト依存関係を作成します。")
            self.create_default_requirements()

        try:
            python_bin = self.venv_dir / 'bin' / 'python3'
            subprocess.run(
                [str(python_bin), '-m', 'pip', 'install', '-r', str(requirements_file)],
                check=True
            )
            logger.info("依存関係をインストールしました")
            return True

        except Exception as e:
            logger.error(f"依存関係インストールエラー: {e}")
            return False

    def create_default_requirements(self):
        """デフォルト requirements.txt を作成"""
        requirements = """# Core Trading
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
"""
        requirements_file = self.project_root / 'requirements.txt'
        requirements_file.write_text(requirements)
        logger.info(f"requirements.txt を作成しました: {requirements_file}")

    def setup_env_file(self) -> bool:
        """環境設定ファイルをセットアップ"""
        logger.info("環境設定ファイルをセットアップ中...")

        env_file = self.project_root / '.env'

        if env_file.exists():
            logger.warning(f".env ファイルは既に存在します: {env_file}")
            return True

        # .env.example をコピー
        env_example = self.project_root / '.env.example'
        if env_example.exists():
            shutil.copy(env_example, env_file)
            logger.info(f".env.example から .env をコピーしました")
        else:
            # デフォルト .env を作成
            env_content = f"""# Hyperliquid Trading API (Production)
HYPERLIQUID_API_KEY=your_api_key_here
HYPERLIQUID_SECRET_KEY=your_secret_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here

# Trading Configuration
TRADING_ENV=production
BASE_POSITION_SIZE=1.0
MAX_POSITION_SIZE=10.0
RISK_LIMIT=0.02

# Production Environment
PRODUCTION_HOST={os.uname().nodename}
PRODUCTION_DATA_DIR={self.data_dir}
PRODUCTION_LOG_DIR={self.logs_dir}

# Monitoring
ENABLE_HEALTH_CHECKS=true
ALERT_EMAIL=
SLACK_WEBHOOK_URL=

# Version
VERSION_TAG=v3.0.0-production
INSTALL_DATE={datetime.now().isoformat()}
"""
            env_file.write_text(env_content)
            logger.info(f".env ファイルを作成しました: {env_file}")

        # パーミッション設定
        os.chmod(env_file, 0o600)
        logger.info(".env ファイルのパーミッションを設定しました (600)")

        return True

    def generate_startup_scripts(self) -> bool:
        """スタートアップスクリプトを生成"""
        logger.info("スタートアップスクリプトを生成中...")

        python_bin = self.venv_dir / 'bin' / 'python3'

        # startup.sh
        startup_script = self.project_root / 'startup.sh'
        startup_content = f"""#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Start processes
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Clarity Act Pair Trading v3.0..."

cd "$PROJECT_DIR"

# Main Bot
echo "Starting Main Bot..."
${{PYTHON_BIN:-python3}} data/qwen_unified_live.py >> "$LOG_DIR/main_bot.log" 2>&1 &
MAIN_PID=$!

# Whale Monitor
echo "Starting Whale Monitor..."
${{PYTHON_BIN:-python3}} whale_monitor.py >> "$LOG_DIR/whale_monitor.log" 2>&1 &
WHALE_PID=$!

# Macro Filter
echo "Starting Macro Filter..."
${{PYTHON_BIN:-python3}} macro_filter.py >> "$LOG_DIR/macro_filter.log" 2>&1 &
MACRO_PID=$!

echo "All systems started."
echo "Main Bot PID: $MAIN_PID"
echo "Whale Monitor PID: $WHALE_PID"
echo "Macro Filter PID: $MACRO_PID"

# Wait for all processes
wait
"""
        startup_script.write_text(startup_content)
        os.chmod(startup_script, 0o755)
        logger.info(f"スタートアップスクリプトを作成しました: {startup_script}")

        # stop.sh
        stop_script = self.project_root / 'stop.sh'
        stop_content = """#!/bin/bash
set -euo pipefail

echo "Stopping Clarity Act Pair Trading systems..."

# Stop processes
pkill -f "qwen_unified_live.py" || true
pkill -f "whale_monitor.py" || true
pkill -f "macro_filter.py" || true

echo "All systems stopped."
"""
        stop_script.write_text(stop_content)
        os.chmod(stop_script, 0o755)
        logger.info(f"ストップスクリプトを作成しました: {stop_script}")

        # status.sh
        status_script = self.project_root / 'status.sh'
        status_content = """#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

echo "=========================================="
echo "Clarity Act Pair Trading - Status Check"
echo "=========================================="
echo ""

# Check processes
echo "Process Status:"
pgrep -f "qwen_unified_live.py" > /dev/null && echo "  Main Bot: RUNNING" || echo "  Main Bot: STOPPED"
pgrep -f "whale_monitor.py" > /dev/null && echo "  Whale Monitor: RUNNING" || echo "  Whale Monitor: STOPPED"
pgrep -f "macro_filter.py" > /dev/null && echo "  Macro Filter: RUNNING" || echo "  Macro Filter: STOPPED"

echo ""
echo "Log Files:"
ls -lh "$LOG_DIR"/*.log 2>/dev/null | tail -5 || echo "  No log files found"

echo ""
echo "Latest Errors (last 10 lines):"
for log in "$LOG_DIR"/*.log; do
    if [ -f "$log" ]; then
        grep -i error "$log" 2>/dev/null | tail -2 || true
    fi
done

echo ""
echo "=========================================="
"""
        status_script.write_text(status_content)
        os.chmod(status_script, 0o755)
        logger.info(f"ステータススクリプトを作成しました: {status_script}")

        return True

    def setup_cron(self) -> bool:
        """cron ジョブをセットアップ"""
        logger.info("cron ジョブをセットアップ中...")

        python_bin = self.venv_dir / 'bin' / 'python3'

        cron_jobs = [
            f"*/1 * * * * cd {self.project_root} && {python_bin} data/qwen_unified_live.py >> {self.logs_dir}/main_bot.log 2>&1",
            f"*/15 * * * * cd {self.project_root} && {python_bin} whale_monitor.py >> {self.logs_dir}/whale_monitor.log 2>&1",
            f"0 * * * * cd {self.project_root} && {python_bin} macro_filter.py >> {self.logs_dir}/macro_filter.log 2>&1",
            f"0 */6 * * * cd {self.project_root} && bash deploy_scripts/health_check.sh >> {self.logs_dir}/health_check.log 2>&1",
        ]

        try:
            # 既存の cron ジョブを確認
            current_crons = subprocess.run(
                ['crontab', '-l'],
                capture_output=True,
                text=True
            )
            existing = current_crons.stdout

            # 既に設定済みか確認
            if 'qwen_unified_live.py' in existing:
                logger.warning("cron ジョブは既に設定されています")
                return True

            # 新しい cron ジョブを追加
            new_crontab = f"""# Clarity Act Pair Trading v3.0 - Automated Jobs
# Generated: {datetime.now().isoformat()}

{chr(10).join(cron_jobs)}
"""

            # crontab に追加
            crontab_input = (existing + '\n' + new_crontab).encode()
            subprocess.run(
                ['crontab', '-'],
                input=crontab_input,
                check=True,
                capture_output=True
            )

            logger.info("cron ジョブを設定しました")
            logger.info("設定内容:")
            for job in cron_jobs:
                logger.info(f"  {job}")

            return True

        except Exception as e:
            logger.error(f"cron セットアップエラー: {e}")
            return False

    def generate_install_report(self) -> bool:
        """インストールレポートを生成"""
        logger.info("インストールレポートを生成中...")

        report = {
            'timestamp': datetime.now().isoformat(),
            'project_root': str(self.project_root),
            'venv_dir': str(self.venv_dir),
            'data_dir': str(self.data_dir),
            'logs_dir': str(self.logs_dir),
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'installed_packages': [],
            'status': 'OK'
        }

        # インストール済みパッケージを取得
        try:
            python_bin = self.venv_dir / 'bin' / 'python3'
            result = subprocess.run(
                [str(python_bin), '-m', 'pip', 'list', '--format=json'],
                capture_output=True,
                text=True,
                check=True
            )
            report['installed_packages'] = json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"インストール済みパッケージ取得エラー: {e}")

        # レポートを保存
        report_file = self.logs_dir / f"install_report_{self.timestamp}.json"
        try:
            report_file.write_text(json.dumps(report, indent=2))
            logger.info(f"レポートを保存しました: {report_file}")
        except Exception as e:
            logger.error(f"レポート保存エラー: {e}")

        return True

    def install(self) -> bool:
        """インストール全体を実行"""
        logger.info("=" * 60)
        logger.info("Clarity Act Pair Trading v3.0 - Production Installer")
        logger.info("=" * 60)
        logger.info(f"プロジェクトディレクトリ: {self.project_root}")
        logger.info("")

        steps = [
            ("前提条件チェック", self.check_prerequisites),
            ("ディレクトリ作成", self.create_directories),
            ("仮想環境セットアップ", self.setup_venv),
            ("依存関係インストール", self.install_dependencies),
            ("環境設定ファイルセットアップ", self.setup_env_file),
            ("スタートアップスクリプト生成", self.generate_startup_scripts),
            ("cron ジョブセットアップ", self.setup_cron),
            ("インストールレポート生成", self.generate_install_report),
        ]

        for step_name, step_func in steps:
            logger.info("")
            logger.info(f">>> {step_name}")
            try:
                result = step_func()
                if not result:
                    logger.error(f"!!! {step_name} が失敗しました")
                    return False
            except Exception as e:
                logger.error(f"!!! {step_name} エラー: {e}")
                return False

        logger.info("")
        logger.info("=" * 60)
        logger.info("インストール完了！")
        logger.info("=" * 60)
        logger.info("")
        logger.info("次のステップ:")
        logger.info(f"  1. .env ファイルを編集してください:")
        logger.info(f"     vi {self.project_root / '.env'}")
        logger.info("")
        logger.info(f"  2. システムを起動してください:")
        logger.info(f"     bash {self.project_root / 'startup.sh'}")
        logger.info("")
        logger.info(f"  3. ステータスを確認してください:")
        logger.info(f"     bash {self.project_root / 'status.sh'}")
        logger.info("")

        return True


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clarity Act Pair Trading v3.0 - Production Installer'
    )
    parser.add_argument('--project-root', type=Path, default=Path.cwd(),
                       help='プロジェクトルートディレクトリ')

    args = parser.parse_args()

    # インストール実行
    installer = ProductionInstaller(args.project_root)
    success = installer.install()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
