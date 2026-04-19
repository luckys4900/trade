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

def run_backtest_entry_timing(df, signal_col, entry_type, sl_mult, tp_mult, max_hold, label):
    """
    entry_type:
      'open': Enter at Open of bar i if signal was true at i-1 (Confirmed/Wait)
      'close': Enter at Close of bar i if signal is true at i (Aggressive/Don't Wait)
    """
    cash = 100.0; peak_eq = 100.0; eq = []; trades = []; cm = 0.0005
    in_pos = False; side = ""; entry = 0; bar_in = 0; sz = 0; stop = 0
    loss_count = 0; cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]; px = r["close"]; atr = r.get("atr", 0)
        
        # Determine entry price based on type
        if entry_type == 'open':
            # Signal based on previous bar (shifted), enter at current Open
            # Note: signal_col should be shifted in the df preparation
            entry_px = r["open"]
        else:
            # Signal based on current bar, enter at current Close
            entry_px = r["close"]

        pv = sz * px if in_pos else 0; equity = cash + pv
        peak_eq = max(peak_eq, equity); dd = (peak_eq-equity)/peak_eq if peak_eq > 0 else 0
        eq.append(equity)
        if dd >= 0.15:
            if in_pos:
                pnl = (px - entry)*sz - sz*px*cm if side=="LONG" else (entry-px)*sz - sz*px*cm
                cash += sz*entry + pnl
                trades.append({"pnl": pnl, "side": side, "reason": "DD"}); in_pos = False
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
                pnl = (exit_px - entry)*sz - sz*exit_px*cm if side=="LONG" else (entry-exit_px)*sz - sz*exit_px*cm
                cash += sz*entry + pnl
                trades.append({"pnl": pnl, "side": side, "reason": reason}); 
                if pnl < 0: loss_count += 1
                else: loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            # Check signal
            if r.get(signal_col, 0) == 1:
                risk = cash * 0.015; sl_d = sl_mult * (atr if atr > 0 else px*0.02)
                sz = min(risk/sl_d, (cash*0.40)/entry_px)
                if sz*entry_px >= 10 and sz*entry_px*(1+cm) <= cash:
                    cash -= sz*entry_px*(1+cm); in_pos = True; 
                    side = "LONG" if "long" in signal_col else "SHORT"
                    entry = entry_px; bar_in = i
                    stop = entry_px - sl_mult*(atr if atr > 0 else px*0.02) if side=="LONG" else entry_px + sl_mult*(atr if atr > 0 else px*0.02)

    if in_pos:
        pnl = (px - entry)*sz - sz*px*cm if side=="LONG" else (entry-px)*sz - sz*px*cm
        cash += sz*entry + pnl
        trades.append({"pnl": pnl, "side": side, "reason": "END"})

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    win_total = sum(t["pnl"] for t in wins)
    loss_total = sum(t["pnl"] for t in losses)
    pf = abs(win_total/loss_total) if loss_total != 0 else float('inf')
    total_pnl = sum(t["pnl"] for t in trades)
    eq_arr = np.array(eq); peak = np.maximum.accumulate(eq_arr); dd_arr = (peak-eq_arr)/peak
    max_dd = np.max(dd_arr)*100
    rets = np.diff(eq_arr)/eq_arr[:-1]
    sharpe = (np.mean(rets)/np.std(rets))*np.sqrt(365*6) if np.std(rets) > 0 else 0

    return {"label": label, "trades": len(trades), "wr": wr, "pf": pf, "pnl": total_pnl,
            "dd": max_dd, "sharpe": sharpe, "longs": sum(1 for t in trades if t["side"]=="LONG"),
            "shorts": sum(1 for t in trades if t["side"]=="SHORT")}

