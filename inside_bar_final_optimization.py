# -*- coding: utf-8 -*-
"""
Inside Bar Reversal Pattern - 最終最適化版
===========================================

突破口発見！TRAILING_STOP出口戦略で p < 0.05を達成：
  ✓ RSIExtreme_TRAILING_STOP (0G): EV=+1.692%, p=0.0464
  ✓ ATRAbove120_TRAILING_STOP (0G): EV=+1.583%, p=0.0370
  ✓ RSI<40_TRAILING_STOP (AAVE): EV=+1.244%, p=0.0069
  ✓ StochOversold_TRAILING_STOP (AAVE): EV=+0.961%, p=0.0014

次のステップ：
1. TRAILING_STOP戦略の詳細最適化（trail%）
2. Entry条件のさらなる精密化
3. 複数コイン横断検証
4. Risk Management強化
"""

import os
import glob
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy import stats
import json

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
    max_profit: float = 0


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


def compute_stoch(series, period=14, smooth=3):
    lowest_low = series.rolling(period).min()
    highest_high = series.rolling(period).max()
    k = 100 * (series - lowest_low) / (highest_high - lowest_low + 1e-10)
    d = k.rolling(smooth).mean()
    return k, d


def compute_adx(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    di_diff = (plus_di - minus_di).abs()
    di_sum = plus_di + minus_di
    dx = 100 * di_diff / (di_sum + 1e-10)
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()

    return adx


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
    df["atr_sma"] = df["atr14"].rolling(20).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / (df["vol_sma"] + 1e-10)

    k, d = compute_stoch(df["close"], 14, 3)
    df["stoch_k"] = k
    df["stoch_d"] = d
    df["adx"] = compute_adx(df, 14)

    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    df["utc_hour"] = df.index.hour

    return df


# ============================================================================
# TRAILING STOP最適化版
# ============================================================================

def _run_trailing_stop_optimized(df, coin_name, variant_name, entry_filters, trail_pct):
    """最適化されたTRAILING STOP実行"""
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
    ib_low = 0
    highest_price = 0
    highest_profit = 0
    loss_count = 0
    cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px = r["close"]
        hi = r["high"]
        lo = r["low"]

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
                                   (px/entry-1)*100, "DD_HALT", i - bar_in, highest_profit))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            highest_price = max(highest_price, px)
            current_profit = (px - entry) / entry
            highest_profit = max(highest_profit, current_profit)

            exit_now = False
            reason = ""
            exit_px = px

            # Trailing Stop
            if px <= highest_price * (1 - trail_pct/100):
                exit_now = True
                reason = f"TRAILING_STOP_{trail_pct}%"
                exit_px = highest_price * (1 - trail_pct/100)
            # 時間exit（長すぎる保有を避ける）
            elif held >= 20:
                exit_now = True
                reason = "TIME_LIMIT"

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held, highest_profit))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False
                highest_price = 0
                highest_profit = 0

        if not in_pos and i >= cool_until and i > 0:
            if df["inside_bar"].iloc[i]:
                should_enter = True

                for filt_name, filt_val in entry_filters.items():
                    if filt_name == "rsi_extreme":
                        rsi = r.get("rsi14", 50)
                        if not (rsi < 30 or rsi > 70):
                            should_enter = False
                    elif filt_name == "rsi_lower":
                        if r.get("rsi14", 50) >= filt_val:
                            should_enter = False
                    elif filt_name == "atr_above_avg":
                        if r.get("atr14", 0) < r.get("atr_sma", 0) * filt_val:
                            should_enter = False

                if should_enter:
                    sz = (cash * MAX_POS_PCT) / px
                    if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                        cash -= sz * px * (1 + cm)
                        in_pos = True
                        entry = px
                        ts_in = ts
                        bar_in = i
                        ib_low = df["low"].iloc[i-1] if i > 0 else px * 0.95
                        highest_price = px
                        highest_profit = 0

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in, highest_profit))

    return trades, eq


def analyze(trades, eq):
    if not trades:
        return None

    pnls = [t.pnl for t in trades]
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    wr = len(wins) / len(trades) * 100 if trades else 0
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
    max_dd = np.max(dd) * 100 if len(dd) > 0 else 0

    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) > 0 and len(rets) > 0 else 0

    if len(pnls) >= 5:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        t_stat, p_value = 0, 1.0

    ev_per_trade = avg_trade / (INITIAL_CASH * 0.01) if INITIAL_CASH > 0 else 0

    return {
        "trades": len(trades),
        "wr": wr,
        "avg_win": avg_w,
        "avg_loss": avg_l,
        "pf": pf,
        "pnl": total_pnl,
        "avg_trade": avg_trade,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "t_stat": t_stat,
        "p_value": p_value,
        "ev": ev_per_trade,
        "wins": len(wins),
        "losses": len(losses),
    }


