# -*- coding: utf-8 -*-
"""
Hyperliquid Altcoin Data Fetcher
Fetch OHLCV for all active perpetual markets on Hyperliquid
"""
import ccxt, os, json, time, pandas as pd
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def get_hl_markets():
    """Get all active perpetual markets on Hyperliquid"""
    ex = ccxt.hyperliquid()
    markets = ex.load_markets()
    perps = []
    for sym, info in markets.items():
        if info.get("swap", False) and info.get("active", False):
            base = info.get("baseId", info.get("base", ""))
            perps.append({
                "symbol": sym,
                "base": base,
                "active": True,
            })
    return sorted(perps, key=lambda x: x["symbol"])


def fetch_ohlcv(symbol, timeframe="4h", days=365, output_dir=None):
    """Fetch OHLCV data from Hyperliquid and save to CSV"""
    if output_dir is None:
        output_dir = DATA_DIR

    ex = ccxt.hyperliquid({"enableRateLimit": True, "rateLimit": 2000})
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
        time.sleep(0.1)

    if not all_bars:
        print(f"    No data for {symbol}")
        return None

    df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]]
    df = df.sort_index()

    # Save
    safe_name = symbol.replace("/", "_").replace(":", "")
    filename = f"{safe_name}_{timeframe}_{days}d.csv"
    path = os.path.join(output_dir, filename)
    df.to_csv(path)
    print(f"    Saved {path}: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return path


def fetch_top_coins(top_n=20, timeframe="4h", days=365):
    """Fetch OHLCV for top N coins by volume"""
    markets = get_hl_markets()
    print(f"Found {len(markets)} active perpetual markets")

    # Filter: exclude BTC (already have), exclude stablecoins
    exclude = {"BTC", "USDC", "USDT", "USD"}
    coins = [m for m in markets if m["base"] not in exclude]

    # Take top N
    targets = coins[:top_n]
    print(f"Fetching top {len(targets)} coins: {[c['symbol'] for c in targets]}")

    results = []
    for m in targets:
        try:
            path = fetch_ohlcv(m["symbol"], timeframe, days)
            if path:
                results.append({"symbol": m["symbol"], "path": path})
            time.sleep(3)
        except Exception as e:
            print(f"  Failed {m['symbol']}: {e}")

    # Save manifest
    manifest = os.path.join(DATA_DIR, "altcoin_manifest.json")
    with open(manifest, "w") as f:
        json.dump({"coins": results, "timeframe": timeframe, "days": days, "updated": str(datetime.utcnow())}, f, indent=2)
    print(f"\nManifest saved: {manifest}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["list", "fetch", "single"], default="fetch")
    parser.add_argument("--symbol", default="ETH/USDT:USDT")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--tf", default="4h")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    if args.mode == "list":
        markets = get_hl_markets()
        for m in markets:
            print(f"  {m['symbol']}")
        print(f"\nTotal: {len(markets)} active perps")

    elif args.mode == "fetch":
        fetch_top_coins(args.top, args.tf, args.days)

    elif args.mode == "single":
        fetch_ohlcv(args.symbol, args.tf, args.days)
