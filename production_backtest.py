# -*- coding: utf-8 -*-
"""
Inside Bar Strategy - Production-Ready Backtest
================================================
プロ本番想定での最終検証
1. ATRベース固定リスクサイジング（1.5%）
2. 手数料（Taker 0.05%×2）+ スリッページ（0.02%）
3. SL余裕（IB安値 - ATR×0.5）+ ギャップ考慮
"""

import os, glob, numpy as np, pandas as pd
from dataclasses import dataclass

# Production Parameters
INITIAL_CASH = 211.0
RISK_PCT = 0.015  # 1トレードのリスクを資金の1.5%に固定
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.20

# Fee & Slippage
TAKER_FEE = 0.0005  # 0.05% per side
SLIPPAGE_PCT = 0.0002  # 0.02%
TOTAL_COMM = TAKER_FEE * 2 + SLIPPAGE_PCT  # 0.0012 = 0.12%

# SL Settings
SL_BUFFER_ATR_MULT = 0.5  # IB安値 - ATR×0.5

# Time Exit
MAX_HOLD = 10


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
    risk_pct: float  # 実際のリスク%
    reason: str
    bars: int = 0


def compute_atr(df, period):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def _pnl_with_fees(side, entry, exit_px, sz, comm_pct):
    """手数料・スリッページ込みのPnL計算"""
    # Entry cost
    entry_cost = sz * entry * comm_pct
    # Exit cost
    exit_cost = sz * exit_px * comm_pct
    # Gross PnL
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
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    return df


