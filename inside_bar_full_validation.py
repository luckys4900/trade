# -*- coding: utf-8 -*-
"""
Inside Bar Strategy - Full Validation
======================================
1. SL改善版バックテスト（Inside Bar安値をSLに設定）
2. 全12コイン横断検証
3. QSの結論との整合性検証
"""

import os, glob, numpy as np, pandas as pd
from dataclasses import dataclass

INITIAL_CASH = 10000.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.25


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


def compute_rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def compute_atr(df, period):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    return (entry - exit_px) * sz - notional * comm


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
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    return df


def run_backtest_variants(df, coin_name):
    """Run 4 variants of Inside Bar strategy"""
    results = {}

    # Variant A: Original (10-bar time exit, no SL)
    results["A_Original"] = _run_single(df, coin_name, "A_Original",
        long_cond=lambda r, i: r["inside_bar"].iloc[i-1] if i > 0 else False,
        entry_on_next=True,
        exit_type="time", max_hold=10,
        use_ib_sl=False
    )

    # Variant B: Inside Bar low as SL + 10-bar time exit
    results["B_IB_SL"] = _run_single(df, coin_name, "B_IB_SL",
        long_cond=lambda r, i: r["inside_bar"].iloc[i-1] if i > 0 else False,
        entry_on_next=True,
        exit_type="time", max_hold=10,
        use_ib_sl=True
    )

    # Variant C: Inside Bar + EMA55 filter + IB SL
    results["C_EMA55_IBSL"] = _run_single(df, coin_name, "C_EMA55_IBSL",
        long_cond=lambda r, i: r["inside_bar"].iloc[i-1] and r["close"].iloc[i] > r["ema55"].iloc[i] if i > 0 else False,
        entry_on_next=False,
        exit_type="time", max_hold=10,
        use_ib_sl=True
    )

    # Variant D: Inside Bar + EMA55 + RSI<50 filter + IB SL (QS-style)
    results["D_EMA55_RSI_IBSL"] = _run_single(df, coin_name, "D_EMA55_RSI_IBSL",
        long_cond=lambda r, i: r["inside_bar"].iloc[i-1] and r["close"].iloc[i] > r["ema55"].iloc[i] and r["rsi14"].iloc[i] < 50 if i > 0 else False,
        entry_on_next=False,
        exit_type="time", max_hold=10,
        use_ib_sl=True
    )

    return results


