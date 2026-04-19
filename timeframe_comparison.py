import os, sys, numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

@dataclass
class Trade:
    t_in: str; t_out: str; side: str; strat: str
    p_in: float; p_out: float; sz: float
    pnl: float; pnl_pct: float; reason: str; bars: int = 0

INITIAL_CASH = 100.0
COMM_PCT = 0.0005
RISK_PCT = 0.015
MAX_POS_PCT = 0.40
DD_HALT = 0.15

def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG": return (exit_px-entry)*sz - notional*comm
    else: return (entry-exit_px)*sz - notional*comm

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

def run_backtest(df, long_col, short_col, sl_mult, tp_mult, max_hold, label):
    cash = INITIAL_CASH; peak_eq = INITIAL_CASH; eq = []; trades = []; cm = COMM_PCT
    in_pos = False; side = ""; entry = 0; bar_in = 0; sz = 0; stop = 0
    loss_count = 0; cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]; px = r["close"]; atr = r.get("atr", 0)
        pv = sz * px if in_pos else 0; equity = cash + pv
        peak_eq = max(peak_eq, equity); dd = (peak_eq-equity)/peak_eq if peak_eq > 0 else 0
        eq.append(equity)
        if dd >= DD_HALT:
            if in_pos:
                pnl = _pnl(side, entry, px, sz, cm); cash += sz*entry + pnl
                trades.append(Trade("","",side,label,entry,px,sz,pnl,0,"DD_HALT",i-bar_in)); in_pos = False
            continue

        if in_pos:
            held = i - bar_in; exit_now = False; reason = ""; exit_px = px
            if held >= max_hold: exit_now = True; reason = "TIME"
            elif atr > 0:
                if side == "LONG":
                    new_sl = px - sl_mult*atr
                    if new_sl > stop: stop = new_sl
                    if r["low"] <= stop: exit_now = True; reason = "SL"; exit_px = stop
                else:
                    new_sl = px + sl_mult*atr
                    if new_sl < stop: stop = new_sl
                    if r["high"] >= stop: exit_now = True; reason = "SL"; exit_px = stop
            if exit_now:
                pnl = _pnl(side, entry, exit_px, sz, cm); cash += sz*entry + pnl
                trades.append(Trade("","",side,label,entry,exit_px,sz,pnl,0,reason,held))
                if pnl < 0: loss_count += 1
                else: loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            if r.get(long_col, 0) == 1:
                risk = cash * RISK_PCT; sl_d = sl_mult * (atr if atr > 0 else px*0.02)
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm); in_pos = True; side = "LONG"; entry = px; bar_in = i
                    stop = px - sl_mult*(atr if atr > 0 else px*0.02)
            elif r.get(short_col, 0) == 1:
                risk = cash * RISK_PCT; sl_d = sl_mult * (atr if atr > 0 else px*0.02)
                sz = min(risk/sl_d, (cash*MAX_POS_PCT)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm); in_pos = True; side = "SHORT"; entry = px; bar_in = i
                    stop = px + sl_mult*(atr if atr > 0 else px*0.02)

    if in_pos:
        pnl = _pnl(side, entry, px, sz, cm); cash += sz*entry + pnl
        trades.append(Trade("","",side,label,entry,px,sz,pnl,0,"END",i-bar_in))

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    win_total = sum(t.pnl for t in wins)
    loss_total = sum(t.pnl for t in losses)
    pf = abs(win_total/loss_total) if loss_total != 0 else float('inf')
    total_pnl = sum(t.pnl for t in trades)
    eq_arr = np.array(eq); peak = np.maximum.accumulate(eq_arr); dd_arr = (peak-eq_arr)/peak
    max_dd = np.max(dd_arr)*100
    rets = np.diff(eq_arr)/eq_arr[:-1]
    sharpe = (np.mean(rets)/np.std(rets))*np.sqrt(365*6) if np.std(rets) > 0 else 0

    return {"label": label, "trades": len(trades), "wr": wr, "pf": pf, "pnl": total_pnl,
            "dd": max_dd, "sharpe": sharpe, "longs": sum(1 for t in trades if t.side=="LONG"),
            "shorts": sum(1 for t in trades if t.side=="SHORT"),
            "win_total": win_total, "loss_total": loss_total}

