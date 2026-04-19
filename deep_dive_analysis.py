# -*- coding: utf-8 -*-
"""
Deep Dive Analysis - Top 3 Strategies
=======================================
プロトレーダー目線での戦略精査
1. Inside Bar Breakout (Al Brooks) on AR
2. VWAP Confluence (Institutional) on AIXBT
3. BB Squeeze Breakout (John Bollinger) on ACE

分析内容:
- 月別パフォーマンス（アップ/ダウンマーケットでの挙動）
- 連続勝敗・ドローダウン分析
- 平均保有期間 vs 利益率
- エントリー価格帯別分析
- 期待値の構成要素分解
"""

import os, json, numpy as np, pandas as pd
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


def compute_vwap(df, period):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).rolling(period).sum() / df["volume"].rolling(period).sum()


def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    return (entry - exit_px) * sz - notional * comm


def run_backtest_detail(df, long_col, exit_col, use_atr_sl=False, atr_sl_mult=0, max_hold=999):
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
                trades.append(Trade(ts_in, ts, "LONG", "STRAT", entry, px, sz, pnl,
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
            elif use_atr_sl and atr and atr > 0:
                new_sl = px - atr_sl_mult * atr
                if new_sl > stop:
                    stop = new_sl
                if lo <= stop:
                    exit_now = True
                    reason = "TRAILING_STOP"
                    exit_px = stop
            elif r.get(exit_col, False):
                exit_now = True
                reason = "SIGNAL_EXIT"

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", "STRAT", entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until:
            if r.get(long_col, False):
                risk = cash * RISK_PCT
                if use_atr_sl and atr and atr > 0:
                    sl_d = atr_sl_mult * atr
                    sz = min(risk / sl_d, (cash * MAX_POS_PCT) / px)
                else:
                    sz = (cash * MAX_POS_PCT) / px
                if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                    cash -= sz * px * (1 + cm)
                    in_pos = True
                    entry = px
                    ts_in = ts
                    bar_in = i
                    stop = px - (atr_sl_mult * atr if use_atr_sl and atr else px * 0.05)

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", "STRAT", entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


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

    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["high_25"] = df["high"].rolling(25).max()
    df["low_10"] = df["low"].rolling(10).min()
    df["bb_mid"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2.0 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2.0 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    df["vwap"] = compute_vwap(df, 20)

    # Connors RSI components
    streak = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] + 1 if streak.iloc[i-1] > 0 else 1
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] - 1 if streak.iloc[i-1] < 0 else -1
    rsi_streak = compute_rsi(streak, 2)
    roc = df["close"].pct_change(100) * 100
    roc_pct = roc.rolling(100).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False)
    df["connors_rsi"] = (compute_rsi(df["close"], 3) + rsi_streak + roc_pct) / 3

    return df


def generate_signals_ar_inside_bar(df):
    """AR Inside Bar Breakout - Al Brooks"""
    df["long"] = df["inside_bar"].shift(1) & (df["close"] > df["high"].shift(2)) & (df["close"] > df["ema55"])
    df["exit"] = df["close"] < df["low"].rolling(10).min().shift(1)
    return df


def generate_signals_aixbt_vwap(df):
    """AIXBT VWAP Confluence"""
    df["long"] = (
        (df["close"] > df["vwap"]) &
        (df["rsi14"] > 40) &
        (df["rsi14"].shift(1) <= 40)
    )
    df["exit"] = df["rsi14"] > 60
    return df


def generate_signals_ace_bb(df):
    """ACE BB Squeeze Breakout"""
    squeeze = df["bb_width"] < df["bb_width"].rolling(50).quantile(0.10)
    df["long"] = squeeze & (df["close"] > df["bb_upper"].shift(1))
    df["exit"] = df["close"] < df["bb_mid"]
    return df


