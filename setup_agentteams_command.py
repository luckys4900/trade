#!/usr/bin/env python3
"""
opencode内で 'agentteams' コマンドを実行するための設定
"""

import os
import sys
from pathlib import Path


def setup_opencode_command():
    """opencodeで 'agentteams' コマンドを有効にする設定"""

    # opencodeの設定ディレクトリを確認
    opencode_config = Path.home() / ".config" / "opencode"
    if not opencode_config.exists():
        opencode_config.mkdir(parents=True, exist_ok=True)

    # エイリアス設定ファイルを作成
    alias_file = opencode_config / "aliases"

    # 既存のエイリアスを読み込む
    aliases = {}
    if alias_file.exists():
        with open(alias_file, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    aliases[key.strip()] = value.strip()

    # agentteamsエイリアスを追加
    aliases["agentteams"] = str(Path(__file__).parent / "agentteams_command.py")

    # エイリアスファイルを書き出し
    with open(alias_file, "w", encoding="utf-8") as f:
        f.write("# GLM Agent Teams Commands\n")
        f.write("# agentteams - GLMエージェントシステムを起動\n")
        for key, value in aliases.items():
            f.write(f"{key}={value}\n")

    print(f"✅ opencodeコマンド 'agentteams' を設定しました")
    print(f"📁 設定ファイル: {alias_file}")
    print(f"🔧 使用方法: agentteams [start|status|stop|help]")


if __name__ == "__main__":
    setup_opencode_command()