def main():
    print("Loading 4h data...")
    df4h = load_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_usdt_4h_unified.csv"))
    print(f"  4h: {len(df4h)} bars")

    print("Loading 1h data...")
    df1h = load_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_usdt_1h.csv"))
    print(f"  1h: {len(df1h)} bars")

    results = []

    # === TEST 1: 4h only (current) ===
    print("\n[1] 4h only (current)...")
    d = df4h.copy()
    d["ema55"] = d["close"].ewm(span=55, adjust=False).mean()
    d["donchian_h"] = d["high"].rolling(20).max()
    d["donchian_l"] = d["low"].rolling(20).min()
    d["donchian_mid"] = (d["donchian_h"] + d["donchian_l"]) / 2
    d["rsi"] = compute_rsi(d["close"], 14)
    d["rsi_prev"] = d["rsi"].shift(1)
    d["atr"] = compute_atr(d, 14)
    d["long"] = ((d["close"]>d["ema55"])&(d["close"]>d["donchian_mid"])&(d["rsi_prev"]<=48)&(d["rsi"]>d["rsi_prev"])&(d["rsi"]<55)).astype(int)
    d["short"] = ((d["close"]<d["ema55"])&(d["close"]<d["donchian_mid"])&(d["rsi_prev"]>=52)&(d["rsi"]<d["rsi_prev"])&(d["rsi"]>45)).astype(int)
    r = run_backtest(d, "long", "short", 3.0, 6.0, 20, "4h only")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # === TEST 2: 1h only ===
    print("\n[2] 1h only...")
    d = df1h.copy()
    d["ema55"] = d["close"].ewm(span=55, adjust=False).mean()
    d["donchian_h"] = d["high"].rolling(80).max()  # 20*4=80 for 1h equivalent
    d["donchian_l"] = d["low"].rolling(80).min()
    d["donchian_mid"] = (d["donchian_h"] + d["donchian_l"]) / 2
    d["rsi"] = compute_rsi(d["close"], 14)
    d["rsi_prev"] = d["rsi"].shift(1)
    d["atr"] = compute_atr(d, 14)
    d["long"] = ((d["close"]>d["ema55"])&(d["close"]>d["donchian_mid"])&(d["rsi_prev"]<=48)&(d["rsi"]>d["rsi_prev"])&(d["rsi"]<55)).astype(int)
    d["short"] = ((d["close"]<d["ema55"])&(d["close"]<d["donchian_mid"])&(d["rsi_prev"]>=52)&(d["rsi"]<d["rsi_prev"])&(d["rsi"]>45)).astype(int)
    r = run_backtest(d, "long", "short", 3.0, 6.0, 80, "1h only")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # === TEST 3: 4h trend + 1h entry (multi-timeframe) ===
    print("\n[3] 4h trend + 1h entry (multi-TF)...")
    # Get 4h trend signals
    d4 = df4h.copy()
    d4["ema55"] = d4["close"].ewm(span=55, adjust=False).mean()
    d4["donchian_h"] = d4["high"].rolling(20).max()
    d4["donchian_l"] = d4["low"].rolling(20).min()
    d4["donchian_mid"] = (d4["donchian_h"] + d4["donchian_l"]) / 2
    d4["rsi"] = compute_rsi(d4["close"], 14)
    d4["rsi_prev"] = d4["rsi"].shift(1)
    d4["atr"] = compute_atr(d4, 14)
    # 4h trend direction
    d4["trend_4h"] = 0
    d4.loc[d4["close"]>d4["ema55"], "trend_4h"] = 1
    d4.loc[d4["close"]<d4["ema55"], "trend_4h"] = -1

    # Resample 4h trend to 1h (forward fill)
    trend_1h = d4[["trend_4h"]].resample("1h").ffill()

    # Merge with 1h data
    d = df1h.copy()
    d["ema55"] = d["close"].ewm(span=55, adjust=False).mean()
    d["donchian_h"] = d["high"].rolling(80).max()
    d["donchian_l"] = d["low"].rolling(80).min()
    d["donchian_mid"] = (d["donchian_h"] + d["donchian_l"]) / 2
    d["rsi"] = compute_rsi(d["close"], 14)
    d["rsi_prev"] = d["rsi"].shift(1)
    d["atr"] = compute_atr(d, 14)

    # Merge 4h trend
    d = d.join(trend_1h["trend_4h"], how="left")
    d["trend_4h"] = d["trend_4h"].fillna(0).astype(int)

    # Entry: 1h RSI pullback IN DIRECTION of 4h trend
    d["long"] = ((d["trend_4h"]==1)
                 & (d["close"]>d["donchian_mid"])
                 & (d["rsi_prev"]<=48)
                 & (d["rsi"]>d["rsi_prev"])
                 & (d["rsi"]<55)).astype(int)
    d["short"] = ((d["trend_4h"]==-1)
                  & (d["close"]<d["donchian_mid"])
                  & (d["rsi_prev"]>=52)
                  & (d["rsi"]<d["rsi_prev"])
                  & (d["rsi"]>45)).astype(int)
    r = run_backtest(d, "long", "short", 3.0, 6.0, 80, "4h trend + 1h entry")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # === TEST 4: 1h with tighter SL/TP ===
    print("\n[4] 1h only (tight SL/TP: 2x/4x)...")
    d = df1h.copy()
    d["ema55"] = d["close"].ewm(span=55, adjust=False).mean()
    d["donchian_h"] = d["high"].rolling(80).max()
    d["donchian_l"] = d["low"].rolling(80).min()
    d["donchian_mid"] = (d["donchian_h"] + d["donchian_l"]) / 2
    d["rsi"] = compute_rsi(d["close"], 14)
    d["rsi_prev"] = d["rsi"].shift(1)
    d["atr"] = compute_atr(d, 14)
    d["long"] = ((d["close"]>d["ema55"])&(d["close"]>d["donchian_mid"])&(d["rsi_prev"]<=48)&(d["rsi"]>d["rsi_prev"])&(d["rsi"]<55)).astype(int)
    d["short"] = ((d["close"]<d["ema55"])&(d["close"]<d["donchian_mid"])&(d["rsi_prev"]>=52)&(d["rsi"]<d["rsi_prev"])&(d["rsi"]>45)).astype(int)
    r = run_backtest(d, "long", "short", 2.0, 4.0, 40, "1h tight SL/TP")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # === Summary ===
    print(f"\n{'='*90}")
    print(f"  TIMEFRAME COMPARISON")
    print(f"{'='*90}")
    print(f"  {'Approach':<30} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>8} {'DD%':>5} {'Sharpe':>7} {'L':>4} {'S':>4}")
    print(f"  {'-'*85}")
    for r in results:
        pf_s = f"{r['pf']:.2f}" if r['pf'] != float('inf') else "INF"
        print(f"  {r['label']:<30} {r['trades']:>6} {r['wr']:>4.0f}% {pf_s:>6} ${r['pnl']:>7.2f} {r['dd']:>4.0f}% {r['sharpe']:>7.2f} {r['longs']:>4} {r['shorts']:>4}")

    best = max(results, key=lambda x: x["sharpe"] if x["trades"] > 10 else -999)
    print(f"\n  => Best risk-adjusted: {best['label']} (Sharpe={best['sharpe']:.2f})")
    print(f"     Trades={best['trades']}, WR={best['wr']:.0f}%, PF={best['pf']:.2f}, DD={best['dd']:.1f}%")

if __name__ == "__main__":
    main()
