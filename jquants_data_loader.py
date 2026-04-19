import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
import jquantsapi

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class JQuantsDataLoader:
    """
    J-Quants APIから日本株データを取得するクラス
    """
    def __init__(self, mail_address: Optional[str] = None, password: Optional[str] = None):
        self.mail_address = mail_address or os.getenv("JQUANTS_MAIL_ADDRESS")
        self.password = password or os.getenv("JQUANTS_PASSWORD")
        self.cli = None
        
        if self.mail_address and self.password:
            try:
                self.cli = jquantsapi.Client(mail_address=self.mail_address, password=self.password)
                logging.info("J-Quants API client initialized.")
            except Exception as e:
                logging.error(f"Failed to initialize J-Quants client: {e}")
        else:
            logging.warning("J-Quants credentials not found. Using synthetic data or cached files only.")

    def get_stock_list(self) -> pd.DataFrame:
        """
        全上場銘柄リストを取得
        """
        if not self.cli:
            return pd.DataFrame()
        return self.cli.get_list()

    def get_daily_quotes(self, code: str, start: str, end: str) -> pd.DataFrame:
        """
        日足株価を取得
        """
        if not self.cli:
            logging.warning("No API client. Fetching synthetic daily data.")
            return self._synth_daily(code, start, end)
        
        try:
            df = self.cli.get_prices_daily_quotes(code=code, from_date=start, to_date=end)
            if df.empty:
                return df
            
            # カラム名をバックテスト用に変換
            df = df.rename(columns={
                "Date": "Date",
                "Open": "Open",
                "High": "High",
                "Low": "Low",
                "Close": "Close",
                "Volume": "Volume"
            })
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date').sort_index()
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logging.error(f"Error fetching J-Quants data: {e}")
            return self._synth_daily(code, start, end)

    def _synth_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        """合成日本株データ"""
        s_dt = pd.to_datetime(start)
        e_dt = pd.to_datetime(end)
        days = (e_dt - s_dt).days
        ts = pd.date_range(s_dt, periods=days, freq="D")
        # 土日を除外
        ts = ts[ts.dayofweek < 5]
        n = len(ts)
        
        np.random.seed(42)
        base = 2000.0  # 日本株の平均的な価格帯
        cl = base * np.exp(np.cumsum(np.random.normal(0.0001, 0.015, n)))
        op = cl * (1 + np.random.normal(0, 0.005, n))
        hi = np.maximum(op, cl) * (1 + np.abs(np.random.normal(0, 0.01, n)))
        lo = np.minimum(op, cl) * (1 - np.abs(np.random.normal(0, 0.01, n)))
        vol = np.random.lognormal(14, 1, n)
        
        return pd.DataFrame(
            {"Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": vol},
            index=ts,
        )

if __name__ == "__main__":
    # テスト実行
    loader = JQuantsDataLoader()
    # トヨタ(7203)のデータを想定
    df = loader.get_daily_quotes("7203", "2024-01-01", "2024-03-30")
    print(df.head())
    print(f"Data length: {len(df)}")
