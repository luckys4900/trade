#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Cloud Run への自動デプロイスクリプト
このスクリプトを実行すると、ボットが自動的にクラウドにアップロードされます
"""

import subprocess
import os
import sys
import json
import io
from pathlib import Path

# Windows Unicode 対応
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class CloudDeployer:
    """Google Cloud Run へのデプロイメント"""

    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.project_id = None
        self.service_name = "btc-trading-bot"
        self.region = "us-central1"
        self.image_name = f"{self.region}-docker.pkg.dev"

    def run_command(self, cmd: list, description: str) -> bool:
        """コマンド実行"""
        print(f"\n[{description}]")
        print(f"Command: {' '.join(cmd)}")
        print("-" * 80)

        try:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            if result.stdout:
                print(result.stdout)
            return True
        except subprocess.CalledProcessError as e:
            print(f"ERROR: {e}")
            if e.stderr:
                print(f"Details: {e.stderr}")
            return False

    def check_requirements(self) -> bool:
        """前提条件を確認"""
        print("\n" + "=" * 80)
        print("CHECKING REQUIREMENTS")
        print("=" * 80)

        # gcloud チェック
        print("\n[1/4] Checking gcloud...")
        result = subprocess.run(["gcloud", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("[OK] gcloud is installed")
        else:
            print("✗ gcloud not installed. Please install Google Cloud SDK")
            print("  https://cloud.google.com/sdk/docs/install")
            return False

        # Docker チェック
        print("\n[2/4] Checking Docker...")
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("[OK] Docker is installed")
        else:
            print("✗ Docker not installed. Please install Docker")
            print("  https://www.docker.com/products/docker-desktop")
            return False

        # gcloud 認証チェック
        print("\n[3/4] Checking gcloud authentication...")
        result = subprocess.run(["gcloud", "auth", "list"], capture_output=True, text=True)
        if "active account:" in result.stdout.lower():
            print("[OK] gcloud is authenticated")
        else:
            print("✗ gcloud not authenticated")
            print("  Run: gcloud auth login")
            return False

        # プロジェクトIDを取得
        print("\n[4/4] Getting Google Cloud project...")
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            self.project_id = result.stdout.strip()
            if self.project_id:
                print(f"[OK] Project: {self.project_id}")
            else:
                print("✗ No project configured")
                print("  Run: gcloud config set project YOUR_PROJECT_ID")
                return False
        else:
            print("✗ Could not get project")
            return False

        return True

    def enable_apis(self) -> bool:
        """必要なAPI を有効化"""
        print("\n" + "=" * 80)
        print("ENABLING GOOGLE CLOUD APIS")
        print("=" * 80)

        apis = [
            ("logging.googleapis.com", "Cloud Logging"),
            ("run.googleapis.com", "Cloud Run"),
            ("cloudbuild.googleapis.com", "Cloud Build"),
            ("cloudscheduler.googleapis.com", "Cloud Scheduler"),
            ("artifactregistry.googleapis.com", "Artifact Registry"),
        ]

        for api, name in apis:
            print(f"\nEnabling {name}...")
            if not self.run_command(
                ["gcloud", "services", "enable", api],
                f"Enabling {name}"
            ):
                print(f"Warning: Could not enable {name}")

        return True

    def build_docker_image(self) -> bool:
        """Docker イメージをビルド"""
        print("\n" + "=" * 80)
        print("BUILDING DOCKER IMAGE")
        print("=" * 80)

        return self.run_command(
            ["docker", "build", "-t", f"{self.service_name}:latest", str(self.script_dir)],
            "Building Docker image"
        )

    def push_to_artifact_registry(self) -> bool:
        """Docker イメージをArtifact Registry にプッシュ"""
        print("\n" + "=" * 80)
        print("PUSHING TO ARTIFACT REGISTRY")
        print("=" * 80)

        # Artifact Registry にログイン
        print("\n[Step 1/2] Authenticating Docker...")
        if not self.run_command(
            ["gcloud", "auth", "configure-docker", f"{self.region}-docker.pkg.dev"],
            "Configuring Docker authentication"
        ):
            return False

        # イメージをタグ付け
        registry_image = f"{self.region}-docker.pkg.dev/{self.project_id}/{self.service_name}/{self.service_name}:latest"
        print(f"\n[Step 2/2] Tagging and pushing image...")
        print(f"Image: {registry_image}")

        if not self.run_command(
            ["docker", "tag", f"{self.service_name}:latest", registry_image],
            "Tagging Docker image"
        ):
            return False

        return self.run_command(
            ["docker", "push", registry_image],
            "Pushing to Artifact Registry"
        )

    def deploy_to_cloud_run(self) -> bool:
        """Cloud Run にデプロイ"""
        print("\n" + "=" * 80)
        print("DEPLOYING TO CLOUD RUN")
        print("=" * 80)

        registry_image = f"{self.region}-docker.pkg.dev/{self.project_id}/{self.service_name}/{self.service_name}:latest"

        return self.run_command(
            [
                "gcloud", "run", "deploy", self.service_name,
                f"--image={registry_image}",
                f"--region={self.region}",
                "--memory=512Mi",
                "--timeout=300",
                "--no-allow-unauthenticated"
            ],
            "Deploying to Cloud Run"
        )

    def setup_cloud_scheduler(self) -> bool:
        """Cloud Scheduler で自動実行を設定"""
        print("\n" + "=" * 80)
        print("SETTING UP CLOUD SCHEDULER")
        print("=" * 80)

        # Cloud Run URL を取得
        print("\nGetting Cloud Run service URL...")
        result = subprocess.run(
            [
                "gcloud", "run", "services", "describe", self.service_name,
                f"--region={self.region}",
                "--format=value(status.url)"
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("Could not get Cloud Run URL")
            return False

        service_url = result.stdout.strip()
        print(f"Service URL: {service_url}")

        # スケジューラジョブを作成
        job_name = f"{self.service_name}-hourly"

        # 既存ジョブを削除（存在する場合）
        print(f"\nChecking for existing scheduler job '{job_name}'...")
        subprocess.run(
            ["gcloud", "scheduler", "jobs", "delete", job_name, f"--location={self.region}", "--quiet"],
            capture_output=True
        )

        # 新規ジョブを作成
        return self.run_command(
            [
                "gcloud", "scheduler", "jobs", "create", "http", job_name,
                f"--location={self.region}",
                "--schedule=0 * * * *",  # 毎時間00分に実行
                f"--uri={service_url}",
                "--http-method=POST",
                "--oidc-service-account-email=default@appspot.gserviceaccount.com"
            ],
            "Creating Cloud Scheduler job"
        )

    def deploy(self) -> bool:
        """完全なデプロイメント"""
        print("\n" + "=" * 80)
        print("GOOGLE CLOUD DEPLOYMENT WIZARD")
        print("=" * 80)

        # 前提条件チェック
        if not self.check_requirements():
            print("\n[ERROR] Requirements not met. Please fix the issues above.")
            return False

        # デプロイステップ
        steps = [
            ("Enable APIs", self.enable_apis),
            ("Build Docker Image", self.build_docker_image),
            ("Push to Artifact Registry", self.push_to_artifact_registry),
            ("Deploy to Cloud Run", self.deploy_to_cloud_run),
            ("Setup Cloud Scheduler", self.setup_cloud_scheduler),
        ]

        for step_name, step_func in steps:
            print(f"\n>>> {step_name}...")
            if not step_func():
                print(f"[ERROR] {step_name} failed")
                return False
            print(f"[OK] {step_name} completed")

        return True

    def show_success_message(self):
        """成功メッセージを表示"""
        print("\n" + "=" * 80)
        print("DEPLOYMENT SUCCESSFUL!")
        print("=" * 80)

        print(f"""
Your BTC Short Trading Bot is now running on Google Cloud Run!

Service Details:
  Project: {self.project_id}
  Service: {self.service_name}
  Region: {self.region}

Scheduler:
  Job Name: {self.service_name}-hourly
  Schedule: Every hour (0 * * * *)

Monitor your bot:
  Run: python cloud_monitor.py --stats
  Or: gcloud logging read "resource.type=cloud_run_revision" --limit=50

What happens next:
  1. Cloud Scheduler will trigger the bot every hour at :00
  2. Cloud Run executes short_trading_bot_cloud.py
  3. Logs are stored in Cloud Logging
  4. No PC needed - 24/7 automatic execution!

To stop the bot:
  gcloud scheduler jobs pause {self.service_name}-hourly --location={self.region}

To delete everything:
  gcloud run services delete {self.service_name} --region={self.region}
  gcloud scheduler jobs delete {self.service_name}-hourly --location={self.region}
""")


def main():
    deployer = CloudDeployer()

    try:
        if deployer.deploy():
            deployer.show_success_message()
            return 0
        else:
            print("\n[ERROR] Deployment failed")
            return 1
    except KeyboardInterrupt:
        print("\n\nDeployment cancelled")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
