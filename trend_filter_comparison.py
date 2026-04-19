import os, sys, numpy as np, pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_unified_strategy import fetch_ohlcv, Trade, INITIAL_CASH, COMM_PCT, RISK_PCT, MAX_POS_PCT, MAX_LOSSES, COOLDOWN, DD_HALT

def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG": return (exit_px-entry)*sz - notional*comm
    else: return (entry-exit_px)*sz - notional*comm

def compute_indicators_v1(df):
    """Original: 3-condition trend"""
    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["slope"] = df["ema_f"].pct_change(10)
    df["donchian_h"] = df["high"].rolling(20).max()
    df["donchian_l"] = df["low"].rolling(20).min()
    df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2
    
    df["trend"] = "RANGE"
    df.loc[(df["close"]>df["ema_s"])&(df["ema_f"]>df["ema_s"])&(df["slope"]>0),"trend"]="UPTREND"
    df.loc[(df["close"]<df["ema_s"])&(df["ema_f"]<df["ema_s"])&(df["slope"]<0),"trend"]="DOWNTREND"
    
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+gain/loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)
    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()
    
    df["long"] = ((df["trend"]=="UPTREND")&(df["close"]>df["donchian_mid"])&(df["rsi_prev"]<=48)&(df["rsi"]>df["rsi_prev"])&(df["rsi"]<55)).astype(int)
    df["short"] = ((df["trend"]=="DOWNTREND")&(df["close"]<df["donchian_mid"])&(df["rsi_prev"]>=52)&(df["rsi"]<df["rsi_prev"])&(df["rsi"]>45)).astype(int)
    return df

def compute_indicators_v2(df):
    """Simplified: close vs EMA55 only"""
    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["slope"] = df["ema_f"].pct_change(10)
    df["donchian_h"] = df["high"].rolling(20).max()
    df["donchian_l"] = df["low"].rolling(20).min()
    df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2
    
    df["trend"] = "RANGE"
    df.loc[df["close"]>df["ema_s"],"trend"]="UPTREND"
    df.loc[df["close"]<df["ema_s"],"trend"]="DOWNTREND"
    
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+gain/loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)
    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()
    
    df["long"] = ((df["trend"]=="UPTREND")&(df["close"]>df["donchian_mid"])&(df["rsi_prev"]<=48)&(df["rsi"]>df["rsi_prev"])&(df["rsi"]<55)).astype(int)
    df["short"] = ((df["trend"]=="DOWNTREND")&(df["close"]<df["donchian_mid"])&(df["rsi_prev"]>=52)&(df["rsi"]<df["rsi_prev"])&(df["rsi"]>45)).astype(int)
    return df

def compute_indicators_v3(df):
    """Donchian-only trend filter (no EMA trend)"""
    df["ema_f"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_s"] = df["close"].ewm(span=55, adjust=False).mean()
    df["slope"] = df["ema_f"].pct_change(10)
    df["donchian_h"] = df["high"].rolling(20).max()
    df["donchian_l"] = df["low"].rolling(20).min()
    df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2
    
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+gain/loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)
    tr = pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),(df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, min_periods=14).mean()
    
    df["long"] = ((df["close"]>df["donchian_mid"])&(df["rsi_prev"]<=48)&(df["rsi"]>df["rsi_prev"])&(df["rsi"]<55)).astype(int)
    df["short"] = ((df["close"]<df["donchian_mid"])&(df["rsi_prev"]>=52)&(df["rsi"]<df["rsi_prev"])&(df["rsi"]>45)).astype(int)
    return df

