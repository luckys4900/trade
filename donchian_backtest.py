# -*- coding: utf-8 -*-
"""
Donchian Trend Following - Academic Paper Replication
=====================================================
出典: "Catching Crypto Trends" (Zarattini, Pagani, Barbon)
検証: BTC + アルトコインでの再現性、手数料込み実力
"""

import os, glob, numpy as np, pandas as pd
from dataclasses import dataclass

INITIAL_CASH = 10000.0
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.25

# Fee structure (Hyperliquid Taker)
TAKER_FEE = 0.00035  # 0.035% per side (Hyperliquid maker is 0, taker 0.035%)
SLIPPAGE_PCT = 0.0002
TOTAL_COMM = TAKER_FEE * 2 + SLIPPAGE_PCT  # ~0.0009 = 0.09%

# Donchian parameters (from paper)
DONCHIAN_PERIODS = [5, 10, 20, 30, 60, 90]  # 4h equivalent of paper's day periods
# Paper uses 5,10,20,30,60,90,150,250,360 days
# On 4h: 6 bars/day, so 5d=30, 10d=60, 20d=120, 30d=180, 60d=360, 90d=540
DONCHIAN_4H = [10, 20, 40, 60, 80, 100]  # Shorter periods for 1-year data

# Trailing stop (from paper: never moves down, exits when close below)
TRAILING_STOP_PERIODS = [20, 30, 60]  # 4h equivalent

# Volatility target (from paper: 25% annualized)
VOL_TARGET = 0.25

# Rebalance threshold (from paper: 20%)
REBALANCE_THRESHOLD = 0.20


@dataclass
class Trade:
    t_in: str
    t_out: str
    side: str
    strat: str
    p_in: float
    p_out: float
    sz: float
    pnl: float
    pnl_pct: float
    reason: str
    bars: int = 0


def compute_atr(df, period):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def compute_realized_vol(df, period):
    """Annualized realized volatility from 4h returns"""
    returns = df["close"].pct_change()
    vol_4h = returns.rolling(period).std()
    # Annualize: 365*6 4h bars per year
    vol_annual = vol_4h * np.sqrt(365 * 6)
    return vol_annual


def _pnl_with_fees(side, entry, exit_px, sz, comm_pct):
    entry_cost = sz * entry * comm_pct
    exit_cost = sz * exit_px * comm_pct
    if side == "LONG":
        gross = (exit_px - entry) * sz
    else:
        gross = (entry - exit_px) * sz
    return gross - entry_cost - exit_cost


def load_and_prepare(path):
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ('open', 'o'): col_map[c] = 'open'
        elif cl in ('high', 'h'): col_map[c] = 'high'
        elif cl in ('low', 'l'): col_map[c] = 'low'
        elif cl in ('close', 'c'): col_map[c] = 'close'
        elif cl in ('volume', 'v'): col_map[c] = 'volume'
    df = df.rename(columns=col_map)
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float).sort_index()
    df["atr14"] = compute_atr(df, 14)
    df["vol60"] = compute_realized_vol(df, 60)
    # Donchian channels
    for period in DONCHIAN_4H:
        df[f"donchian_high_{period}"] = df["high"].rolling(period).max()
        df[f"donchian_low_{period}"] = df["low"].rolling(period).min()
    return df


