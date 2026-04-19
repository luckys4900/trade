import os, sys, numpy as np, pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def compute_rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100/(1+rs)

def compute_atr(df, period):
    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

def load_csv(path):
    if not os.path.exists(path): return None
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ('open','o'): col_map[c] = 'open'
        elif cl in ('high','h'): col_map[c] = 'high'
        elif cl in ('low','l'): col_map[c] = 'low'
        elif cl in ('close','c'): col_map[c] = 'close'
        elif cl in ('volume','v'): col_map[c] = 'volume'
    df = df.rename(columns=col_map)
    df = df[['open','high','low','close','volume']].astype(float).sort_index()
    return df

def main():
    print("Loading 4h data...")
    df = load_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_usdt_4h_unified.csv"))
    print(f"  {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")

    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["donchian_h"] = df["high"].rolling(20).max()
    df["donchian_l"] = df["low"].rolling(20).min()
    df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2
    df["rsi"] = compute_rsi(df["close"], 14)
    df["rsi_prev"] = df["rsi"].shift(1)
    df["atr"] = compute_atr(df, 14)

    df["long"] = ((df["close"]>df["ema55"])&(df["close"]>df["donchian_mid"])&(df["rsi_prev"]<=48)&(df["rsi"]>df["rsi_prev"])&(df["rsi"]<55)).astype(int)
    df["short"] = ((df["close"]<df["ema55"])&(df["close"]<df["donchian_mid"])&(df["rsi_prev"]>=52)&(df["rsi"]<df["rsi_prev"])&(df["rsi"]>45)).astype(int)

    signals = df[(df["long"]==1) | (df["short"]==1)].copy()
    signals["side"] = "LONG"
    signals.loc[signals["short"]==1, "side"] = "SHORT"
    signals["hour"] = signals.index.hour
    signals["dayofweek"] = signals.index.dayofweek
    signals["dayname"] = signals.index.day_name()

    print(f"\n  Total signals: {len(signals)} (LONG={int(signals['long'].sum())}, SHORT={int(signals['short'].sum())})")

    # === Hour analysis (JST = UTC+9) ===
    print(f"\n{'='*60}")
    print(f"  ENTRY SIGNALS BY HOUR (JST = UTC+9)")
    print(f"{'='*60}")
    signals["hour_jst"] = (signals.index.hour + 9) % 24
    hour_counts = signals.groupby("hour_jst").size()

    print(f"  {'Hour (JST)':<12} {'Count':>6} {'LONG':>5} {'SHORT':>5} {'% of Total':>10}")
    print(f"  {'-'*45}")
    for h in range(24):
        cnt = hour_counts.get(h, 0)
        if cnt > 0:
            longs = int(signals[signals["hour_jst"]==h]["long"].sum())
            shorts = int(signals[signals["hour_jst"]==h]["short"].sum())
            pct = cnt / len(signals) * 100
            marker = " ***" if cnt >= 5 else ""
            print(f"  {h:02d}:00        {cnt:>6} {longs:>5} {shorts:>5} {pct:>9.1f}%{marker}")

    top_hours = hour_counts.nlargest(3)
    print(f"\n  Top 3 hours (JST):")
    for h, cnt in top_hours.items():
        print(f"    {int(h):02d}:00 - {cnt} signals ({cnt/len(signals)*100:.0f}%)")

    # === Day of week analysis ===
    print(f"\n{'='*60}")
    print(f"  ENTRY SIGNALS BY DAY OF WEEK")
    print(f"{'='*60}")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_counts = signals.groupby("dayname").size()

    print(f"  {'Day':<12} {'Count':>6} {'LONG':>5} {'SHORT':>5} {'% of Total':>10}")
    print(f"  {'-'*45}")
    for day in day_order:
        cnt = day_counts.get(day, 0)
        if cnt > 0:
            longs = int(signals[signals["dayname"]==day]["long"].sum())
            shorts = int(signals[signals["dayname"]==day]["short"].sum())
            pct = cnt / len(signals) * 100
            marker = " ***" if cnt >= 8 else ""
            print(f"  {day:<12} {cnt:>6} {longs:>5} {shorts:>5} {pct:>9.1f}%{marker}")

    top_days = day_counts.nlargest(3)
    print(f"\n  Top 3 days:")
    for day, cnt in top_days.items():
        print(f"    {day} - {cnt} signals ({cnt/len(signals)*100:.0f}%)")

    # === All signal timestamps ===
    print(f"\n{'='*60}")
    print(f"  ALL SIGNAL TIMESTAMPS (UTC -> JST)")
    print(f"{'='*60}")
    print(f"  {'UTC Time':<20} {'JST Time':<20} {'Day':<12} {'Side':<6} {'Price':>12} {'RSI':>6}")
    print(f"  {'-'*80}")
    for _, s in signals.iterrows():
        jst = s.name + pd.Timedelta(hours=9)
        print(f"  {str(s.name):<20} {str(jst):<20} {s['dayname']:<12} {s['side']:<6} ${s['close']:>11,.0f} {s['rsi']:>5.1f}")

    # === Hour x Day heatmap ===
    print(f"\n{'='*60}")
    print(f"  SIGNAL HEATMAP (Day x Hour JST)")
    print(f"{'='*60}")
    heatmap = pd.crosstab(signals["dayname"], signals["hour_jst"])
    heatmap = heatmap.reindex([d for d in day_order if d in heatmap.index])
    print(f"  {'Day':<12} " + " ".join([f"{h:02d}" for h in range(24)]))
    print(f"  {'-'*65}")
    for day in day_order:
        if day in heatmap.index:
            row = heatmap.loc[day]
            cells = []
            for h in range(24):
                v = row.get(h, 0)
                if v >= 3: cells.append(f" {v:02d}")
                elif v > 0: cells.append(f"  {v}")
                else: cells.append("  .")
            print(f"  {day:<12} {''.join(cells)}")

if __name__ == "__main__":
    main()
