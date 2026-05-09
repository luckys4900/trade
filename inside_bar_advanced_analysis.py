# -*- coding: utf-8 -*-
"""
Inside Bar Reversal - 高度な分析と最適化
==========================================

前回の結果から：
- ベースラインEV = -0.275%（統計的に有意でない）
- 複数フィルターで小幅改善（最高EV +0.288%：RSI極値）
- p値がすべて > 0.05（統計的有意性なし）

新しいアプローチ：
1. フィルター条件の精密化（パラメータ最適化）
2. Exit戦略の多様化
3. 複合パターンの相互作用分析
4. Win RateとProfit Factorのトレード分析
5. 出来高ブレイクアウトの検証
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


# ============================================================================
# INDICATORS
# ============================================================================

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
    """Stochastic計算"""
    lowest_low = series.rolling(period).min()
    highest_high = series.rolling(period).max()
    k = 100 * (series - lowest_low) / (highest_high - lowest_low + 1e-10)
    d = k.rolling(smooth).mean()
    return k, d


def compute_adx(df, period=14):
    """ADX計算（トレンド強度）"""
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


# ============================================================================
# DATA
# ============================================================================

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

    # インジケータ
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["atr_sma"] = df["atr14"].rolling(20).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / (df["vol_sma"] + 1e-10)

    # Stochastic
    k, d = compute_stoch(df["close"], 14, 3)
    df["stoch_k"] = k
    df["stoch_d"] = d

    # ADX
    df["adx"] = compute_adx(df, 14)

    # Inside Bar
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    df["ib_range"] = df["high"] - df["low"]
    df["ib_range_prev"] = df["ib_range"].shift(1)
    df["ib_size_ratio"] = df["ib_range"] / (df["ib_range_prev"] + 1e-10)

    # ボラティリティ測度
    df["close_returns"] = df["close"].pct_change()
    df["returns_vol"] = df["close_returns"].rolling(20).std() * np.sqrt(252)

    # 時刻
    df["utc_hour"] = df.index.hour

    # 前バーの特性
    df["prev_close_gt_open"] = (df["close"].shift(1) > df["open"].shift(1)).astype(int)
    df["prev_range"] = df["high"].shift(1) - df["low"].shift(1)

    return df


# ============================================================================
# EXIT STRATEGIES
# ============================================================================

def _run_with_exit_strategy(df, coin_name, variant_name, entry_filters, exit_strategy="TIME"):
    """複数EXIT戦略での実行"""
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
                                   (px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            highest_price = max(highest_price, px)
            exit_now = False
            reason = ""
            exit_px = px

            # 複数EXIT戦略
            if exit_strategy == "TIME":
                if held >= 10:
                    exit_now = True
                    reason = "TIME_10"
            elif exit_strategy == "PROFIT_TARGET":
                if px >= entry * 1.02:  # 2% profit target
                    exit_now = True
                    reason = "PROFIT_2PCT"
            elif exit_strategy == "TRAILING_STOP":
                if px <= highest_price * 0.98:  # 2% trailing stop
                    exit_now = True
                    reason = "TRAILING_STOP"
                    exit_px = highest_price * 0.98
            elif exit_strategy == "SL_ONLY":
                if lo <= ib_low:
                    exit_now = True
                    reason = "SL_HIT"
                    exit_px = ib_low
            elif exit_strategy == "COMBINED":
                # 複合：利確+SL+時間
                if px >= entry * 1.02:
                    exit_now = True
                    reason = "PROFIT_2PCT"
                elif lo <= ib_low:
                    exit_now = True
                    reason = "SL_HIT"
                    exit_px = ib_low
                elif held >= 15:
                    exit_now = True
                    reason = "TIME_15"

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
                highest_price = 0

        if not in_pos and i >= cool_until and i > 0:
            # Entry条件
            if df["inside_bar"].iloc[i]:
                should_enter = True

                # Entry filters
                for filt_name, filt_val in entry_filters.items():
                    if filt_name == "rsi_extreme":
                        rsi = r.get("rsi14", 50)
                        if not (rsi < 30 or rsi > 70):
                            should_enter = False
                    elif filt_name == "rsi_lower":
                        if r.get("rsi14", 50) >= filt_val:
                            should_enter = False
                    elif filt_name == "vol_above_avg":
                        if r.get("vol_ratio", 0) < filt_val:
                            should_enter = False
                    elif filt_name == "atr_above_avg":
                        if r.get("atr14", 0) < r.get("atr_sma", 0) * filt_val:
                            should_enter = False
                    elif filt_name == "adx_above":
                        if r.get("adx", 0) < filt_val:
                            should_enter = False
                    elif filt_name == "stoch_oversold":
                        if r.get("stoch_k", 50) >= filt_val:
                            should_enter = False
                    elif filt_name == "uptrend":
                        if r.get("close", 0) < r.get("ema55", 0):
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

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_name, entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


# ============================================================================
# ANALYSIS
# ============================================================================

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

    # 統計検定
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


# ============================================================================
# MAIN
# ============================================================================

def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    if not files:
        print("No data files found!")
        return

    print(f"\n{'='*150}")
    print(f"  INSIDE BAR - 高度な分析（EXIT戦略 + Entry フィルター最適化）")
    print(f"  対象: {len(files)} コイン")
    print(f"{'='*150}")

    # テスト構成
    entry_configs = {
        "Base": {},
        "RSIExtreme": {"rsi_extreme": True},
        "RSI<40": {"rsi_lower": 40},
        "VolAbove150": {"vol_above_avg": 1.5},
        "ATRAbove120": {"atr_above_avg": 1.2},
        "ADXAbove25": {"adx_above": 25},
        "StochOversold": {"stoch_oversold": 30},
        "Uptrend+RSI": {"uptrend": True, "rsi_lower": 40},
    }

    exit_strategies = ["TIME", "PROFIT_TARGET", "TRAILING_STOP", "SL_ONLY", "COMBINED"]

    results = {}

    for fpath in files[:3]:  # 最初の3コイン
        coin = os.path.basename(fpath).replace("_4h_365d.csv", "").replace("_USDCUSDC", "")
        print(f"\n  処理中: {coin}...", end="", flush=True)

        df = load_and_prepare(fpath)
        if len(df) < 100:
            print(" スキップ")
            continue

        coin_results = {}
        for entry_name, entry_filters in entry_configs.items():
            for exit_strat in exit_strategies:
                variant = f"{entry_name}_{exit_strat}"
                trades, eq = _run_with_exit_strategy(df, coin, variant, entry_filters, exit_strat)
                analysis = analyze(trades, eq)
                if analysis:
                    coin_results[variant] = analysis

        results[coin] = coin_results
        print(" 完了")

    # ========================================================================
    # レポート
    # ========================================================================

    print(f"\n{'='*150}")
    print(f"  【EXIT戦略別の平均パフォーマンス】")
    print(f"{'='*150}")
    print(f"  {'Exit Strategy':<20} {'Avg Trades':>8} {'Avg WR%':>7} {'Avg PF':>7} {'Avg PnL':>10} {'Avg Sharpe':>10} {'p<0.05':>6}")
    print(f"  {'-'*150}")

    exit_stats = {}
    for exit_strat in exit_strategies:
        trades_list = []
        wr_list = []
        pf_list = []
        pnl_list = []
        sharpe_list = []
        sig_count = 0

        for coin_res in results.values():
            for variant, analysis in coin_res.items():
                if variant.endswith(f"_{exit_strat}"):
                    trades_list.append(analysis["trades"])
                    wr_list.append(analysis["wr"])
                    if isinstance(analysis["pf"], (int, float)):
                        pf_list.append(analysis["pf"])
                    pnl_list.append(analysis["pnl"])
                    sharpe_list.append(analysis["sharpe"])
                    if analysis["p_value"] < 0.05:
                        sig_count += 1

        if trades_list:
            avg_trades = np.mean(trades_list)
            avg_wr = np.mean(wr_list)
            avg_pf = np.mean(pf_list) if pf_list else 0
            avg_pnl = np.mean(pnl_list)
            avg_sharpe = np.mean(sharpe_list)

            exit_stats[exit_strat] = {
                "trades": avg_trades,
                "wr": avg_wr,
                "pf": avg_pf,
                "pnl": avg_pnl,
                "sharpe": avg_sharpe,
                "sig": sig_count
            }

            print(f"  {exit_strat:<20} {avg_trades:>8.0f} {avg_wr:>6.0f}% {avg_pf:>7.2f} ${avg_pnl:>9.0f} {avg_sharpe:>10.2f} {sig_count:>6}")

    # Entry フィルター別
    print(f"\n{'='*150}")
    print(f"  【Entry フィルター別の平均パフォーマンス】")
    print(f"{'='*150}")
    print(f"  {'Entry Filter':<25} {'Avg Trades':>8} {'Avg WR%':>7} {'Avg PF':>7} {'Avg EV%':>8} {'Avg Sharpe':>10} {'p<0.05':>6}")
    print(f"  {'-'*150}")

    entry_stats = {}
    for entry_name in entry_configs.keys():
        trades_list = []
        wr_list = []
        pf_list = []
        ev_list = []
        sharpe_list = []
        sig_count = 0

        for coin_res in results.values():
            for variant, analysis in coin_res.items():
                if variant.startswith(f"{entry_name}_"):
                    trades_list.append(analysis["trades"])
                    wr_list.append(analysis["wr"])
                    if isinstance(analysis["pf"], (int, float)):
                        pf_list.append(analysis["pf"])
                    ev_list.append(analysis["ev"])
                    sharpe_list.append(analysis["sharpe"])
                    if analysis["p_value"] < 0.05:
                        sig_count += 1

        if trades_list:
            avg_trades = np.mean(trades_list)
            avg_wr = np.mean(wr_list)
            avg_pf = np.mean(pf_list) if pf_list else 0
            avg_ev = np.mean(ev_list)
            avg_sharpe = np.mean(sharpe_list)

            entry_stats[entry_name] = {
                "trades": avg_trades,
                "wr": avg_wr,
                "pf": avg_pf,
                "ev": avg_ev,
                "sharpe": avg_sharpe,
                "sig": sig_count
            }

            print(f"  {entry_name:<25} {avg_trades:>8.0f} {avg_wr:>6.0f}% {avg_pf:>7.2f} {avg_ev:>7.2f}% {avg_sharpe:>10.2f} {sig_count:>6}")

    # 目標達成チェック
    print(f"\n{'='*150}")
    print(f"  【統計有意性チェック (p < 0.05)】")
    print(f"{'='*150}")

    sig_variants = []
    for coin, coin_res in results.items():
        for variant, analysis in coin_res.items():
            if analysis["p_value"] < 0.05 and analysis["ev"] > 0.15:
                sig_variants.append((coin, variant, analysis))

    if sig_variants:
        sig_variants.sort(key=lambda x: x[2]["ev"], reverse=True)
        print(f"\n  ✓ 目標達成バリアント見つかり！(p<0.05 かつ EV>0.15%)\n")
        for coin, variant, analysis in sig_variants[:10]:
            print(f"    {coin:<10} {variant:<35} EV={analysis['ev']:.3f}% p={analysis['p_value']:.4f} Sharpe={analysis['sharpe']:.2f}")
    else:
        print(f"\n  現在のテスト構成では有意なバリアント見つからず")
        print(f"  最高スコアのバリアント：\n")

        best = []
        for coin, coin_res in results.items():
            for variant, analysis in coin_res.items():
                best.append((coin, variant, analysis))

        best.sort(key=lambda x: x[2]["sharpe"], reverse=True)
        for coin, variant, analysis in best[:10]:
            sig_mark = "✓" if analysis["p_value"] < 0.05 else " "
            print(f"    {sig_mark} {coin:<10} {variant:<35} Sharpe={analysis['sharpe']:>6.2f} EV={analysis['ev']:>7.3f}% p={analysis['p_value']:.4f}")

    print(f"\n{'='*150}\n")


if __name__ == "__main__":
    main()