def run_donchian_single(df, coin_name, donchian_period, trailing_period, variant_name):
    """Single Donchian strategy with trailing stop"""
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    in_pos = False
    entry = 0
    ts_in = ""
    bar_in = 0
    sz = 0
    trailing_stop = 0
    loss_count = 0
    cool_until = 0

    dh_col = f"donchian_high_{donchian_period}"

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo = r["close"], r["high"], r["low"]
        atr = r.get("atr14", 0)
        vol = r.get("vol60", 0.5)

        pv = sz * px if in_pos else 0
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            if in_pos:
                exit_px = px * (1 - SLIPPAGE_PCT)
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            # Update trailing stop (never moves down)
            new_trail = df["low"].iloc[max(0, i-trailing_period+1):i+1].min()
            if new_trail > trailing_stop:
                trailing_stop = new_trail

            # Exit if close below trailing stop
            if px < trailing_stop:
                exit_now = True
                reason = "TRAILING_STOP"
                exit_px = trailing_stop * (1 - SLIPPAGE_PCT)

            if exit_now:
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            # Entry: close >= Donchian high
            if r[dh_col] > 0 and px >= r[dh_col]:
                # Volatility-based position sizing (paper: target 25% vol)
                if vol > 0:
                    # Target position size for vol targeting
                    target_notional = cash * (VOL_TARGET / vol)
                    target_notional = min(target_notional, cash * MAX_POS_PCT)
                    sz = target_notional / px
                else:
                    sz = (cash * MAX_POS_PCT) / px

                entry_cost = sz * px * (1 + TOTAL_COMM)
                if sz * px >= 10 and entry_cost <= cash:
                    cash -= entry_cost
                    in_pos = True
                    entry = px * (1 + SLIPPAGE_PCT)
                    ts_in = ts
                    bar_in = i
                    trailing_stop = lo  # Initial stop at current low

    if in_pos:
        exit_px = px * (1 - SLIPPAGE_PCT)
        pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                           (exit_px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


def run_donchian_combo(df, coin_name, variant_name):
    """Ensemble: multiple Donchian periods, entry when ANY signals"""
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    in_pos = False
    entry = 0
    ts_in = ""
    bar_in = 0
    sz = 0
    trailing_stop = 0
    active_signals = 0
    loss_count = 0
    cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo = r["close"], r["high"], r["low"]
        vol = r.get("vol60", 0.5)

        pv = sz * px if in_pos else 0
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            if in_pos:
                exit_px = px * (1 - SLIPPAGE_PCT)
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            # Update trailing stop: min of all trailing stops
            min_trail = px
            for tp in TRAILING_STOP_PERIODS:
                trail = df["low"].iloc[max(0, i-tp+1):i+1].min()
                if trail < min_trail:
                    min_trail = trail
            if min_trail > trailing_stop:
                trailing_stop = min_trail

            if px < trailing_stop:
                exit_now = True
                reason = "TRAILING_STOP"
                exit_px = trailing_stop * (1 - SLIPPAGE_PCT)

            if exit_now:
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            # Count how many Donchian channels are broken
            signals = 0
            for period in DONCHIAN_4H:
                dh_col = f"donchian_high_{period}"
                if r[dh_col] > 0 and px >= r[dh_col]:
                    signals += 1

            # Entry: at least 2 signals (ensemble filter)
            if signals >= 2:
                if vol > 0:
                    target_notional = cash * (VOL_TARGET / vol)
                    target_notional = min(target_notional, cash * MAX_POS_PCT)
                    sz = target_notional / px
                else:
                    sz = (cash * MAX_POS_PCT) / px

                entry_cost = sz * px * (1 + TOTAL_COMM)
                if sz * px >= 10 and entry_cost <= cash:
                    cash -= entry_cost
                    in_pos = True
                    entry = px * (1 + SLIPPAGE_PCT)
                    ts_in = ts
                    bar_in = i
                    trailing_stop = lo
                    active_signals = signals

    if in_pos:
        exit_px = px * (1 - SLIPPAGE_PCT)
        pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                           (exit_px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


def analyze(trades, eq, variant_name, coin_name):
    if not trades:
        return None
    pnls = [t.pnl for t in trades]
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins) / len(trades) * 100
    avg_w = np.mean([t.pnl for t in wins]) if wins else 0
    avg_l = np.mean([t.pnl for t in losses]) if losses else 0
    win_total = sum(t.pnl for t in wins)
    loss_total = sum(t.pnl for t in losses)
    pf = abs(win_total / loss_total) if loss_total != 0 else float('inf')
    total_pnl = sum(pnls)
    avg_trade = total_pnl / len(trades)

    eq_arr = np.array(eq)
    peak = np.maximum.accumulate(eq_arr)
    dd = (peak - eq_arr) / peak
    max_dd = np.max(dd) * 100

    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(365*6) if np.std(rets) > 0 else 0

    total_fees = sum(t.sz * (t.p_in + t.p_out) * TAKER_FEE * 2 for t in trades)

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        if t.reason not in exit_reasons:
            exit_reasons[t.reason] = {"count": 0, "pnl": 0, "wins": 0}
        exit_reasons[t.reason]["count"] += 1
        exit_reasons[t.reason]["pnl"] += t.pnl
        if t.pnl > 0:
            exit_reasons[t.reason]["wins"] += 1

    return {
        "coin": coin_name,
        "variant": variant_name,
        "trades": len(trades),
        "win_rate": round(wr, 1),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "profit_factor": round(pf, 2) if pf != float('inf') else "INF",
        "total_pnl": round(total_pnl, 2),
        "avg_trade": round(avg_trade, 2),
        "max_dd": round(max_dd, 1),
        "sharpe": round(sharpe, 2),
        "total_fees": round(total_fees, 2),
        "exit_reasons": exit_reasons,
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    print(f"\n{'='*110}")
    print(f"  DONCHIAN TREND FOLLOWING - Academic Paper Replication")
    print(f"  Source: 'Catching Crypto Trends' (Zarattini, Pagani, Barbon)")
    print(f"  Fees: {TOTAL_COMM*100:.2f}% round-trip | Vol Target: {VOL_TARGET*100:.0f}%")
    print(f"  Coins: {len(files)}")
    print(f"{'='*110}")

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        df = load_and_prepare(fpath)
        if len(df) < 150:
            print(f"  SKIP {coin}: only {len(df)} bars (need 150+)")
            continue

        coin_results = {}

        # Single period strategies
        for dp, tp in zip([10, 20, 40], [20, 30, 60]):
            vname = f"D{dp}_T{tp}"
            trades, eq = run_donchian_single(df, coin, dp, tp, vname)
            r = analyze(trades, eq, vname, coin)
            if r:
                coin_results[vname] = r

        # Combo (ensemble)
        trades_c, eq_c = run_donchian_combo(df, coin, "Combo_2sig")
        r_c = analyze(trades_c, eq_c, "Combo_2sig", coin)
        if r_c:
            coin_results["Combo_2sig"] = r_c

        all_results[coin] = coin_results

    # Summary
    print(f"\n{'='*120}")
    print(f"  RESULTS")
    print(f"{'='*120}")
    print(f"  {'Coin':<12} {'Variant':<12} {'Trades':>6} {'WR%':>5} {'PF':>5} {'PnL$':>8} {'Fees$':>6} {'DD%':>5} {'Sharpe':>6}")
    print(f"  {'-'*85}")

    for coin in sorted(all_results.keys()):
        for vname in all_results[coin]:
            r = all_results[coin][vname]
            pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
            print(f"  {coin:<12} {vname:<12} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>5} ${r['total_pnl']:>7.0f} ${r['total_fees']:>5.0f} {r['max_dd']:>4.0f}% {r['sharpe']:>6.2f}")

    # Viable combos
    print(f"\n{'='*120}")
    print(f"  VIABLE COMBOS (PF>1.2, MaxDD<20%, Trades>5)")
    print(f"{'='*120}")
    viable = []
    for coin in all_results:
        for vname in all_results[coin]:
            r = all_results[coin][vname]
            pf_val = r["profit_factor"] if isinstance(r["profit_factor"], (int, float)) else 999
            if pf_val > 1.2 and r["max_dd"] < 20 and r["trades"] > 5:
                viable.append((coin, vname, r))
    viable.sort(key=lambda x: x[2]["sharpe"], reverse=True)
    for i, (coin, vname, r) in enumerate(viable[:15]):
        pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
        print(f"  {i+1:>2}. {coin:<10} {vname:<12} Trades={r['trades']:>3} WR={r['win_rate']:.0f}% PF={pf_s} PnL=${r['total_pnl']:.0f} DD={r['max_dd']:.0f}% Sharpe={r['sharpe']:.2f}")

    if not viable:
        print("  No combos meet criteria.")

    # Best per coin
    print(f"\n{'='*120}")
    print(f"  BEST PER COIN (by Sharpe)")
    print(f"{'='*120}")
    for coin in sorted(all_results.keys()):
        if not all_results[coin]:
            continue
        best_v = max(all_results[coin].items(), key=lambda x: x[1]["sharpe"])
        r = best_v[1]
        pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
        print(f"  {coin:<12} {best_v[0]:<12} Trades={r['trades']:>3} WR={r['win_rate']:.0f}% PF={pf_s} PnL=${r['total_pnl']:.0f} DD={r['max_dd']:.0f}% Sharpe={r['sharpe']:.2f}")

    # Exit reason analysis for top combos
    if viable:
        print(f"\n{'='*120}")
        print(f"  EXIT REASON ANALYSIS (Top 5)")
        print(f"{'='*120}")
        for i, (coin, vname, r) in enumerate(viable[:5]):
            print(f"\n  {coin} - {vname}")
            for reason, data in sorted(r["exit_reasons"].items(), key=lambda x: -x[1]["pnl"]):
                r_wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
                print(f"    {reason:<15} Count={data['count']:>3} WR={r_wr:>3.0f}% PnL=${data['pnl']:>8.0f} Avg=${data['pnl']/data['count']:>7.0f}")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
