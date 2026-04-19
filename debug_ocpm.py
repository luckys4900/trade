import ccxt, pandas as pd, numpy as np
from datetime import datetime, timedelta

ex = ccxt.binance({"enableRateLimit": True})
since = ex.parse8601((datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))
rows = []
while True:
    b = ex.fetch_ohlcv("BTC/USDT", "4h", since=since, limit=1000)
    if not b: break
    rows.extend(b)
    since = b[-1][0] + 1
    if len(b) < 1000: break

df = pd.DataFrame(rows, columns=["ts","o","h","l","c","v"])
df["datetime"] = pd.to_datetime(df["ts"], unit="ms")
df = df.sort_values("datetime").reset_index(drop=True)

df["ema_f"] = df["c"].ewm(span=21, adjust=False).mean()
df["ema_s"] = df["c"].ewm(span=55, adjust=False).mean()
df["slope"] = df["ema_f"].pct_change(10)
df["donchian_h"] = df["h"].rolling(20).max()
df["donchian_l"] = df["l"].rolling(20).min()
df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2

delta = df["c"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
df["rsi"] = 100 - 100/(1+gain/loss.replace(0, np.nan))
df["rsi_prev"] = df["rsi"].shift(1)

print("Last 5 bars analysis:")
for i in range(max(0, len(df)-5), len(df)):
    r = df.iloc[i]
    trend_cond = (r["c"]<r["ema_s"]) and (r["ema_f"]<r["ema_s"]) and (r["slope"]<0)
    dc_cond = r["c"] < r["donchian_mid"]
    rsi_cond = (r["rsi_prev"] >= 52.0) and (r["rsi"] < r["rsi_prev"]) and (r["rsi"] > 45)
    short = trend_cond and dc_cond and rsi_cond
    print(f"  {r['datetime']} | C={r['c']:,.0f} | DC_mid={r['donchian_mid']:,.0f} | trend={trend_cond} | dc={dc_cond} | rsi={r['rsi']:.1f} | rsi_prev={r['rsi_prev']:.1f} | rsi_ok={rsi_cond} | SHORT={short}")