def run_production_backtest(df, coin_name, variant_name, use_ema_filter=False):
    """Production-ready backtest with proper risk management"""
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    in_pos = False
    entry = 0
    ts_in = ""
    bar_in = 0
    sz = 0
    sl_price = 0
    risk_amount = 0
    loss_count = 0
    cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo = r["close"], r["high"], r["low"]
        atr = r.get("atr14", 0)

        # Equity
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
                                   (exit_px/entry-1)*100, risk_amount/cash*100 if cash > 0 else 0, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            if held >= MAX_HOLD:
                exit_now = True
                reason = "TIME_EXIT"
            elif sl_price > 0 and lo <= sl_price:
                exit_now = True
                reason = "IB_SL"
                exit_px = sl_price * (1 - SLIPPAGE_PCT)  # SL発動時はスリッページ追加

            if exit_now:
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                actual_risk = risk_amount
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, actual_risk/INITIAL_CASH*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            # Check entry condition
            ib_prev = df["inside_bar"].iloc[i-1] if i > 0 else False
            ema_ok = (not use_ema_filter) or (r["close"] > r["ema55"])

            if ib_prev and ema_ok:
                ib_low = df["low"].iloc[i-1]
                sl_with_buffer = ib_low - atr * SL_BUFFER_ATR_MULT if atr > 0 else ib_low * 0.98
                risk_per_unit = px - sl_with_buffer

                if risk_per_unit > 0:
                    # Fixed fractional risk sizing
                    risk_amount = cash * RISK_PCT
                    sz = risk_amount / risk_per_unit

                    # Cap position size
                    max_sz = (cash * MAX_POS_PCT) / px
                    if sz > max_sz:
                        sz = max_sz
                        risk_amount = sz * risk_per_unit

                    # Minimum position check
                    entry_cost = sz * px * (1 + TOTAL_COMM)
                    if sz * px >= 10 and entry_cost <= cash:
                        cash -= entry_cost
                        in_pos = True
                        entry = px * (1 + SLIPPAGE_PCT)  # Entry slippage
                        ts_in = ts
                        bar_in = i
                        sl_price = sl_with_buffer

    if in_pos:
        exit_px = px * (1 - SLIPPAGE_PCT)
        pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                           (exit_px/entry-1)*100, risk_amount/INITIAL_CASH*100, "END_OF_DATA", i - bar_in))

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

    # Fee impact
    total_fees = sum(t.sz * (t.p_in + t.p_out) * TAKER_FEE * 2 for t in trades)
    fee_pct = total_fees / abs(total_pnl) * 100 if total_pnl != 0 else 0

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
        "fee_pct": round(fee_pct, 1),
        "exit_reasons": exit_reasons,
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    print(f"\n{'='*100}")
    print(f"  PRODUCTION-READY BACKTEST - Inside Bar Strategy")
    print(f"  Risk: 1.5% fixed | Fees: 0.12% round-trip | SL: IB Low - ATR×0.5")
    print(f"  Coins: {len(files)}")
    print(f"{'='*100}")

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        df = load_and_prepare(fpath)
        if len(df) < 100:
            continue

        # Variant A: No EMA filter
        trades_a, eq_a = run_production_backtest(df, coin, "Prod_NoEMA", use_ema_filter=False)
        r_a = analyze(trades_a, eq_a, "Prod_NoEMA", coin)

        # Variant B: EMA55 filter
        trades_b, eq_b = run_production_backtest(df, coin, "Prod_EMA55", use_ema_filter=True)
        r_b = analyze(trades_b, eq_b, "Prod_EMA55", coin)

        if r_a:
            all_results[coin] = {"Prod_NoEMA": r_a, "Prod_EMA55": r_b}

    # Summary
    print(f"\n{'='*110}")
    print(f"  RESULTS")
    print(f"{'='*110}")
    print(f"  {'Coin':<12} {'Variant':<14} {'Trades':>6} {'WR%':>5} {'PF':>5} {'PnL$':>9} {'Fees$':>7} {'DD%':>5} {'Sharpe':>6}")
    print(f"  {'-'*85}")

    for coin in sorted(all_results.keys()):
        for vname in ["Prod_NoEMA", "Prod_EMA55"]:
            if vname in all_results[coin]:
                r = all_results[coin][vname]
                pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
                print(f"  {coin:<12} {vname:<14} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>5} ${r['total_pnl']:>8.0f} ${r['total_fees']:>6.0f} {r['max_dd']:>4.0f}% {r['sharpe']:>6.2f}")

    # Viable combos
    print(f"\n{'='*110}")
    print(f"  VIABLE COMBOS (PF>1.2, MaxDD<15%, Trades>20, Fees<50% of PnL)")
    print(f"{'='*110}")
    viable = []
    for coin in all_results:
        for vname in ["Prod_NoEMA", "Prod_EMA55"]:
            if vname in all_results[coin]:
                r = all_results[coin][vname]
                pf_val = r["profit_factor"] if isinstance(r["profit_factor"], (int, float)) else 999
                fee_ok = r["fee_pct"] < 50 if r["total_pnl"] > 0 else True
                if pf_val > 1.2 and r["max_dd"] < 15 and r["trades"] > 20 and fee_ok:
                    viable.append((coin, vname, r))
    viable.sort(key=lambda x: x[2]["sharpe"], reverse=True)

    for i, (coin, vname, r) in enumerate(viable[:10]):
        pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
        print(f"  {i+1:>2}. {coin:<10} {vname:<14} Trades={r['trades']:>3} WR={r['win_rate']:.0f}% PF={pf_s} PnL=${r['total_pnl']:.0f} Fees=${r['total_fees']:.0f} DD={r['max_dd']:.0f}% Sharpe={r['sharpe']:.2f}")

    # Top 3 detail
    if viable:
        print(f"\n{'='*110}")
        print(f"  TOP 3 DETAILED ANALYSIS")
        print(f"{'='*110}")
        for i, (coin, vname, r) in enumerate(viable[:3]):
            print(f"\n  [{i+1}] {coin} - {vname}")
            print(f"  Trades: {r['trades']}, WR: {r['win_rate']}%, PF: {r['profit_factor']}")
            print(f"  Total PnL: ${r['total_pnl']:.0f}, Fees: ${r['total_fees']:.0f} ({r['fee_pct']:.1f}% of PnL)")
            print(f"  Max DD: {r['max_dd']}%, Sharpe: {r['sharpe']}")
            print(f"  Exit Reasons:")
            for reason, data in sorted(r["exit_reasons"].items(), key=lambda x: -x[1]["pnl"]):
                r_wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
                print(f"    {reason:<15} Count={data['count']:>3} WR={r_wr:>3.0f}% PnL=${data['pnl']:>8.0f} Avg=${data['pnl']/data['count']:>7.0f}")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
