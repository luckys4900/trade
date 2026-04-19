import requests
from datetime import datetime
from typing import Dict, Optional

class WhaleAnalyzer:
    def __init__(self):
        self.coingecko_api = "https://api.coingecko.com/api/v3"

    def calculate_roi(self, whale: Dict) -> Dict:
        try:
            address = whale["address"]
            current_balance_btc = whale["balance_btc"]
            first_seen_ts = whale["first_seen_ts"]
            
            current_price = self.get_btc_price_current()
            if current_price is None:
                return {"error": "Failed to fetch current BTC price"}
            
            inflow_date = datetime.fromtimestamp(first_seen_ts).strftime("%Y-%m-%d")
            inflow_price = self.get_btc_price_at_date(inflow_date)
            
            if inflow_price is None or inflow_price <= 0:
                return {"error": f"Failed to fetch BTC price at {inflow_date}"}
            
            inflow_value = current_balance_btc * inflow_price
            current_value = current_balance_btc * current_price
            
            holding_days = (datetime.now() - datetime.fromtimestamp(first_seen_ts)).days
            roi_pct = ((current_value - inflow_value) / inflow_value * 100) if inflow_value > 0 else 0
            annualized_roi = roi_pct / (holding_days / 365.0) if holding_days > 0 else 0
            
            return {
                "address": address,
                "inflow_date": inflow_date,
                "inflow_price_usd": inflow_price,
                "inflow_value_usd": inflow_value,
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "current_price_usd": current_price,
                "current_value_usd": current_value,
                "balance_btc": current_balance_btc,
                "roi_pct": roi_pct,
                "holding_days": holding_days,
                "annualized_roi_pct": annualized_roi
            }
        except Exception as e:
            return {"error": str(e)}

    def get_btc_price_current(self) -> Optional[float]:
        try:
            url = f"{self.coingecko_api}/simple/price"
            params = {"ids": "bitcoin", "vs_currencies": "usd"}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return float(resp.json()["bitcoin"]["usd"])
        except:
            return None

    def get_btc_price_at_date(self, date_str: str) -> Optional[float]:
        try:
            url = f"{self.coingecko_api}/coins/bitcoin/history"
            params = {"date": date_str, "localization": "false"}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            price = data.get("market_data", {}).get("current_price", {}).get("usd")
            return float(price) if price else None
        except:
            return None