def run_backtest(df, long_col, short_col, label):
    cash = 100.0; peak_eq = 100.0; eq = []; trades = []; cm = 0.0005
    in_pos = False; side = ""; entry = 0; bar_in = 0; sz = 0; stop = 0
    loss_count = 0; cool_until = 0
    
    for i in range(len(df)):
        r = df.iloc[i]; px = r["close"]; atr = r.get("atr", 0)
        pv = sz * px if in_pos else 0; equity = cash + pv
        peak_eq = max(peak_eq, equity); dd = (peak_eq-equity)/peak_eq if peak_eq > 0 else 0
        eq.append(equity)
        if dd >= 0.15:
            if in_pos:
                pnl = _pnl(side, entry, px, sz, cm); cash += sz*entry + pnl
                trades.append(Trade("","",side,label,entry,px,sz,pnl,0,"DD_HALT",i-bar_in)); in_pos = False
            continue
        
        if in_pos:
            held = i - bar_in; exit_now = False; reason = ""; exit_px = px
            if held >= 20: exit_now = True; reason = "TIME"
            elif atr > 0:
                if side == "LONG":
                    new_sl = px - 3.0*atr
                    if new_sl > stop: stop = new_sl
                    if r["low"] <= stop: exit_now = True; reason = "SL"; exit_px = stop
                else:
                    new_sl = px + 3.0*atr
                    if new_sl < stop: stop = new_sl
                    if r["high"] >= stop: exit_now = True; reason = "SL"; exit_px = stop
            if exit_now:
                pnl = _pnl(side, entry, exit_px, sz, cm); cash += sz*entry + pnl
                trades.append(Trade("","",side,label,entry,exit_px,sz,pnl,0,reason,held))
                if pnl < 0: loss_count += 1; 
                else: loss_count = 0
                in_pos = False
        
        if not in_pos and i >= cool_until:
            if r.get(long_col, 0) == 1:
                risk = cash * 0.015; sl_d = 3.0 * (atr if atr > 0 else px*0.02)
                sz = min(risk/sl_d, (cash*0.40)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm); in_pos = True; side = "LONG"; entry = px; bar_in = i
                    stop = px - 3.0*(atr if atr > 0 else px*0.02)
            elif r.get(short_col, 0) == 1:
                risk = cash * 0.015; sl_d = 3.0 * (atr if atr > 0 else px*0.02)
                sz = min(risk/sl_d, (cash*0.40)/px)
                if sz*px >= 10 and sz*px*(1+cm) <= cash:
                    cash -= sz*px*(1+cm); in_pos = True; side = "SHORT"; entry = px; bar_in = i
                    stop = px + 3.0*(atr if atr > 0 else px*0.02)
    
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
    
    return {"label": label, "trades": len(trades), "wr": wr, "pf": pf, "pnl": total_pnl, "dd": max_dd, "sharpe": sharpe, "longs": sum(1 for t in trades if t.side=="LONG"), "shorts": sum(1 for t in trades if t.side=="SHORT")}

def main():
    print("Fetching data...")
    df = fetch_ohlcv(730, "4h", "btc_usdt_4h_unified.csv")
    print(f"Data: {len(df)} bars")
    
    results = []
    for ver, compute_fn, name in [(1, compute_indicators_v1, "V1: 3-cond trend"), (2, compute_indicators_v2, "V2: close vs EMA55"), (3, compute_indicators_v3, "V3: Donchian only")]:
        print(f"\nTesting {name}...")
        df2 = compute_fn(df.copy())
        longs = df2["long"].sum()
        shorts = df2["short"].sum()
        print(f"  Signals: L={longs} S={shorts}")
        r = run_backtest(df2, "long", "short", name)
        results.append(r)
        print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f} L={r['longs']} S={r['shorts']}")
    
    print(f"\n{'='*80}")
    print(f"  COMPARISON")
    print(f"{'='*80}")
    print(f"  {'Version':<25} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>8} {'DD%':>5} {'Sharpe':>7} {'L':>4} {'S':>4}")
    print(f"  {'-'*75}")
    for r in results:
        pf_s = f"{r['pf']:.2f}" if r['pf'] != float('inf') else "INF"
        print(f"  {r['label']:<25} {r['trades']:>6} {r['wr']:>4.0f}% {pf_s:>6} ${r['pnl']:>7.2f} {r['dd']:>4.0f}% {r['sharpe']:>7.2f} {r['longs']:>4} {r['shorts']:>4}")
    
    best = max(results, key=lambda x: x["sharpe"] if x["trades"] > 5 else -999)
    print(f"\n  => Best: {best['label']} (Sharpe={best['sharpe']:.2f})")

if __name__ == "__main__":
    main()
