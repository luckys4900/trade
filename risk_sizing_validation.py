# -*- coding: utf-8 -*-
"""
Risk Sizing Validation - Inside Bar Strategy
=============================================
「リスク不均一（IB安値が近いほど大きく張る）」はバグか戦略か？
"""

import os, glob, numpy as np, pandas as pd
from dataclasses import dataclass

INITIAL_CASH = 211.0
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.20

TAKER_FEE = 0.0005
SLIPPAGE_PCT = 0.0002
TOTAL_COMM = TAKER_FEE * 2 + SLIPPAGE_PCT

SL_BUFFER_ATR_MULT = 0.5
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
    risk_dollar: float  # 実際のドルリスク
    risk_pct: float     # 資金に対するリスク%
    sl_distance_pct: float  # SLまでの距離%
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
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    return df


def run_backtest_sizing(df, coin_name, variant_name, sizing_mode, use_ema_filter=False):
    """
    sizing_mode:
      "fixed_pct"     - 資金40%固定（前版バグ版）
      "fixed_risk"    - リスク1.5%固定（本番版）
      "inverse_sl"    - SL距離に反比例（狭いほど大きく）- 最適化版
      "kelly"         - ケリー基準ベース
    """
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
    loss_count = 0
    cool_until = 0
    risk_amount = 0

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
                exit_px = px * (1 - SLIPPAGE_PCT)
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, risk_amount, risk_amount/INITIAL_CASH*100, 0, "DD_HALT", i - bar_in))
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
                exit_px = sl_price * (1 - SLIPPAGE_PCT)

            if exit_now:
                pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
                cash += sz * entry + pnl
                actual_sl_dist = abs(entry - sl_price) / entry * 100
                actual_risk = sz * abs(entry - sl_price)
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, actual_risk, actual_risk/INITIAL_CASH*100, actual_sl_dist, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            ib_prev = df["inside_bar"].iloc[i-1] if i > 0 else False
            ema_ok = (not use_ema_filter) or (r["close"] > r["ema55"])

            if ib_prev and ema_ok:
                ib_low = df["low"].iloc[i-1]
                sl_with_buffer = ib_low - atr * SL_BUFFER_ATR_MULT if atr > 0 else ib_low * 0.98
                sl_distance_pct = (px - sl_with_buffer) / px
                risk_per_unit = px - sl_with_buffer

                if risk_per_unit > 0 and sl_distance_pct > 0:
                    if sizing_mode == "fixed_pct":
                        # 前版: 常に資金40%
                        sz = (cash * MAX_POS_PCT) / px
                        risk_amount = sz * risk_per_unit

                    elif sizing_mode == "fixed_risk":
                        # 本番版: リスク1.5%固定
                        risk_amount = cash * 0.015
                        sz = risk_amount / risk_per_unit
                        max_sz = (cash * MAX_POS_PCT) / px
                        if sz > max_sz:
                            sz = max_sz
                            risk_amount = sz * risk_per_unit

                    elif sizing_mode == "inverse_sl":
                        # SL距離に反比例: 狭いほど大きく（ただし上限40%）
                        # 基準: SL距離2%のとき資金10%、SL距離1%のとき資金20%
                        base_sl = 0.02  # 2%
                        base_pos = 0.10  # 10%
                        sz = (base_pos / sl_distance_pct * base_sl) * cash / px
                        sz = min(sz, (cash * MAX_POS_PCT) / px)
                        risk_amount = sz * risk_per_unit

                    elif sizing_mode == "kelly":
                        # 簡易ケリー: 過去勝率ベース
                        # 簡易化: 固定10%
                        sz = (cash * 0.10) / px
                        risk_amount = sz * risk_per_unit

                    entry_cost = sz * px * (1 + TOTAL_COMM)
                    if sz * px >= 10 and entry_cost <= cash:
                        cash -= entry_cost
                        in_pos = True
                        entry = px * (1 + SLIPPAGE_PCT)
                        ts_in = ts
                        bar_in = i
                        sl_price = sl_with_buffer

    if in_pos:
        exit_px = px * (1 - SLIPPAGE_PCT)
        pnl = _pnl_with_fees("LONG", entry, exit_px, sz, TOTAL_COMM)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                           (exit_px/entry-1)*100, risk_amount, risk_amount/INITIAL_CASH*100, 0, "END_OF_DATA", i - bar_in))

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

    # SL距離と勝率の相関
    sl_dists = [t.sl_distance_pct for t in trades if t.sl_distance_pct > 0]
    pnl_signs = [1 if t.pnl > 0 else 0 for t in trades if t.sl_distance_pct > 0]
    if len(sl_dists) > 5:
        corr = np.corrcoef(sl_dists, pnl_signs)[0, 1]
    else:
        corr = 0

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
        "corr_sl_wr": round(corr, 3),
        "exit_reasons": exit_reasons,
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    sizing_modes = ["fixed_pct", "fixed_risk", "inverse_sl", "kelly"]
    mode_labels = {
        "fixed_pct": "Fixed40%",
        "fixed_risk": "Risk1.5%",
        "inverse_sl": "InverseSL",
        "kelly": "Kelly10%"
    }

    print(f"\n{'='*120}")
    print(f"  RISK SIZING VALIDATION - Inside Bar Strategy")
    print(f"  Modes: Fixed40% | Risk1.5% | InverseSL | Kelly10%")
    print(f"  Coins: {len(files)}")
    print(f"{'='*120}")

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        df = load_and_prepare(fpath)
        if len(df) < 100:
            continue

        coin_results = {}
        for mode in sizing_modes:
            trades, eq = run_backtest_sizing(df, coin, mode, sizing_mode=mode, use_ema_filter=False)
            r = analyze(trades, eq, mode, coin)
            if r:
                coin_results[mode] = r

        all_results[coin] = coin_results

    # Summary per coin
    print(f"\n{'='*130}")
    print(f"  PER-COIN COMPARISON")
    print(f"{'='*130}")
    print(f"  {'Coin':<12} {'Mode':<12} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>8} {'Fees$':>6} {'DD%':>5} {'Sharpe':>6} {'Corr(SL-WR)':>10}")
    print(f"  {'-'*95}")

    for coin in sorted(all_results.keys()):
        for mode in sizing_modes:
            if mode in all_results[coin]:
                r = all_results[coin][mode]
                pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
                print(f"  {coin:<12} {mode_labels[mode]:<12} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>6} ${r['total_pnl']:>7.0f} ${r['total_fees']:>5.0f} {r['max_dd']:>4.0f}% {r['sharpe']:>6.2f} {r['corr_sl_wr']:>10.3f}")

    # Best mode per coin
    print(f"\n{'='*130}")
    print(f"  BEST MODE PER COIN (by Sharpe, min 20 trades)")
    print(f"{'='*130}")
    print(f"  {'Coin':<12} {'Best Mode':<12} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>8} {'DD%':>5} {'Sharpe':>6}")
    print(f"  {'-'*75}")
    for coin in sorted(all_results.keys()):
        best_mode = None
        best_sharpe = -999
        for mode in sizing_modes:
            if mode in all_results[coin]:
                r = all_results[coin][mode]
                if r["sharpe"] > best_sharpe and r["trades"] >= 20:
                    best_sharpe = r["sharpe"]
                    best_mode = mode
        if best_mode:
            r = all_results[coin][best_mode]
            pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
            print(f"  {coin:<12} {mode_labels[best_mode]:<12} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>6} ${r['total_pnl']:>7.0f} {r['max_dd']:>4.0f}% {r['sharpe']:>6.2f}")

    # Overall mode averages
    print(f"\n{'='*130}")
    print(f"  OVERALL MODE AVERAGES (12 coins)")
    print(f"{'='*130}")
    for mode in sizing_modes:
        vals = [all_results[c][mode] for c in all_results if mode in all_results[c]]
        if vals:
            avg_trades = np.mean([r["trades"] for r in vals])
            avg_wr = np.mean([r["win_rate"] for r in vals])
            avg_pnl = np.mean([r["total_pnl"] for r in vals])
            avg_dd = np.mean([r["max_dd"] for r in vals])
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            pf_vals = [r["profit_factor"] for r in vals if isinstance(r["profit_factor"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0
            corr_vals = [r["corr_sl_wr"] for r in vals]
            avg_corr = np.mean(corr_vals)
            print(f"  {mode_labels[mode]:<12} Trades={avg_trades:.0f}  WR={avg_wr:.0f}%  PF={avg_pf:.2f}  PnL=${avg_pnl:.0f}  DD={avg_dd:.0f}%  Sharpe={avg_sharpe:.2f}  Corr(SL-WR)={avg_corr:.3f}")

    # Viable combos
    print(f"\n{'='*130}")
    print(f"  VIABLE COMBOS (PF>1.2, MaxDD<20%, Trades>20)")
    print(f"{'='*130}")
    viable = []
    for coin in all_results:
        for mode in sizing_modes:
            if mode in all_results[coin]:
                r = all_results[coin][mode]
                pf_val = r["profit_factor"] if isinstance(r["profit_factor"], (int, float)) else 999
                if pf_val > 1.2 and r["max_dd"] < 20 and r["trades"] > 20:
                    viable.append((coin, mode, r))
    viable.sort(key=lambda x: x[2]["sharpe"], reverse=True)
    for i, (coin, mode, r) in enumerate(viable[:10]):
        pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
        print(f"  {i+1:>2}. {coin:<10} {mode_labels[mode]:<12} Trades={r['trades']:>3} WR={r['win_rate']:.0f}% PF={pf_s} PnL=${r['total_pnl']:.0f} DD={r['max_dd']:.0f}% Sharpe={r['sharpe']:.2f}")

    if not viable:
        print("  No combos meet criteria.")

    # Correlation analysis
    print(f"\n{'='*130}")
    print(f"  SL DISTANCE vs WIN RATE CORRELATION ANALYSIS")
    print(f"{'='*130}")
    print(f"  相関が負 = SL距離が短いほど勝率が高い（InverseSLが有効）")
    print(f"  相関が正 = SL距離が長いほど勝率が高い（InverseSLは逆効果）")
    print(f"  {'Coin':<12} {'Correlation':>10} {'Interpretation':<40}")
    print(f"  {'-'*65}")
    for coin in sorted(all_results.keys()):
        if "fixed_risk" in all_results[coin]:
            corr = all_results[coin]["fixed_risk"]["corr_sl_wr"]
            interp = "InverseSL有効" if corr < -0.1 else ("InverseSL逆効果" if corr > 0.1 else "相関なし")
            print(f"  {coin:<12} {corr:>10.3f} {interp:<40}")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
