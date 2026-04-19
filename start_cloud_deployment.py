#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Cloud デプロイ自動化スタートスクリプト
gcloud のインストール確認 → デプロイ実行
"""

import subprocess
import sys
import os
import platform

def run_command(cmd, description="", shell=False):
    """コマンド実行"""
    print(f"\n[実行] {description}")
    print(f"コマンド: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    print("-" * 80)

    try:
        if shell:
            result = subprocess.run(cmd, shell=True, text=True)
        else:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            if result.stdout:
                print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 実行失敗: {e}")
        if e.stderr:
            print(f"詳細: {e.stderr}")
        return False
    except FileNotFoundError:
        return False

def check_gcloud():
    """gcloud がインストールされているか確認"""
    print("\n" + "=" * 80)
    print("Google Cloud SDK インストール確認")
    print("=" * 80)

    try:
        result = subprocess.run(
            ["gcloud", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            print("[OK] gcloud はすでにインストール済み")
            print(result.stdout)
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("[ERROR] gcloud が見つかりません")
    return False

def install_gcloud_windows():
    """Windows に gcloud をインストール"""
    print("\n" + "=" * 80)
    print("Google Cloud SDK インストール（Windows）")
    print("=" * 80)

    print("\n[推奨方法] PowerShell でインストール")
    print("  1. PowerShell を「管理者として実行」で開く")
    print("  2. 以下をコピペして実行:")
    print("")
    print("     iwr -useb get.scoop.sh | iex")
    print("     scoop install gcloud")
    print("")

    print("[代替方法] 直接ダウンロード")
    print("  https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe")
    print("")

    print("[代替方法] Chocolatey でインストール")
    print("  choco install google-cloud-sdk")
    print("")

    print("=" * 80)
    print("インストール完了後、このウィンドウに戻ってください。")
    print("=" * 80)

    response = input("\nEnter キーを押してインストール完了を確認: ").strip()

    # 再度確認（複数回試行）
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["gcloud", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                print("\n[OK] gcloud インストール確認完了")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            if attempt < 2:
                print(f"\n再度確認中... ({attempt + 2}/3)")
                import time
                time.sleep(2)

    print("\n[ERROR] gcloud が見つかりません。")
    print("以下を確認してください:")
    print("  1. PowerShell を「管理者として実行」で開いたか")
    print("  2. インストールコマンドが完全に実行されたか")
    print("  3. インストール後、新しい PowerShell ウィンドウを開いたか")
    return False

def install_gcloud_linux():
    """Linux に gcloud をインストール"""
    print("\n" + "=" * 80)
    print("Google Cloud SDK インストール")
    print("=" * 80)

    print("\n以下をターミナルで実行:")
    print("  curl https://sdk.cloud.google.com | bash")
    print("  exec -l $SHELL")
    print("  gcloud init")

    response = input("\nインストール完了後、Enter キーを押してください: ").strip()

    result = subprocess.run(
        ["gcloud", "--version"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("[OK] gcloud インストール確認完了")
        return True
    else:
        print("[ERROR] gcloud が見つかりません。インストールしてください。")
        return False

def main():
    print("\n" + "=" * 80)
    print("BTC Short Trading Bot - Google Cloud 自動デプロイ")
    print("=" * 80)

    # gcloud チェック
    if not check_gcloud():
        print("\n" + "=" * 80)
        print("[重要] Google Cloud SDK をインストールする必要があります")
        print("=" * 80)

        if sys.platform.startswith("win"):
            if not install_gcloud_windows():
                print("\n[エラー] gcloud をインストールできません。")
                print("手動でインストール後、もう一度このスクリプトを実行してください。")
                sys.exit(1)
        else:
            if not install_gcloud_linux():
                print("\n[エラー] gcloud をインストールできません。")
                print("手動でインストール後、もう一度このスクリプトを実行してください。")
                sys.exit(1)

    # gcloud 認証確認
    print("\n" + "=" * 80)
    print("Google Cloud 認証確認")
    print("=" * 80)

    result = subprocess.run(
        ["gcloud", "auth", "list"],
        capture_output=True,
        text=True
    )

    if "ACTIVE" not in result.stdout:
        print("\n[警告] Google Cloud に認証していません")
        print("ブラウザで Google アカウントにログインしてください...")

        if not run_command(
            ["gcloud", "auth", "login"],
            "Google Cloud 認証"
        ):
            print("[ERROR] 認証失敗")
            sys.exit(1)
    else:
        print("[OK] 認証済み")
        print(result.stdout)

    # プロジェクト確認
    print("\n" + "=" * 80)
    print("Google Cloud プロジェクト確認")
    print("=" * 80)

    result = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True,
        text=True
    )

    project_id = result.stdout.strip()

    if not project_id:
        print("[ERROR] プロジェクトが設定されていません")
        print("\n以下を実行してプロジェクトを設定:")
        print("  gcloud projects list")
        print("  gcloud config set project YOUR_PROJECT_ID")
        sys.exit(1)

    print(f"[OK] プロジェクト: {project_id}")

    # Docker 確認
    print("\n" + "=" * 80)
    print("Docker インストール確認")
    print("=" * 80)

    result = subprocess.run(
        ["docker", "--version"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] Docker がインストールされていません")
        print("Docker Desktop をインストール: https://www.docker.com/products/docker-desktop")
        sys.exit(1)

    print("[OK] Docker インストール済み")
    print(result.stdout)

    # デプロイ実行
    print("\n" + "=" * 80)
    print("デプロイを開始します...")
    print("=" * 80)

    trade_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(trade_dir)

    result = subprocess.run(
        [sys.executable, "deploy_to_cloud.py"],
        text=True
    )

    sys.exit(result.returncode)

if __name__ == '__main__':
    main()
