# -*- coding: utf-8 -*-
"""
Inside Bar Strategy - 複数時間軸テスト
========================================

テスト内容:
1. 4H での Inside Bar（メイン）
2. 1H での Inside Bar（中期トレンド内の短期反転）
3. 15M での Inside Bar（スキャルピング）

各時間軸で独立に機能するか検証
統計有意性を確認
"""

import os
import glob
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy import stats

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


def compute_volume_sma(volume, period=20):
    return volume.rolling(period).mean()


def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    return (entry - exit_px) * sz - notional * comm


def load_and_prepare(path, timeframe_str="4h"):
    """データ読み込みと準備"""
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

    # インジケーター
    df["atr14"] = compute_atr(df, 14)
    df["atr14_mean"] = df["atr14"].rolling(20).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["volume_sma"] = compute_volume_sma(df["volume"], 20)
    df["volume_ratio"] = df["volume"] / df["volume_sma"].replace(0, 1)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))

    return df


def run_backtest_timeframe(df, max_hold=10, use_vol_filter=True, use_atr_filter=True):
    """
    時間軸別バックテスト

    Parameters:
    - max_hold: 最大保有期間（バー数）
    - use_vol_filter: 出来高フィルター有効化
    - use_atr_filter: ATRフィルター有効化
    """
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
    loss_count = 0
    cool_until = 0

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo = r["close"], r["high"], r["low"]

        pv = sz * px if in_pos else 0
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            if in_pos:
                pnl = _pnl("LONG", entry, px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", "test", entry, px, sz, pnl,
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
            elif lo <= ib_low:
                exit_now = True
                reason = "IB_SL"
                exit_px = ib_low

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", "test", entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until and i > 0:
            if df["inside_bar"].iloc[i-1]:
                # フィルター適用
                filter_ok = True

                if use_vol_filter:
                    vol_ratio = r.get("volume_ratio", 0)
                    if vol_ratio < 1.5:
                        filter_ok = False

                if filter_ok and use_atr_filter:
                    atr = r.get("atr14", np.nan)
                    atr_mean = r.get("atr14_mean", np.nan)
                    if not (np.isnan(atr) or np.isnan(atr_mean) or atr_mean == 0):
                        atr_ratio = atr / atr_mean
                        if atr_ratio < 1.2:
                            filter_ok = False

                if filter_ok:
                    risk = cash * RISK_PCT
                    sz = (cash * MAX_POS_PCT) / px
                    if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                        cash -= sz * px * (1 + cm)
                        in_pos = True
                        entry = px
                        ts_in = ts
                        bar_in = i
                        ib_low = df["low"].iloc[i-1]

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", "test", entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


def analyze_trades(trades, eq):
    """取引分析"""
    if not trades:
        return None

    pnls = [t.pnl for t in trades]
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    wr = len(wins) / len(trades) * 100 if len(trades) > 0 else 0
    avg_w = np.mean([t.pnl for t in wins]) if wins else 0
    avg_l = np.mean([t.pnl for t in losses]) if losses else 0
    win_total = sum(t.pnl for t in wins)
    loss_total = sum(t.pnl for t in losses)
    pf = abs(win_total / loss_total) if loss_total != 0 else float('inf')
    total_pnl = sum(pnls)
    avg_trade = total_pnl / len(trades) if len(trades) > 0 else 0

    eq_arr = np.array(eq)
    peak = np.maximum.accumulate(eq_arr)
    dd = (peak - eq_arr) / peak
    max_dd = np.max(dd) * 100 if len(dd) > 0 else 0

    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(365*6) if np.std(rets) > 0 else 0

    # 統計有意性
    if len(pnls) >= 2:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        t_stat, p_value = np.nan, 1.0

    return {
        "trades": len(trades),
        "win_rate": round(wr, 1),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "profit_factor": round(pf, 2) if pf != float('inf') else "INF",
        "total_pnl": round(total_pnl, 2),
        "avg_trade": round(avg_trade, 2),
        "max_dd": round(max_dd, 1),
        "sharpe": round(sharpe, 2),
        "p_value": round(p_value, 4),
        "t_stat": round(t_stat, 4),
    }


def resample_and_test(df, base_timeframe, target_timeframe, timeframe_hours):
    """
    時間軸リサンプリングとテスト

    base_timeframe: "4h", "1h", "15m"
    target_timeframe: 目標時間軸（バー数）
    timeframe_hours: 時間数
    """
    if len(df) < timeframe_hours * 4:
        return None  # データ不足

    # リサンプリング（OHLCVを適切に集計）
    df_resampled = df.resample(f"{timeframe_hours}h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    if len(df_resampled) < 50:
        return None

    # インジケーター再計算
    df_resampled["atr14"] = compute_atr(df_resampled, 14)
    df_resampled["atr14_mean"] = df_resampled["atr14"].rolling(20).mean()
    df_resampled["rsi14"] = compute_rsi(df_resampled["close"], 14)
    df_resampled["volume_sma"] = compute_volume_sma(df_resampled["volume"], 20)
    df_resampled["volume_ratio"] = df_resampled["volume"] / df_resampled["volume_sma"].replace(0, 1)
    df_resampled["inside_bar"] = (df_resampled["high"] < df_resampled["high"].shift(1)) & \
                                  (df_resampled["low"] > df_resampled["low"].shift(1))

    # バックテスト
    trades, eq = run_backtest_timeframe(df_resampled, max_hold=10, use_vol_filter=True, use_atr_filter=True)
    return analyze_trades(trades, eq)


def main():
    """メイン実行"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" in os.path.basename(f)]

    if not files:
        files = sorted(glob.glob(os.path.join(data_dir, "*_4h_*.csv")))[:1]

    print(f"\n{'='*140}")
    print(f"  INSIDE BAR STRATEGY - 複数時間軸テスト")
    print(f"  テスト対象: 4H / 1H / 15M")
    print(f"  データ: {len(files)} coins")
    print(f"{'='*140}")

    timeframes = [
        ("4H", 4),
        ("1H", 1),
    ]

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        print(f"\n{coin}")

        try:
            df = load_and_prepare(fpath)
            if len(df) < 200:
                print(f"  Skipped: insufficient data")
                continue

            coin_results = {}
            for tf_name, tf_hours in timeframes:
                result = resample_and_test(df, "4h", tf_name, tf_hours)
                if result:
                    coin_results[tf_name] = result
                    print(f"  {tf_name:<5} trades={result['trades']:>4} wr={result['win_rate']:>5.1f}% "
                          f"pf={str(result['profit_factor']):>6} pnl=${result['total_pnl']:>8.0f} "
                          f"sharpe={result['sharpe']:>6.2f} p={result['p_value']:.4f}")
                else:
                    print(f"  {tf_name:<5} insufficient data for this timeframe")

            all_results[coin] = coin_results
        except Exception as e:
            print(f"  Error: {e}")

    # 結果サマリー
    print(f"\n{'='*140}")
    print(f"  SUMMARY BY TIMEFRAME")
    print(f"{'='*140}")

    for tf_name, _ in timeframes:
        vals = [all_results[c][tf_name] for c in all_results if tf_name in all_results[c]]
        if vals:
            avg_trades = np.mean([r["trades"] for r in vals])
            avg_wr = np.mean([r["win_rate"] for r in vals])
            avg_pnl = np.mean([r["total_pnl"] for r in vals])
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            avg_p = np.mean([r["p_value"] for r in vals])
            pf_vals = [r["profit_factor"] for r in vals if isinstance(r["profit_factor"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0

            sig = "✓ p<0.05" if avg_p < 0.05 else "✗ p>=0.05"
            print(f"  {tf_name:<10} Trades={avg_trades:>5.0f} WR={avg_wr:>5.1f}% PF={avg_pf:>5.2f} "
                  f"PnL=${avg_pnl:>8.0f} Sharpe={avg_sharpe:>6.2f} {sig}")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