def analyze_deep(trades, df, coin_name, strat_name):
    """Deep analysis of trades"""
    if not trades:
        print("  No trades")
        return

    # Basic stats
    pnls = [t.pnl for t in trades]
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins) / len(trades) * 100
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
    total_pnl = sum(pnls)
    win_total = sum(t.pnl for t in wins)
    loss_total = sum(t.pnl for t in losses)
    pf = abs(win_total / loss_total) if loss_total != 0 else float('inf')

    # Expectancy breakdown
    avg_trade = total_pnl / len(trades)
    expectancy_pct = avg_trade / INITIAL_CASH * 100

    # Monthly performance
    monthly = {}
    for t in trades:
        month = t.t_in[:7]  # YYYY-MM
        if month not in monthly:
            monthly[month] = {"wins": 0, "losses": 0, "pnl": 0, "trades": 0}
        monthly[month]["trades"] += 1
        monthly[month]["pnl"] += t.pnl
        if t.pnl > 0:
            monthly[month]["wins"] += 1
        else:
            monthly[month]["losses"] += 1

    # Market regime analysis
    up_months = 0
    down_months = 0
    up_pnl = 0
    down_pnl = 0
    for m, data in sorted(monthly.items()):
        # Determine market direction by price change
        pass

    # Consecutive analysis
    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0
    for t in trades:
        if t.pnl > 0:
            cur_win += 1
            cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        if t.reason not in exit_reasons:
            exit_reasons[t.reason] = {"count": 0, "pnl": 0, "wins": 0}
        exit_reasons[t.reason]["count"] += 1
        exit_reasons[t.reason]["pnl"] += t.pnl
        if t.pnl > 0:
            exit_reasons[t.reason]["wins"] += 1

    # Hold time analysis
    hold_times = [t.bars for t in trades]
    avg_hold = np.mean(hold_times)
    win_avg_hold = np.mean([t.bars for t in wins]) if wins else 0
    loss_avg_hold = np.mean([t.bars for t in losses]) if losses else 0

    # Print deep analysis
    print(f"\n{'='*70}")
    print(f"  DEEP ANALYSIS: {coin_name} - {strat_name}")
    print(f"{'='*70}")

    print(f"\n  [1] 基本統計")
    print(f"  総トレード数:     {len(trades)}")
    print(f"  勝率:             {wr:.1f}% ({len(wins)}勝 / {len(losses)}敗)")
    print(f"  平均利益:         ${avg_win:+.2f} ({avg_win/INITIAL_CASH*100:+.2f}%)")
    print(f"  平均損失:         ${avg_loss:+.2f} ({avg_loss/INITIAL_CASH*100:+.2f}%)")
    print(f"  利益合計:         ${win_total:+.2f}")
    print(f"  損失合計:         ${loss_total:+.2f}")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"  期待値(1トレード): ${avg_trade:.2f} ({expectancy_pct:+.2f}%)")

    print(f"\n  [2] 期待値の構成要素分解")
    print(f"  期待値 = (勝率 × 平均利益) - (敗率 × 平均損失)")
    print(f"         = ({wr/100:.3f} × ${avg_win:.2f}) - ({1-wr/100:.3f} × ${abs(avg_loss):.2f})")
    ev = (wr/100 * avg_win) - ((1-wr/100) * abs(avg_loss))
    print(f"         = ${ev:.2f} per trade")
    print(f"  損益レシオ:       {abs(avg_win/avg_loss):.2f}:1" if avg_loss != 0 else "  損益レシオ: N/A")
    print(f"  必要勝率(PF=1):   {1/(1+abs(avg_win/avg_loss))*100:.1f}%" if avg_loss != 0 else "  必要勝率: N/A")

    print(f"\n  [3] 月別パフォーマンス")
    print(f"  {'月':<10} {'件数':>4} {'勝':>3} {'敗':>3} {'勝率':>5} {'PnL':>10} {'累積PnL':>10}")
    print(f"  {'-'*50}")
    cum_pnl = 0
    for m in sorted(monthly.keys()):
        d = monthly[m]
        m_wr = d["wins"]/d["trades"]*100 if d["trades"] > 0 else 0
        cum_pnl += d["pnl"]
        print(f"  {m:<10} {d['trades']:>4} {d['wins']:>3} {d['losses']:>3} {m_wr:>4.0f}% ${d['pnl']:>9.0f} ${cum_pnl:>9.0f}")

    print(f"\n  [4] 連続勝敗分析")
    print(f"  最大連勝: {max_win_streak}")
    print(f"  最大連敗: {max_loss_streak}")

    print(f"\n  [5] 決済理由別分析")
    print(f"  {'理由':<20} {'件数':>4} {'勝率':>5} {'PnL合計':>10} {'平均PnL':>10}")
    print(f"  {'-'*55}")
    for reason, data in sorted(exit_reasons.items(), key=lambda x: -x[1]["pnl"]):
        r_wr = data["wins"]/data["count"]*100 if data["count"] > 0 else 0
        avg = data["pnl"]/data["count"]
        print(f"  {reason:<20} {data['count']:>4} {r_wr:>4.0f}% ${data['pnl']:>9.0f} ${avg:>9.2f}")

    print(f"\n  [6] 保有期間分析")
    print(f"  平均保有期間:     {avg_hold:.1f} バー")
    print(f"  勝ちトレード平均: {win_avg_hold:.1f} バー")
    print(f"  負けトレード平均: {loss_avg_hold:.1f} バー")
    if win_avg_hold > 0 and loss_avg_hold > 0:
        if win_avg_hold > loss_avg_hold:
            print(f"  => 勝ちの方が長く保有（トレンドフォロー型）")
        else:
            print(f"  => 負けの方が長く保有（ホープ型、要改善）")

    print(f"\n{'='*70}")

    return {
        "coin": coin_name,
        "strategy": strat_name,
        "trades": len(trades),
        "win_rate": wr,
        "profit_factor": pf,
        "expectancy": ev,
        "total_pnl": total_pnl,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_hold": avg_hold,
        "win_avg_hold": win_avg_hold,
        "loss_avg_hold": loss_avg_hold,
        "monthly": monthly,
        "exit_reasons": exit_reasons,
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    # Strategy 1: AR Inside Bar
    print("\n" + "#"*60)
    print("  STRATEGY 1: AR Inside Bar Breakout (Al Brooks)")
    print("#"*60)
    ar_path = os.path.join(data_dir, "AR_USDCUSDC_4h_365d.csv")
    df_ar = load_and_prepare(ar_path)
    df_ar = generate_signals_ar_inside_bar(df_ar)
    trades_ar, eq_ar = run_backtest_detail(df_ar, "long", "exit", max_hold=10)
    analyze_deep(trades_ar, df_ar, "AR", "Inside Bar Breakout (Al Brooks)")

    # Strategy 2: AIXBT VWAP Confluence
    print("\n" + "#"*60)
    print("  STRATEGY 2: AIXBT VWAP Confluence (Institutional)")
    print("#"*60)
    aixbt_path = os.path.join(data_dir, "AIXBT_USDCUSDC_4h_365d.csv")
    df_aixbt = load_and_prepare(aixbt_path)
    df_aixbt = generate_signals_aixbt_vwap(df_aixbt)
    trades_aixbt, eq_aixbt = run_backtest_detail(df_aixbt, "long", "exit", max_hold=15)
    analyze_deep(trades_aixbt, df_aixbt, "AIXBT", "VWAP Confluence (Institutional)")

    # Strategy 3: ACE BB Squeeze
    print("\n" + "#"*60)
    print("  STRATEGY 3: ACE BB Squeeze Breakout (John Bollinger)")
    print("#"*60)
    ace_path = os.path.join(data_dir, "ACE_USDCUSDC_4h_365d.csv")
    df_ace = load_and_prepare(ace_path)
    df_ace = generate_signals_ace_bb(df_ace)
    trades_ace, eq_ace = run_backtest_detail(df_ace, "long", "exit", max_hold=20)
    analyze_deep(trades_ace, df_ace, "ACE", "BB Squeeze Breakout (Bollinger)")


if __name__ == "__main__":
    main()
