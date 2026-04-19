# -*- coding: utf-8 -*-
"""
Fetch 2-year 4h data for top altcoins via Binance
"""
import ccxt, os, time, pandas as pd
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Top altcoins on Hyperliquid that are also on Binance
COINS = [
    "AR/USDT", "AIXBT/USDT", "ACE/USDT", "AAVE/USDT", "ADA/USDT",
    "AERO/USDT", "APE/USDT", "APEX/USDT", "APT/USDT", "ARB/USDT",
    "0G/USDT", "2Z/USDT", "DOGE/USDT", "SOL/USDT", "ETH/USDT",
    "LINK/USDT", "SUI/USDT", "HYPE/USDT", "WIF/USDT", "PEPE/USDT",
]

def fetch_binance(symbol, timeframe="4h", days=730):
    ex = ccxt.binance({"enableRateLimit": True})
    since_dt = datetime.utcnow() - timedelta(days=days)
    since = ex.parse8601(since_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))

    print(f"  Fetching {symbol} {timeframe} ({days}d)...")
    all_bars = []
    while True:
        try:
            bars = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"    Error: {e}")
            break
        if not bars:
            break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        if len(bars) < 1000:
            break
        time.sleep(0.15)

    if not all_bars:
        print(f"    No data for {symbol}")
        return None

    df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]]
    df = df.sort_index()

    safe_name = symbol.replace("/", "_").replace(":", "")
    filename = f"{safe_name}_4h_730d.csv"
    path = os.path.join(DATA_DIR, filename)
    df.to_csv(path)
    print(f"    Saved: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return path

if __name__ == "__main__":
    success = 0
    for coin in COINS:
        try:
            if fetch_binance(coin):
                success += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"  Failed {coin}: {e}")
    print(f"\nDone. {success}/{len(COINS)} coins fetched.")
