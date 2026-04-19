import requests
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path


class BlockchairScraper:
    def __init__(self):
        self.base_url = "https://blockchair.com/api/v1/bitcoin"
        self.rate_limit_delay = 0.2  # 5 req/sec
        self.backup_dir = Path("data/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def fetch_top_whales(
        self,
        min_btc: float = 100,
        limit: int = 50,
        max_retries: int = 3
    ) -> Optional[List[Dict]]:
        """大口ウォレット取得（リトライ＋フォールバック付き）"""

        for attempt in range(max_retries):
            try:
                return self._fetch_with_retry(min_btc, limit)
            except Exception as e:
                print(f"[Attempt {attempt+1}/{max_retries}] Error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff
                else:
                    print("[Fallback] Loading backup data...")
                    return self._load_backup_data()

    def _fetch_with_retry(self, min_btc: float, limit: int) -> List[Dict]:
        """Blockchair APIから取得"""
        response = self._request_blockchair(limit, min_btc)
        whales = []

        if "data" in response and isinstance(response["data"], list):
            for addr_info in response["data"]:
                balance_btc = addr_info.get("balance", 0) / 1e8
                if balance_btc >= min_btc:
                    whales.append({
                        "address": addr_info.get("address"),
                        "balance_btc": balance_btc,
                        "first_seen_ts": addr_info.get("first_seen_receiving"),
                        "tx_count": addr_info.get("transaction_count", 0),
                        "fetched_at": datetime.now().isoformat()
                    })

        # Backup保存
        self._save_backup(whales)
        return whales

    def _request_blockchair(self, limit: int, min_btc: float) -> Dict:
        """Blockchair API呼び出し"""
        url = f"{self.base_url}/addresses"
        params = {
            "limit": limit,
            "offset": 0,
            "sort": "balance(desc)"
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def _load_backup_data(self) -> Optional[List[Dict]]:
        """最新のバックアップを読み込む"""
        backup_files = sorted(self.backup_dir.glob("whales_backup_*.json"), reverse=True)
        if backup_files:
            with open(backup_files[0], "r") as f:
                return json.load(f)
        return []

    def _save_backup(self, whales: List[Dict]) -> None:
        """バックアップ保存"""
        backup_file = self.backup_dir / f"whales_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(whales, f, ensure_ascii=False, indent=2)

        # 最新7日分のみ保持
        for old_backup in sorted(self.backup_dir.glob("*.json"), reverse=True)[7:]:
            old_backup.unlink()
