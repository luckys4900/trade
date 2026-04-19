#!/usr/bin/env python3
"""
OpenCode内で「agentteams」コマンドを実行するためのエントリーポイント
"""

import sys
import os
from pathlib import Path

# カレントディレクトリをスクリプトのある場所に設定
script_dir = Path(__file__).parent
os.chdir(script_dir)

# agentteams.pyをインポートして実行
try:
    from agentteams import main

    if __name__ == "__main__":
        main()
except ImportError:
    print("❌ agentteams.pyが見つかりません")
    print("💡 スクリプトが存在することを確認してください")