def _run_single(df, coin, variant_name, long_cond, entry_on_next, exit_type, max_hold, use_ib_sl):
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    cm = COMM_PCT
    in_pos = False
    entry = 0
    ts_in = ""
    bar_in = 0
    sz = 0
    ib_low = 0  # Inside Bar low for SL
    loss_count = 0
    cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo = r["close"], r["high"], r["low"]
        atr = r.get("atr14", 0)

        pv = sz * px if in_pos else 0
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            if in_pos:
                pnl = _pnl("LONG", entry, px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, px, sz, pnl,
                                   (px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            if held >= max_hold:
                exit_now = True
                reason = "TIME_EXIT"
            elif use_ib_sl and ib_low > 0:
                if lo <= ib_low:
                    exit_now = True
                    reason = "IB_SL"
                    exit_px = ib_low

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
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
            if long_cond(df, i):
                risk = cash * RISK_PCT
                sz = (cash * MAX_POS_PCT) / px
                if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                    cash -= sz * px * (1 + cm)
                    in_pos = True
                    entry = px
                    ts_in = ts
                    bar_in = i
                    ib_low = df["low"].iloc[i-1] if i > 0 else px * 0.95

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


def analyze(trades, eq, variant_name):
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
        "exit_reasons": exit_reasons,
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    print(f"\n{'='*90}")
    print(f"  INSIDE BAR STRATEGY - FULL VALIDATION")
    print(f"  Variants: A=Original, B=IB SL, C=EMA55+IB SL, D=EMA55+RSI+IB SL")
    print(f"  Coins: {len(files)}")
    print(f"{'='*90}")

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        df = load_and_prepare(fpath)
        if len(df) < 100:
            continue

        results = run_backtest_variants(df, coin)
        coin_results = {}
        for vname, (trades, eq) in results.items():
            r = analyze(trades, eq, vname)
            if r:
                coin_results[vname] = r

        all_results[coin] = coin_results

    # Summary table
    print(f"\n{'='*120}")
    print(f"  FULL RESULTS MATRIX")
    print(f"{'='*120}")

    variants = ["A_Original", "B_IB_SL", "C_EMA55_IBSL", "D_EMA55_RSI_IBSL"]
    for v in variants:
        print(f"\n  --- {v} ---")
        print(f"  {'Coin':<15} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>10} {'MaxDD%':>6} {'Sharpe':>6} {'Avg$':>8}")
        print(f"  {'-'*80}")
        for coin in sorted(all_results.keys()):
            if v in all_results[coin]:
                r = all_results[coin][v]
                pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
                print(f"  {coin:<15} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>6} ${r['total_pnl']:>9.0f} {r['max_dd']:>5.0f}% {r['sharpe']:>6.2f} ${r['avg_trade']:>7.0f}")

    # Best variant per coin
    print(f"\n{'='*120}")
    print(f"  BEST VARIANT PER COIN (by Sharpe)")
    print(f"{'='*120}")
    print(f"  {'Coin':<15} {'Best Variant':<20} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>10} {'MaxDD%':>6} {'Sharpe':>6}")
    print(f"  {'-'*80}")
    for coin in sorted(all_results.keys()):
        best_v = None
        best_sharpe = -999
        for v in variants:
            if v in all_results[coin]:
                r = all_results[coin][v]
                if r["sharpe"] > best_sharpe and r["trades"] >= 5:
                    best_sharpe = r["sharpe"]
                    best_v = v
        if best_v:
            r = all_results[coin][best_v]
            pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
            print(f"  {coin:<15} {best_v:<20} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>6} ${r['total_pnl']:>9.0f} {r['max_dd']:>5.0f}% {r['sharpe']:>6.2f}")

    # Overall best variant
    print(f"\n{'='*120}")
    print(f"  OVERALL VARIANT COMPARISON (averages across all coins)")
    print(f"{'='*120}")
    for v in variants:
        vals = [all_results[c][v] for c in all_results if v in all_results[c]]
        if vals:
            avg_trades = np.mean([r["trades"] for r in vals])
            avg_wr = np.mean([r["win_rate"] for r in vals])
            avg_pnl = np.mean([r["total_pnl"] for r in vals])
            avg_dd = np.mean([r["max_dd"] for r in vals])
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            pf_vals = [r["profit_factor"] for r in vals if isinstance(r["profit_factor"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0
            print(f"  {v:<20} Trades={avg_trades:.0f}  WR={avg_wr:.0f}%  PF={avg_pf:.2f}  PnL=${avg_pnl:.0f}  DD={avg_dd:.0f}%  Sharpe={avg_sharpe:.2f}")

    # Viable combos (PF>1.2, MaxDD<25%, Trades>10)
    print(f"\n{'='*120}")
    print(f"  VIABLE COMBOS (PF>1.2, MaxDD<25%, Trades>10)")
    print(f"{'='*120}")
    viable = []
    for coin in all_results:
        for v in variants:
            if v in all_results[coin]:
                r = all_results[coin][v]
                pf_val = r["profit_factor"] if isinstance(r["profit_factor"], (int, float)) else 999
                if pf_val > 1.2 and r["max_dd"] < 25 and r["trades"] > 10:
                    viable.append((coin, v, r))
    viable.sort(key=lambda x: x[2]["sharpe"], reverse=True)
    for i, (coin, v, r) in enumerate(viable[:15]):
        pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
        print(f"  {i+1:>2}. {coin:<12} {v:<20} Trades={r['trades']:>3} WR={r['win_rate']:.0f}% PF={pf_s} PnL=${r['total_pnl']:.0f} DD={r['max_dd']:.0f}% Sharpe={r['sharpe']:.2f}")

    if not viable:
        print("  No combos meet strict criteria.")

    # Exit reason analysis for best variant
    print(f"\n{'='*120}")
    print(f"  EXIT REASON ANALYSIS (Top 5 viable combos)")
    print(f"{'='*120}")
    for i, (coin, v, r) in enumerate(viable[:5]):
        print(f"\n  {coin} - {v}")
        for reason, data in sorted(r["exit_reasons"].items(), key=lambda x: -x[1]["pnl"]):
            r_wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
            print(f"    {reason:<15} Count={data['count']:>3} WR={r_wr:>3.0f}% PnL=${data['pnl']:>8.0f} Avg=${data['pnl']/data['count']:>7.0f}")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
