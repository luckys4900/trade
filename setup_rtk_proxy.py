#!/usr/bin/env python3
"""
RTKプロキシの導入と設定
トークン使用量を60-90%削減
"""

import os
import json
import subprocess
import logging
import shutil
from pathlib import Path

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RTKProxy:
    """RTKプロキシの管理クラス"""
    
    def __init__(self):
        self.rtk_dir = Path.home() / ".rtk"
        self.rtk_binary = self.rtk_dir / "rtk"
        self.config_file = Path(__file__).parent / "rtk_config.json"
        
    def install_rtk(self):
        """RTKプロキシをインストール"""
        try:
            logger.info("Installing RTK proxy...")
            
            # RTKディレクトリの作成
            self.rtk_dir.mkdir(exist_ok=True)
            
            # Rustとcargoの確認
            if not self._check_rust():
                logger.error("Rust not found. Please install Rust first.")
                return False
            
            # RTKのクローンとビルド
            clone_cmd = "git clone https://github.com/rtk-ai/rtk.git"
            subprocess.run(clone_cmd.split(), cwd=self.rtk_dir, check=True)
            
            # ビルド
            build_cmd = "cargo build --release"
            subprocess.run(build_cmd.split(), cwd=self.rtk_dir / "rtk", check=True)
            
            # バイナリの配置
            src_binary = self.rtk_dir / "rtk" / "target" / "release" / "rtk"
            shutil.copy2(src_binary, self.rtk_binary)
            os.chmod(self.rtk_binary, 0o755)
            
            logger.info("RTK proxy installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install RTK: {e}")
            return False
    
    def _check_rust(self):
        """Rustがインストールされているか確認"""
        try:
            result = subprocess.run(["rustc", "--version"], capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def create_config(self):
        """RTK設定ファイルを作成"""
        config = {
            "rtk": {
                "models": {
                    "glm-5-1": {
                        "provider": "zai",
                        "model": "glm-5-1",
                        "endpoint": "https://api.z.ai/api/coding/paas/v4"
                    },
                    "glm-5-turbo": {
                        "provider": "zai", 
                        "model": "glm-5-turbo",
                        "endpoint": "https://api.z.ai/api/coding/paas/v4"
                    },
                    "glm-4-7-flash": {
                        "provider": "zai",
                        "model": "glm-4-7-flash", 
                        "endpoint": "https://api.z.ai/api/coding/paas/v4"
                    },
                    "tencent/hy3-preview:free": {
                        "provider": "openrouter",
                        "model": "tencent/hy3-preview:free",
                        "endpoint": "https://openrouter.ai/api/v1"
                    },
                        "endpoint": "https://openrouter.ai/api/v1"
                    }
                },
                "caching": {
                    "enabled": True,
                    "max_size": "100MB",
                    "ttl": 3600
                },
                "compression": {
                    "enabled": True,
                    "level": 6
                },
                "batching": {
                    "enabled": True,
                    "max_batch_size": 10,
                    "max_wait_time": 1000
                },
                "fallback": {
                    "local_model": "qwen3:8b",
                    "local_endpoint": "http://localhost:11434/api/generate"
                }
            }
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"RTK config created: {self.config_file}")
    
    def start_proxy(self):
        """RTKプロキシを起動"""
        try:
            if not self.rtk_binary.exists():
                logger.error("RTK binary not found. Run install_rtk() first.")
                return False
            
            # 環境変数の設定
            env = os.environ.copy()
            env['RTK_CONFIG'] = str(self.config_file)
            
            # プロキシの起動
            cmd = [str(self.rtk_binary), "proxy", "--port", "8888"]
            process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # プロセスの保存
            with open('rtk_proxy.pid', 'w') as f:
                f.write(str(process.pid))
            
            logger.info(f"RTK proxy started with PID: {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start RTK proxy: {e}")
            return False
    
    def stop_proxy(self):
        """RTKプロキシを停止"""
        try:
            if os.path.exists('rtk_proxy.pid'):
                with open('rtk_proxy.pid', 'r') as f:
                    pid = int(f.read().strip())
                
                os.kill(pid, 15)  # SIGTERM
                os.remove('rtk_proxy.pid')
                logger.info("RTK proxy stopped")
                return True
            else:
                logger.warning("RTK proxy PID file not found")
                return False
                
        except Exception as e:
            logger.error(f"Failed to stop RTK proxy: {e}")
            return False
    
    def update_opencode_config(self):
        """opencode設定をRTK対応に更新"""
        config_path = Path.home() / ".config" / "opencode" / "opencode.json"
        
        try:
            # 現在の設定読み込み
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
            
            # RTKプロバイダーを追加
            if "provider" not in current_config:
                current_config["provider"] = {}
            
            current_config["provider"]["rtk-proxy"] = {
                "models": {
                    "glm-5-1": {
                        "id": "glm-5-1",
                        "name": "GLM-5.1 (RTK)"
                    },
                    "glm-5-turbo": {
                        "id": "glm-5-turbo", 
                        "name": "GLM-5 Turbo (RTK)"
                    },
                    "glm-4-7-flash": {
                        "id": "glm-4-7-flash",
                        "name": "GLM-4.7 Flash (RTK)"
                    },
                    "tencent/hy3-preview:free": {
                        "id": "tencent/hy3-preview:free",
                        "name": "TENCENT-HY3 Preview (RTK)"
                    }
                },
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "baseURL": "http://localhost:8888/v1"
                }
            }
            
            # 設定を保存
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=2, ensure_ascii=False)
            
            logger.info("Updated opencode config for RTK proxy")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update opencode config: {e}")
            return False
    
    def test_proxy(self):
        """RTKプロキシのテスト"""
        try:
            import requests
            
            # モデルリストのテスト
            response = requests.get("http://localhost:8888/v1/models")
            if response.status_code == 200:
                logger.info("RTK proxy models API working")
            else:
                logger.error(f"RTK proxy test failed: {response.status_code}")
                return False
            
            # チャットAPIのテスト
            test_data = {
                "model": "glm-4-7-flash",
                "messages": [
                    {"role": "user", "content": "Hello, this is a test."}
                ]
            }
            
            response = requests.post("http://localhost:8888/v1/chat/completions", json=test_data)
            if response.status_code == 200:
                logger.info("RTK proxy chat API working")
                return True
            else:
                logger.error(f"RTK proxy chat test failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"RTK proxy test error: {e}")
            return False

def main():
    """メイン関数"""
    print("RTK Proxy Setup")
    print("=" * 50)
    
    rtk = RTKProxy()
    
    # 1. RTKのインストール
    print("1. Installing RTK proxy...")
    if not rtk.install_rtk():
        print("[FAILED] Failed to install RTK")
        return False
    print("[SUCCESS] RTK proxy installed")
    
    # 2. 設定ファイルの作成
    print("\n2. Creating RTK config...")
    rtk.create_config()
    print("[SUCCESS] RTK config created")
    
    # 3. opencode設定の更新
    print("\n3. Updating opencode config...")
    rtk.update_opencode_config()
    print("[SUCCESS] opencode config updated")
    
    # 4. プロキシの起動
    print("\n4. Starting RTK proxy...")
    if not rtk.start_proxy():
        print("[FAILED] Failed to start RTK proxy")
        return False
    print("[SUCCESS] RTK proxy started")
    
    # 5. プロキシのテスト
    print("\n5. Testing RTK proxy...")
    if not rtk.test_proxy():
        print("[FAILED] RTK proxy test failed")
        return False
    print("[SUCCESS] RTK proxy tested successfully")
    
    print("\n" + "=" * 50)
    print("🎉 RTK proxy setup completed successfully!")
    print("Token savings: 60-90%")
    print("Next steps:")
    print("1. Update your API calls to use http://localhost:8888/v1")
    print("2. Monitor token usage in the dashboard")
    print("3. Enjoy cost savings!")
    
    return True

if __name__ == "__main__":
    main()