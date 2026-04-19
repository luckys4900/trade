#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Trading Bot - One-Click Cloud Deployment
Google Cloudへの完全自動デプロイ（認証はブラウザで1回のみ）
"""

import subprocess
import sys
import os
import json
import io
import webbrowser
import time

# Windows Unicode対応
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def print_header(text):
    """ヘッダーを表示"""
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80)

def print_step(num, text):
    """ステップを表示"""
    print(f"\n[ステップ {num}] {text}")
    print("-" * 80)

def find_gcloud():
    """gcloud のパスを探す"""
    import shutil

    # Windows 環境でのパス候補
    gcloud_paths = [
        "gcloud",  # PATH に登録されている場合
        "gcloud.cmd",  # Windows コマンド
        os.path.expanduser("~\\AppData\\Roaming\\scoop\\apps\\gcloud\\current\\bin\\gcloud.cmd"),  # Scoop
        os.path.expanduser("~\\AppData\\Roaming\\scoop\\apps\\gcloud\\current\\bin\\gcloud"),  # Scoop (Unix形式)
        os.path.expanduser("~\\scoop\\apps\\gcloud\\current\\bin\\gcloud.cmd"),  # Scoop (ユーザーインストール)
        os.path.expanduser("~\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin\\gcloud.cmd"),  # 直接インストール
        "C:\\Program Files\\Google\\Cloud SDK\\google-cloud-sdk\\bin\\gcloud.cmd",  # デフォルトパス
    ]

    for path in gcloud_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run([path, "--version"], capture_output=True, check=True, timeout=5)
                if result.returncode == 0:
                    return path
            except:
                continue

    # shutil.which で PATH 内を検索
    gcloud = shutil.which("gcloud")
    if gcloud:
        return gcloud

    return "gcloud"  # フォールバック

def run_cmd(cmd, description="", check=True):
    """コマンドを実行"""
    print(f"実行中: {description}")

    # gcloud コマンドを置き換え
    gcloud_path = find_gcloud()
    cmd = cmd.replace("gcloud ", f"{gcloud_path} ")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.stdout:
            print(result.stdout)
        if result.returncode != 0 and check:
            print(f"[ERROR] {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

def download_gcloud():
    """Google Cloud SDKをダウンロード＆インストール"""
    print_step(1, "Google Cloud SDK をセットアップ")

    if sys.platform.startswith('win'):
        # Windows: PowerShellでインストール
        print("PowerShell で Google Cloud SDK をインストール中...")

        install_cmd = """powershell -NoProfile -Command "Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope CurrentUser -Force; iwr -useb get.scoop.sh | iex; scoop bucket add extras; scoop install gcloud" """

        try:
            result = subprocess.run(
                install_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            print(result.stdout)
            print(result.stderr)

            # インストール確認
            time.sleep(2)
            gcloud_path = find_gcloud()
            if os.path.exists(gcloud_path) or os.path.exists(gcloud_path + ".cmd"):
                print("[OK] Google Cloud SDK インストール完了")
                return True
        except Exception as e:
            print(f"[WARNING] PowerShell インストール失敗: {e}")

        print("[WARNING] PowerShell インストール失敗。別の方法を試します...")

        # 代替方法: choco
        if run_cmd("choco install google-cloud-sdk -y", "Chocolatey でインストール", check=False):
            print("[OK] Google Cloud SDK インストール完了")
            return True
        else:
            print("[ERROR] インストール失敗。手動でインストールしてください。")
            print("https://cloud.google.com/sdk/docs/install")
            return False
    else:
        # Linux/Mac
        print("Linux/Mac で Google Cloud SDK をインストール中...")
        if run_cmd("curl https://sdk.cloud.google.com | bash", "gcloud インストール", check=False):
            print("[OK] Google Cloud SDK インストール完了")
            return True
        else:
            print("[ERROR] インストール失敗")
            return False

def setup_gcloud_auth():
    """Google Cloud認証"""
    print_step(2, "Google Cloud に認証")

    print("ブラウザが開きます。Google アカウントでログインしてください...")
    time.sleep(2)

    # gcloud auth loginを実行
    gcloud_path = find_gcloud()

    try:
        subprocess.run([gcloud_path, "auth", "login"], check=True, timeout=300)
        print("[OK] 認証完了")
        return True
    except Exception as e:
        print(f"[ERROR] 認証失敗: {e}")
        print("Google Cloud SDK をインストール後、PowerShell を再起動してください。")
        return False

def get_or_create_project():
    """Google Cloud プロジェクトを確認/作成"""
    print_step(3, "Google Cloud プロジェクトを設定")

    gcloud_path = find_gcloud()

    # 既存プロジェクトを確認
    try:
        result = subprocess.run(
            [gcloud_path, "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=10
        )
        project_id = result.stdout.strip()

        if project_id and project_id != "None" and project_id != "(unset)":
            print(f"[OK] 既存プロジェクト: {project_id}")
            return project_id
    except:
        pass

    # プロジェクト一覧を表示
    print("\n利用可能なプロジェクト:")
    try:
        result = subprocess.run(
            [gcloud_path, "projects", "list", "--format=value(project_id)"],
            capture_output=True,
            text=True,
            timeout=10
        )
        projects = result.stdout.strip().split('\n')
        for i, proj in enumerate(projects, 1):
            if proj:
                print(f"  {i}. {proj}")

        if projects and projects[0]:
            project_id = projects[0].strip()
            print(f"\n[使用するプロジェクト] {project_id}")
            subprocess.run(
                [gcloud_path, "config", "set", "project", project_id],
                capture_output=True,
                timeout=10
            )
            return project_id
    except:
        pass

    print("[ERROR] プロジェクトが見つかりません")
    return None

def enable_apis(project_id):
    """必要なGoogleCloud APIを有効化"""
    print_step(4, "Google Cloud API を有効化")

    apis = [
        "run.googleapis.com",
        "cloudbuild.googleapis.com",
        "artifactregistry.googleapis.com",
        "cloudscheduler.googleapis.com",
        "logging.googleapis.com",
    ]

    for api in apis:
        print(f"有効化中: {api}...")
        run_cmd(
            f"gcloud services enable {api} --quiet",
            f"{api} を有効化",
            check=False
        )

    print("[OK] API 有効化完了")

def build_and_deploy(project_id):
    """Docker イメージをビルド＆デプロイ"""
    print_step(5, "Docker イメージをビルド＆デプロイ")

    trade_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(trade_dir)

    # Artifact Registry リポジトリを作成
    print("Artifact Registry リポジトリを作成中...")
    run_cmd(
        "gcloud artifacts repositories create btc-trading-bot --repository-format=docker --location=us-central1 --quiet",
        "リポジトリ作成",
        check=False
    )

    # Docker を認証
    print("Docker を認証中...")
    run_cmd(
        "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet",
        "Docker 認証",
        check=False
    )

    # イメージをビルド
    print("Docker イメージをビルド中（3-5分待機）...")
    image_name = f"us-central1-docker.pkg.dev/{project_id}/btc-trading-bot/btc-bot"

    if not run_cmd(
        f"docker build -t {image_name} .",
        "Docker ビルド"
    ):
        print("[ERROR] Docker ビルド失敗")
        return False

    # イメージをプッシュ
    print("Google Cloud にアップロード中（2-5分待機）...")
    if not run_cmd(
        f"docker push {image_name}",
        "Docker プッシュ"
    ):
        print("[ERROR] Docker プッシュ失敗")
        return False

    print("[OK] ビルド＆デプロイ完了")
    return True

def deploy_to_cloud_run(project_id):
    """Cloud Run にデプロイ"""
    print_step(6, "Cloud Run にデプロイ")

    gcloud_path = find_gcloud()
    image_name = f"us-central1-docker.pkg.dev/{project_id}/btc-trading-bot/btc-bot"

    print("Cloud Run にデプロイ中...")
    if not run_cmd(
        f'gcloud run deploy btc-trading-bot --image={image_name} --region=us-central1 --memory=512Mi --timeout=300 --no-allow-unauthenticated --quiet',
        "Cloud Run デプロイ"
    ):
        print("[ERROR] Cloud Run デプロイ失敗")
        return False

    # Service URL を取得
    try:
        result = subprocess.run(
            [gcloud_path, "run", "services", "describe", "btc-trading-bot", "--region=us-central1", "--format=value(status.url)"],
            capture_output=True,
            text=True,
            timeout=10
        )
        service_url = result.stdout.strip()
        print(f"[OK] Service URL: {service_url}")
        return service_url
    except:
        print("[ERROR] Service URL を取得できません")
        return None

def setup_cloud_scheduler(project_id, service_url):
    """Cloud Scheduler で自動実行を設定"""
    print_step(7, "Cloud Scheduler で自動実行を設定")

    print("Cloud Scheduler ジョブを作成中...")

    # 既存ジョブを削除（存在する場合）
    run_cmd(
        "gcloud scheduler jobs delete btc-bot-hourly --location=us-central1 --quiet",
        "既存ジョブ削除",
        check=False
    )

    # 新しいジョブを作成
    if run_cmd(
        f'gcloud scheduler jobs create http btc-bot-hourly --schedule="0 * * * *" --uri="{service_url}" --http-method=POST --location=us-central1 --oidc-service-account-email=default@appspot.gserviceaccount.com --quiet',
        "Cloud Scheduler ジョブ作成"
    ):
        print("[OK] Cloud Scheduler 設定完了")
        return True
    else:
        print("[ERROR] Cloud Scheduler 設定失敗")
        return False

def main():
    print_header("BTC Short Trading Bot - One-Click Cloud Deployment")

    print("\nこのスクリプトは以下を自動的に行います:")
    print("  1. Google Cloud SDK のインストール")
    print("  2. Google Cloud への認証（ブラウザでログイン）")
    print("  3. Google Cloud プロジェクトの設定")
    print("  4. 必要な API の有効化")
    print("  5. Docker イメージのビルド（3-5分）")
    print("  6. Google Cloud へのアップロード（2-5分）")
    print("  7. Cloud Run へのデプロイ")
    print("  8. Cloud Scheduler で毎時実行を設定")

    print("\n開始中...\n")
    time.sleep(1)

    # ステップ 1: gcloud のインストール確認
    gcloud_found = False
    try:
        gcloud_path = find_gcloud()
        result = subprocess.run(
            [gcloud_path, "--version"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            gcloud_found = True
    except:
        pass

    if not gcloud_found:
        print("\nGoogle Cloud SDK をインストール中...\n")
        if not download_gcloud():
            print("\n[ERROR] Google Cloud SDK のインストールに失敗しました。")
            print("手動でインストール後、もう一度実行してください:")
            print("  https://cloud.google.com/sdk/docs/install")
            sys.exit(1)

        # インストール後、パスを更新して再度確認
        print("\nGoogle Cloud SDK をインストールしました。")
        print("環境パスを更新しています...\n")
        time.sleep(2)

    # ステップ 2: 認証
    if not setup_gcloud_auth():
        print("\n[ERROR] 認証に失敗しました")
        sys.exit(1)

    # ステップ 3: プロジェクト設定
    project_id = get_or_create_project()
    if not project_id:
        print("\n[ERROR] プロジェクトが見つかりません")
        sys.exit(1)

    # ステップ 4: API 有効化
    enable_apis(project_id)

    # ステップ 5: ビルド＆デプロイ
    if not build_and_deploy(project_id):
        sys.exit(1)

    # ステップ 6: Cloud Run デプロイ
    service_url = deploy_to_cloud_run(project_id)
    if not service_url:
        sys.exit(1)

    # ステップ 7: Cloud Scheduler 設定
    if not setup_cloud_scheduler(project_id, service_url):
        sys.exit(1)

    # 完了
    print_header("[OK] デプロイ完了！")

    print(f"""
【設定情報】
  プロジェクト: {project_id}
  サービス: btc-trading-bot
  リージョン: us-central1
  URL: {service_url}

【実行スケジュール】
  毎時00分に自動実行（例: 14:00, 15:00, 16:00...）

【PC から監視する場合】
  python cloud_monitor.py --stats

これであなたのボットは Google Cloud で 24/7 自動実行中です！🚀
PC を起動する必要はありません。

""")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nキャンセルされました")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
