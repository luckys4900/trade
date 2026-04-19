# -*- coding: utf-8 -*-
"""
Anomaly Analysis: AR Inside Bar - November 2025
================================================
2025-11月の+$2,493が異常値かどうかを検証
この部分を除外しても戦略として成立するか分析
"""

import os, numpy as np, pandas as pd

INITIAL_CASH = 10000.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.25


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
    df["atr14"] = compute_atr(df, 14)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    df["long"] = df["inside_bar"].shift(1) & (df["close"] > df["high"].shift(2)) & (df["close"] > df["ema55"])
    df["exit"] = df["close"] < df["low"].rolling(10).min().shift(1)
    return df


def run_backtest_detail(df, max_hold=10):
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
    stop = 0
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
                trades.append({"t_in": ts_in, "t_out": ts, "entry": entry, "exit": px, "sz": sz,
                               "pnl": pnl, "pnl_pct": (px/entry-1)*100, "reason": "DD_HALT", "bars": i - bar_in})
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
            elif r.get("exit", False):
                exit_now = True
                reason = "SIGNAL_EXIT"

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append({"t_in": ts_in, "t_out": ts, "entry": entry, "exit": exit_px, "sz": sz,
                               "pnl": pnl, "pnl_pct": (exit_px/entry-1)*100, "reason": reason, "bars": held})
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            if r.get("long", False):
                risk = cash * RISK_PCT
                sz = (cash * MAX_POS_PCT) / px
                if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                    cash -= sz * px * (1 + cm)
                    in_pos = True
                    entry = px
                    ts_in = ts
                    bar_in = i
                    stop = px - px * 0.05

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append({"t_in": ts_in, "t_out": ts, "entry": entry, "exit": px, "sz": sz,
                       "pnl": pnl, "pnl_pct": (px/entry-1)*100, "reason": "END_OF_DATA", "bars": i - bar_in})

    return trades, eq


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    ar_path = os.path.join(data_dir, "AR_USDCUSDC_4h_365d.csv")
    df = load_and_prepare(ar_path)
    trades, eq = run_backtest_detail(df, max_hold=10)

    print("="*80)
    print("  AR Inside Bar Breakout - 全取引明細")
    print("="*80)
    print(f"  {'#':>3} {'エントリー日時':<18} {'決済日時':<18} {'Entry':>10} {'Exit':>10} {'PnL$':>10} {'PnL%':>7} {'理由':<15} {'Bars':>4}")
    print("-"*100)

    for i, t in enumerate(trades):
        month = t["t_in"][:7]
        nov_flag = " <<< NOV" if month == "2025-11" else ""
        print(f"  {i+1:>3} {t['t_in'][:16]:<18} {t['t_out'][:16]:<18} {t['entry']:>10.2f} {t['exit']:>10.2f} ${t['pnl']:>9.0f} {t['pnl_pct']:>6.1f}% {t['reason']:<15} {t['bars']:>4}{nov_flag}")

    # November 2025 analysis
    nov_trades = [t for t in trades if t["t_in"][:7] == "2025-11"]
    non_nov_trades = [t for t in trades if t["t_in"][:7] != "2025-11"]

    nov_pnl = sum(t["pnl"] for t in nov_trades)
    non_nov_pnl = sum(t["pnl"] for t in non_nov_trades)

    print(f"\n{'='*80}")
    print("  2025-11月 取引詳細")
    print(f"{'='*80}")
    for i, t in enumerate(nov_trades):
        print(f"  取引 {i+1}: Entry={t['entry']:.2f}, Exit={t['exit']:.2f}, PnL=${t['pnl']:.0f} ({t['pnl_pct']:.1f}%), Reason={t['reason']}, Bars={t['bars']}")

    # Non-November analysis
    print(f"\n{'='*80}")
    print("  2025-11月 EXCLUDED 分析（再現性検証）")
    print(f"{'='*80}")

    non_nov_wins = [t for t in non_nov_trades if t["pnl"] > 0]
    non_nov_losses = [t for t in non_nov_trades if t["pnl"] <= 0]
    non_nov_wr = len(non_nov_wins) / len(non_nov_trades) * 100 if non_nov_trades else 0
    non_nov_avg_win = np.mean([t["pnl"] for t in non_nov_wins]) if non_nov_wins else 0
    non_nov_avg_loss = np.mean([t["pnl"] for t in non_nov_losses]) if non_nov_losses else 0
    non_nov_win_total = sum(t["pnl"] for t in non_nov_wins)
    non_nov_loss_total = sum(t["pnl"] for t in non_nov_losses)
    non_nov_pf = abs(non_nov_win_total / non_nov_loss_total) if non_nov_loss_total != 0 else float('inf')
    non_nov_avg_trade = non_nov_pnl / len(non_nov_trades) if non_nov_trades else 0
    non_nov_ev_pct = non_nov_avg_trade / INITIAL_CASH * 100

    print(f"  トレード数:        {len(non_nov_trades)} (全{len(trades)}件中 -{len(nov_trades)}件)")
    print(f"  勝率:              {non_nov_wr:.1f}% ({len(non_nov_wins)}勝 / {len(non_nov_losses)}敗)")
    print(f"  平均利益:          ${non_nov_avg_win:+.2f}")
    print(f"  平均損失:          ${non_nov_avg_loss:+.2f}")
    print(f"  利益合計:          ${non_nov_win_total:+.2f}")
    print(f"  損失合計:          ${non_nov_loss_total:+.2f}")
    print(f"  Profit Factor:     {non_nov_pf:.2f}")
    print(f"  総PnL:             ${non_nov_pnl:+.2f} ({non_nov_pnl/INITIAL_CASH*100:+.1f}%)")
    print(f"  期待値/トレード:   ${non_nov_avg_trade:.2f} ({non_nov_ev_pct:+.2f}%)")

    # Monthly breakdown excluding November
    print(f"\n  月別パフォーマンス (11月除外)")
    print(f"  {'月':<10} {'件数':>4} {'勝':>3} {'敗':>3} {'勝率':>5} {'PnL':>10} {'累積PnL':>10}")
    print(f"  {'-'*60}")
    monthly = {}
    for t in non_nov_trades:
        month = t["t_in"][:7]
        if month not in monthly:
            monthly[month] = {"wins": 0, "losses": 0, "pnl": 0, "trades": 0}
        monthly[month]["trades"] += 1
        monthly[month]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            monthly[month]["wins"] += 1
        else:
            monthly[month]["losses"] += 1

    cum_pnl = 0
    for m in sorted(monthly.keys()):
        d = monthly[m]
        m_wr = d["wins"]/d["trades"]*100 if d["trades"] > 0 else 0
        cum_pnl += d["pnl"]
        print(f"  {m:<10} {d['trades']:>4} {d['wins']:>3} {d['losses']:>3} {m_wr:>4.0f}% ${d['pnl']:>9.0f} ${cum_pnl:>9.0f}")

    # Plus months count
    plus_months = sum(1 for d in monthly.values() if d["pnl"] > 0)
    total_months = len(monthly)
    print(f"\n  プラス月数: {plus_months}/{total_months} ({plus_months/total_months*100:.0f}%)")

    # Compare with/without November
    all_wins = [t for t in trades if t["pnl"] > 0]
    all_losses = [t for t in trades if t["pnl"] <= 0]
    all_wr = len(all_wins) / len(trades) * 100
    all_avg_win = np.mean([t["pnl"] for t in all_wins])
    all_avg_loss = np.mean([t["pnl"] for t in all_losses]) if all_losses else 0
    all_pf = abs(sum(t["pnl"] for t in all_wins) / sum(t["pnl"] for t in all_losses)) if all_losses and sum(t["pnl"] for t in all_losses) != 0 else float('inf')

    print(f"\n{'='*80}")
    print("  比較: 全期間 vs 11月除外")
    print(f"{'='*80}")
    print(f"  {'指標':<20} {'全期間':>15} {'11月除外':>15} {'判定':<10}")
    print(f"  {'-'*65}")

    def check(val_all, val_excl, higher_better=True, threshold=None):
        if higher_better:
            ok = val_excl >= (threshold if threshold else val_all * 0.7)
        else:
            ok = val_excl <= (threshold if threshold else val_all * 1.3)
        return "PASS" if ok else "WARN"

    print(f"  {'トレード数':<20} {len(trades):>15} {len(non_nov_trades):>15} {'':<10}")
    print(f"  {'勝率':<20} {all_wr:>14.1f}% {non_nov_wr:>14.1f}% {check(all_wr, non_nov_wr):<10}")
    print(f"  {'Profit Factor':<20} {all_pf:>15.2f} {non_nov_pf:>15.2f} {check(all_pf, non_nov_pf):<10}")
    print(f"  {'期待値/トレード':<16} ${sum(t['pnl'] for t in trades)/len(trades):>13.2f} ${non_nov_avg_trade:>13.2f} {check(sum(t['pnl'] for t in trades)/len(trades), non_nov_avg_trade):<10}")
    print(f"  {'総PnL':<20} ${sum(t['pnl'] for t in trades):>14.0f} ${non_nov_pnl:>14.0f} {'':<10}")

    # November context: what was AR price doing?
    print(f"\n{'='*80}")
    print("  2025-11月の市場環境分析")
    print(f"{'='*80}")
    nov_data = df[df.index.month == 11]
    if len(nov_data) == 0:
        nov_data = df[(df.index >= '2025-11-01') & (df.index < '2025-12-01')]
    if len(nov_data) > 0:
        nov_open = nov_data["open"].iloc[0]
        nov_close = nov_data["close"].iloc[-1]
        nov_high = nov_data["high"].max()
        nov_low = nov_data["low"].min()
        nov_change = (nov_close - nov_open) / nov_open * 100
        nov_avg_atr = nov_data["atr14"].mean()
        nov_avg_vol = nov_data["volume"].mean()

        print(f"  始値: ${nov_open:.2f}")
        print(f"  終値: ${nov_close:.2f}")
        print(f"  高値: ${nov_high:.2f}")
        print(f"  安値: ${nov_low:.2f}")
        print(f"  月間変動率: {nov_change:+.1f}%")
        print(f"  平均ATR: ${nov_avg_atr:.2f}")
        print(f"  平均出来高: {nov_avg_vol:.0f}")

        # Compare with other months
        all_months = df.index.to_period("M").unique()
        monthly_changes = []
        for m in all_months:
            m_data = df[df.index.to_period("M") == m]
            if len(m_data) > 0:
                chg = (m_data["close"].iloc[-1] - m_data["open"].iloc[0]) / m_data["open"].iloc[0] * 100
                monthly_changes.append({"month": str(m), "change": chg})

        print(f"\n  全月の変動率:")
        for mc in monthly_changes:
            flag = " <<< NOV" if mc["month"] == "2025-11" else ""
            print(f"    {mc['month']}: {mc['change']:+.1f}%{flag}")

    # Verdict
    print(f"\n{'='*80}")
    print("  総合判定")
    print(f"{'='*80}")
    if non_nov_pf > 1.5 and non_nov_wr > 50 and non_nov_pnl > 0:
        print("  => 11月を除外しても戦略はVALID（PF>1.5, WR>50%, PnL>0）")
        print("     11月の利益は『異常値』ではなく『トレンド環境での正常な成果』")
    elif non_nov_pf > 1.2 and non_nov_wr > 45 and non_nov_pnl > 0:
        print("  => 11月を除外しても戦略はMARGINALLY VALID")
        print("     ただしPF・WRが低下。環境依存性を考慮すべき")
    else:
        print("  => 11月の利益に戦略の大部分が依存。再現性に疑問")

    # Exit reason analysis excluding November
    print(f"\n{'='*80}")
    print("  決済理由別分析 (11月除外)")
    print(f"{'='*80}")
    exit_reasons = {}
    for t in non_nov_trades:
        if t["reason"] not in exit_reasons:
            exit_reasons[t["reason"]] = {"count": 0, "pnl": 0, "wins": 0}
        exit_reasons[t["reason"]]["count"] += 1
        exit_reasons[t["reason"]]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            exit_reasons[t["reason"]]["wins"] += 1

    print(f"  {'理由':<20} {'件数':>4} {'勝率':>5} {'PnL合計':>10} {'平均PnL':>10}")
    print(f"  {'-'*55}")
    for reason, data in sorted(exit_reasons.items(), key=lambda x: -x[1]["pnl"]):
        r_wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
        avg = data["pnl"]/data["count"]
        print(f"  {reason:<20} {data['count']:>4} {r_wr:>4.0f}% ${data['pnl']:>9.0f} ${avg:>9.2f}")


if __name__ == "__main__":
    main()