def main():
    print("Loading 4h data...")
    df = load_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_usdt_4h_unified.csv"))
    print(f"  {len(df)} bars")

    # Compute indicators
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["donchian_h"] = df["high"].rolling(20).max()
    df["donchian_l"] = df["low"].rolling(20).min()
    df["donchian_mid"] = (df["donchian_h"] + df["donchian_l"]) / 2
    df["rsi"] = compute_rsi(df["close"], 14)
    df["rsi_prev"] = df["rsi"].shift(1)
    df["atr"] = compute_atr(df, 14)

    # Base signals
    df["long_raw"] = ((df["close"]>df["ema55"])&(df["close"]>df["donchian_mid"])&(df["rsi_prev"]<=48)&(df["rsi"]>df["rsi_prev"])&(df["rsi"]<55)).astype(int)
    df["short_raw"] = ((df["close"]<df["ema55"])&(df["close"]<df["donchian_mid"])&(df["rsi_prev"]>=52)&(df["rsi"]<df["rsi_prev"])&(df["rsi"]>45)).astype(int)

    results = []

    # === TEST 1: Wait for Close (Confirmed) ===
    # Signal based on `shift(1)`, enter at `Open` of next bar.
    print("\n[1] Wait for Close (Confirmed)...")
    d = df.copy()
    d["long"] = d["long_raw"].shift(1)
    d["short"] = d["short_raw"].shift(1)
    r = run_backtest_entry_timing(d, "long", 'open', 3.0, 6.0, 20, "Wait (Open Entry)")
    # Note: run_backtest_entry_timing treats 'long' and 'short' separately, need to combine or run twice.
    # Simplified: Run combined logic.
    # Let's modify the function to handle both or just run one combined signal.
    # For simplicity, I'll combine them into one "signal" column with direction.
    # Actually, let's just run the logic inside main for clarity.

    # Re-implementing loop for accuracy
    def run_combined(df, long_col, short_col, entry_type, label):
        cash = 100.0; peak_eq = 100.0; eq = []; trades = []; cm = 0.0005
        in_pos = False; side = ""; entry = 0; bar_in = 0; sz = 0; stop = 0
        loss_count = 0; cool_until = 0

        for i in range(len(df)):
            r = df.iloc[i]; px = r["close"]; atr = r.get("atr", 0)
            entry_px = r["open"] if entry_type == 'open' else r["close"]
            
            pv = sz * px if in_pos else 0; equity = cash + pv
            peak_eq = max(peak_eq, equity); dd = (peak_eq-equity)/peak_eq if peak_eq > 0 else 0
            eq.append(equity)
            if dd >= 0.15:
                if in_pos:
                    pnl = (px - entry)*sz - sz*px*cm if side=="LONG" else (entry-px)*sz - sz*px*cm
                    cash += sz*entry + pnl
                    trades.append({"pnl": pnl, "side": side, "reason": "DD"}); in_pos = False
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
                    pnl = (exit_px - entry)*sz - sz*exit_px*cm if side=="LONG" else (entry-exit_px)*sz - sz*exit_px*cm
                    cash += sz*entry + pnl
                    trades.append({"pnl": pnl, "side": side, "reason": reason}); 
                    if pnl < 0: loss_count += 1
                    else: loss_count = 0
                    in_pos = False

            if not in_pos and i >= cool_until:
                if r.get(long_col, 0) == 1:
                    risk = cash * 0.015; sl_d = 3.0 * (atr if atr > 0 else px*0.02)
                    sz = min(risk/sl_d, (cash*0.40)/entry_px)
                    if sz*entry_px >= 10 and sz*entry_px*(1+cm) <= cash:
                        cash -= sz*entry_px*(1+cm); in_pos = True; side = "LONG"; entry = entry_px; bar_in = i
                        stop = entry_px - 3.0*(atr if atr > 0 else px*0.02)
                elif r.get(short_col, 0) == 1:
                    risk = cash * 0.015; sl_d = 3.0 * (atr if atr > 0 else px*0.02)
                    sz = min(risk/sl_d, (cash*0.40)/entry_px)
                    if sz*entry_px >= 10 and sz*entry_px*(1+cm) <= cash:
                        cash -= sz*entry_px*(1+cm); in_pos = True; side = "SHORT"; entry = entry_px; bar_in = i
                        stop = entry_px + 3.0*(atr if atr > 0 else px*0.02)

        if in_pos:
            pnl = (px - entry)*sz - sz*px*cm if side=="LONG" else (entry-px)*sz - sz*px*cm
            cash += sz*entry + pnl
            trades.append({"pnl": pnl, "side": side, "reason": "END"})

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        wr = len(wins)/len(trades)*100 if trades else 0
        win_total = sum(t["pnl"] for t in wins)
        loss_total = sum(t["pnl"] for t in losses)
        pf = abs(win_total/loss_total) if loss_total != 0 else float('inf')
        total_pnl = sum(t["pnl"] for t in trades)
        eq_arr = np.array(eq); peak = np.maximum.accumulate(eq_arr); dd_arr = (peak-eq_arr)/peak
        max_dd = np.max(dd_arr)*100
        rets = np.diff(eq_arr)/eq_arr[:-1]
        sharpe = (np.mean(rets)/np.std(rets))*np.sqrt(365*6) if np.std(rets) > 0 else 0

        return {"label": label, "trades": len(trades), "wr": wr, "pf": pf, "pnl": total_pnl,
                "dd": max_dd, "sharpe": sharpe, "longs": sum(1 for t in trades if t["side"]=="LONG"),
                "shorts": sum(1 for t in trades if t["side"]=="SHORT")}

    # Test 1: Wait (Signal t-1, Entry Open t)
    print("\n[1] Wait for Close (Confirmed)...")
    d = df.copy()
    d["long"] = d["long_raw"].shift(1)
    d["short"] = d["short_raw"].shift(1)
    r = run_combined(d, "long", "short", 'open', "Wait (Open Entry)")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # Test 2: Don't Wait (Signal t, Entry Close t)
    print("\n[2] Don't Wait (Aggressive)...")
    d = df.copy()
    d["long"] = d["long_raw"]
    d["short"] = d["short_raw"]
    r = run_combined(d, "long", "short", 'close', "Don't Wait (Close Entry)")
    results.append(r)
    print(f"  Trades={r['trades']} WR={r['wr']:.0f}% PF={r['pf']:.2f} PnL=${r['pnl']:.2f} DD={r['dd']:.1f}% Sharpe={r['sharpe']:.2f}")

    # Test 3: Repainting Simulation (Signal t, Entry Open t+1? No, Entry Close t is best proxy for "Don't Wait")
    # Actually, let's add a test for "Repainting Risk":
    # If we enter on Signal(t) but the signal vanishes? We can't test this.
    # But we can test "Signal(t) -> Entry Open(t+1)" which is "Wait 1 bar after signal".
    # No, let's stick to the user's question.

    print(f"\n{'='*80}")
    print(f"  ENTRY TIMING COMPARISON")
    print(f"{'='*80}")
    print(f"  {'Approach':<30} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>8} {'DD%':>5} {'Sharpe':>7}")
    print(f"  {'-'*75}")
    for r in results:
        pf_s = f"{r['pf']:.2f}" if r['pf'] != float('inf') else "INF"
        print(f"  {r['label']:<30} {r['trades']:>6} {r['wr']:>4.0f}% {pf_s:>6} ${r['pnl']:>7.2f} {r['dd']:>4.0f}% {r['sharpe']:>7.2f}")

    best = max(results, key=lambda x: x["sharpe"] if x["trades"] > 10 else -999)
    print(f"\n  => Best risk-adjusted: {best['label']} (Sharpe={best['sharpe']:.2f})")

if __name__ == "__main__":
    main()
