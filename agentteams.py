#!/usr/bin/env python3
"""
GLM Agent Teams - OpenCode内コマンド実行
`agentteams`コマンドでGLMエージェントシステムを起動
"""

import sys
import os
import subprocess
from pathlib import Path


def check_environment():
    """環境チェック"""
    print("🔍 環境をチェック中...")

    # .envファイルの確認
    if not Path(".env").exists():
        print("⚠️  .envファイルが見つかりません")
        if Path(".env.example").exists():
            print("📝 .env.exampleをコピーします")
            import shutil

            shutil.copy(".env.example", ".env")
        print("🔧 .envファイルにAPIキーを設定してください")
        return False

    # Pythonの確認
    try:
        result = subprocess.run(
            [sys.executable, "--version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ Python: {result.stdout.strip()}")
        else:
            print("❌ Pythonが見つかりません")
            return False
    except Exception as e:
        print(f"❌ Python確認失敗: {e}")
        return False

    # openai-swarmライブラリの確認
    try:
        import swarm

        print("✅ openai-swarm: OK")
    except ImportError:
        print("📦 openai-swarmをインストールします...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "openai-swarm"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ openai-swarmのインストール完了")
        else:
            print(f"❌ openai-swarmインストール失敗: {result.stderr}")
            return False

    # Ollamaの確認
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ Ollama: OK")
        else:
            print("⚠️  Ollamaが起動していません")
            print("💡 Ollamaを起動するには: ollama serve")
            choice = input("続行しますか? (y/n): ").lower()
            if choice != "y":
                return False
    except FileNotFoundError:
        print("⚠️  curlコマンドが見つかりません")
        print("💡 Ollamaが起動しているか手動で確認してください")
    except Exception as e:
        print(f"⚠️  Ollama確認失敗: {e}")

    return True


def start_agent_system():
    """GLMエージェントシステムを起動"""
    print("\n🚀 GLM Agent Teams を起動します...")

    # スクリプトの存在確認
    script_path = Path("glm_master_swarm.py")
    if not script_path.exists():
        print("❌ glm_master_swarm.pyが見つかりません")
        return False

    # バックグラウンドで実行
    try:
        # Windowsの場合
        if sys.platform == "win32":
            subprocess.Popen(
                [sys.executable, str(script_path)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            # Unix系の場合
            subprocess.Popen([sys.executable, str(script_path)])

        print("✅ GLM Agent Teams が起動しました")
        print("💡 終了するには 'agentteams_stop' を実行")
        return True
    except Exception as e:
        print(f"❌ 起動失敗: {e}")
        return False


def show_help():
    """ヘルプを表示"""
    print("""
🤖 GLM Agent Teams - ヘルプ

使い方:
  agentteams          - GLMエージェントシステムを起動
  agentteams_status   - 状態を確認
  agentteams_stop     - システムを停止
  agentteams_help     - このヘルプを表示

環境設定:
  1. .envファイルにAPIキーを設定
     OPENROUTER_API_KEY=your_key
     GLM_API_KEY=your_key
     OLLAMA_HOST=http://localhost:11434
  
  2. Ollamaを起動
     ollama serve
  
  3. 必要なライブラリをインストール
     pip install openai-swarm
""")


def check_status():
    """状態を確認"""
    print("📊 GLM Agent Teams 状態確認")

    # Pythonプロセスの確認
    try:
        result = subprocess.run(
            ["tasklist"], capture_output=True, text=True, shell=True
        )
        if "pythonw.exe" in result.stdout:
            print("✅ GLM Agent Teams は実行中")
        else:
            print("⏸️  GLM Agent Teams は停止中")
    except Exception as e:
        print(f"❌ 状態確認失敗: {e}")

    # Ollamaの確認
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ Ollama は起動中")
        else:
            print("⏸️  Ollama は停止中")
    except Exception as e:
        print(f"❌ Ollama確認失敗: {e}")


def stop_agent_system():
    """GLMエージェントシステムを停止"""
    print("🛑 GLM Agent Teams を停止します...")

    try:
        # Pythonプロセスの停止
        subprocess.run(
            ["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True, shell=True
        )
        print("✅ Pythonプロセスを停止")

        # wscriptプロセスの停止
        subprocess.run(
            ["taskkill", "/F", "/IM", "wscript.exe"], capture_output=True, shell=True
        )
        print("✅ wscriptプロセスを停止")

        print("✅ 停止完了")
    except Exception as e:
        print(f"❌ 停止失敗: {e}")


def main():
    """メイン関数"""
    if len(sys.argv) < 2:
        print("📝 使用方法: python agentteams.py <command>")
        print("💡 ヘルプ: python agentteams.py help")
        return

    command = sys.argv[1].lower()

    if command == "start":
        if check_environment():
            start_agent_system()

    elif command == "status":
        check_status()

    elif command == "stop":
        stop_agent_system()

    elif command == "help" or command == "h":
        show_help()

    elif command == "":
        # 引数なしの場合は環境チェックと起動
        if check_environment():
            start_agent_system()

    else:
        print(f"❌ 不明なコマンド: {command}")
        print("💡 ヘルプ: python agentteams.py help")


if __name__ == "__main__":
    main()