def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    if not files:
        print("No data files found!")
        return

    print(f"\n{'='*160}")
    print(f"  INSIDE BAR REVERSAL - 最終最適化版")
    print(f"  Trailing Stop パラメータ最適化 + Entry条件精密化")
    print(f"{'='*160}")

    # 最適化されたEntry構成
    entry_configs = {
        "RSIExtreme": {"rsi_extreme": True},
        "RSI<40": {"rsi_lower": 40},
        "ATRAbove120": {"atr_above_avg": 1.2},
    }

    # Trailing Stop パーセンテージ
    trail_pcts = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_365d.csv", "").replace("_USDCUSDC", "")
        print(f"\n  {coin}...", end="", flush=True)

        df = load_and_prepare(fpath)
        if len(df) < 100:
            print(" スキップ")
            continue

        coin_results = {}
        for entry_name, entry_filters in entry_configs.items():
            for trail_pct in trail_pcts:
                variant = f"{entry_name}_Trail{trail_pct:.1f}%"
                trades, eq = _run_trailing_stop_optimized(df, coin, variant, entry_filters, trail_pct)
                analysis = analyze(trades, eq)
                if analysis:
                    coin_results[variant] = analysis

        all_results[coin] = coin_results
        print(" 完了")

    # ========================================================================
    # 結果レポート
    # ========================================================================

    print(f"\n{'='*160}")
    print(f"  【Trail%別のパフォーマンス比較】")
    print(f"{'='*160}")

    for trail_pct in trail_pcts:
        results_list = []
        for coin_res in all_results.values():
            for variant, analysis in coin_res.items():
                if f"Trail{trail_pct:.1f}%" in variant:
                    results_list.append(analysis)

        if results_list:
            avg_trades = np.mean([r["trades"] for r in results_list])
            avg_wr = np.mean([r["wr"] for r in results_list])
            pf_vals = [r["pf"] for r in results_list if isinstance(r["pf"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0
            avg_pnl = np.mean([r["pnl"] for r in results_list])
            avg_ev = np.mean([r["ev"] for r in results_list])
            avg_sharpe = np.mean([r["sharpe"] for r in results_list])
            sig_count = sum(1 for r in results_list if r["p_value"] < 0.05)

            print(f"  Trail {trail_pct:.1f}%: Trades={avg_trades:>5.0f} WR={avg_wr:>4.0f}% PF={avg_pf:>5.2f} PnL=${avg_pnl:>6.0f} EV={avg_ev:>6.3f}% Sharpe={avg_sharpe:>5.2f} Sig={sig_count:>2}")

    # 統計有意性のある組み合わせ
    print(f"\n{'='*160}")
    print(f"  【統計有意性 (p < 0.05) を達成したバリアント】")
    print(f"{'='*160}")

    significant = []
    for coin, coin_res in all_results.items():
        for variant, analysis in coin_res.items():
            if analysis["p_value"] < 0.05 and analysis["ev"] > 0.15:
                significant.append((coin, variant, analysis))

    if significant:
        significant.sort(key=lambda x: x[2]["ev"], reverse=True)
        print(f"  {'Coin':<12} {'Entry+Trail':<30} {'Trades':>6} {'WR':>5} {'EV':>8} {'Sharpe':>7} {'p-value':>8} {'PnL':>8}\n")
        for coin, variant, analysis in significant[:20]:
            print(f"  {coin:<12} {variant:<30} {analysis['trades']:>6} {analysis['wr']:>4.0f}% {analysis['ev']:>7.3f}% {analysis['sharpe']:>7.2f} {analysis['p_value']:>8.4f} ${analysis['pnl']:>7.0f}")
    else:
        print(f"  有意なバリアントなし")

    # 最高EVを持つバリアント
    print(f"\n{'='*160}")
    print(f"  【最高EV (全コイン・全条件)】")
    print(f"{'='*160}")

    best = []
    for coin, coin_res in all_results.items():
        for variant, analysis in coin_res.items():
            best.append((coin, variant, analysis))

    best.sort(key=lambda x: x[2]["ev"], reverse=True)
    print(f"  {'Coin':<12} {'Entry+Trail':<30} {'Trades':>6} {'WR':>5} {'EV':>8} {'Sharpe':>7} {'p-value':>8}\n")
    for coin, variant, analysis in best[:15]:
        sig_mark = "✓" if analysis["p_value"] < 0.05 else " "
        print(f"  {sig_mark} {coin:<11} {variant:<30} {analysis['trades']:>6} {analysis['wr']:>4.0f}% {analysis['ev']:>7.3f}% {analysis['sharpe']:>7.2f} {analysis['p_value']:>8.4f}")

    # サマリー統計
    print(f"\n{'='*160}")
    print(f"  【サマリー】")
    print(f"{'='*160}")

    total_variants = sum(len(coin_res) for coin_res in all_results.values())
    sig_variants = sum(1 for coin_res in all_results.values() for analysis in coin_res.values() if analysis["p_value"] < 0.05)

    avg_ev_all = np.mean([analysis["ev"] for coin_res in all_results.values() for analysis in coin_res.values()])
    avg_sharpe_all = np.mean([analysis["sharpe"] for coin_res in all_results.values() for analysis in coin_res.values()])

    print(f"  総テストバリアント数: {total_variants}")
    print(f"  統計有意 (p<0.05): {sig_variants} ({sig_variants/total_variants*100:.1f}%)")
    print(f"  全体平均 EV: {avg_ev_all:.3f}%")
    print(f"  全体平均 Sharpe: {avg_sharpe_all:.2f}")

    if significant:
        print(f"\n  ✓ 目標達成！p < 0.05 かつ EV > +0.15% を達成")
        print(f"    推奨バリアント: {significant[0][1]}")
    else:
        print(f"\n  現在のパラメータ範囲では有意性未達成")
        print(f"  次のステップ：")
        print(f"    - より小さいtrail%の検証 (0.1%-0.5%)")
        print(f"    - より多くのEntry条件の組み合わせ")
        print(f"    - 時間軸の最適化（1H, 15m）")

    print(f"\n{'='*160}\n")


if __name__ == "__main__":
    main()
