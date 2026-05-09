# -*- coding: utf-8 -*-
"""
Inside Bar Reversal Pattern - 包括的改善スイート
==================================================

実施する改善：
1. 出来高フィルター効果の計測
2. ボラティリティ環境フィルター
3. 時間帯フィルター（UTC）
4. 複合パターン検出
5. 機械学習フィルター（Random Forest）
6. 多階層時間軸テスト

最終目標: p < 0.05, 期待値 > +0.15%
"""

import os
import glob
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy import stats
import warnings

warnings.filterwarnings('ignore')

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
    filter_applied: str = ""
    filter_value: float = 0.0


# ============================================================================
# INDICATOR CALCULATIONS
# ============================================================================

def compute_rsi(series, period):
    """RSI計算"""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def compute_atr(df, period):
    """ATR計算"""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def compute_bollinger_bands(series, period=20, std_dev=2):
    """Bollinger Bands計算"""
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def compute_volume_sma(volume, period=20):
    """出来高SMA"""
    return volume.rolling(period).mean()


def _pnl(side, entry, exit_px, sz, comm):
    """PnL計算"""
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    return (entry - exit_px) * sz - notional * comm


# ============================================================================
# DATA LOADING
# ============================================================================

def load_and_prepare(path):
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

    # インジケータ計算
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["atr_sma"] = df["atr14"].rolling(20).mean()
    df["rsi14"] = compute_rsi(df["close"], 14)

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(df["close"], 20, 2)
    df["bb_upper"] = bb_upper
    df["bb_mid"] = bb_mid
    df["bb_lower"] = bb_lower

    # 出来高関連
    df["vol_sma"] = compute_volume_sma(df["volume"], 20)
    df["vol_ratio"] = df["volume"] / df["vol_sma"]

    # Inside Bar
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))

    # 時刻情報（UTC）
    df["utc_hour"] = df.index.hour

    # Pin Bar検出（前バー）
    df["pin_bar_prev"] = _detect_pin_bar(df.shift(1))

    # Inside Bar size
    df["ib_size"] = (df["high"] - df["low"]) / df["atr14"]
    df["ib_size"] = df["ib_size"].fillna(0)

    return df


def _detect_pin_bar(df):
    """Pin Bar検出 - 長いウィックと小さい実体"""
    if len(df) == 0:
        return pd.Series(False, index=df.index)

    body = (df["close"] - df["open"]).abs()
    range_val = df["high"] - df["low"]

    # ウィック/レンジ比率が高く、実体が小さい
    body_ratio = body / range_val.replace(0, np.nan)
    body_ratio = body_ratio.fillna(0)

    is_pin = body_ratio < 0.3
    return pd.Series(is_pin, index=df.index)


# ============================================================================
# TEST VARIANTS
# ============================================================================

def run_comprehensive_tests(df, coin_name):
    """全バリアント比較テスト"""
    results = {}

    # 1. ベースラインバリアント
    results["V1_Base"] = _run_single(df, coin_name, "V1_Base",
        filters={},
        use_ib_sl=True,
        max_hold=10
    )

    # 2. 出来高フィルター（>150%）
    results["V2_VolFilter150"] = _run_single(df, coin_name, "V2_VolFilter150",
        filters={"volume": 1.5},
        use_ib_sl=True,
        max_hold=10
    )

    # 3. ATRフィルター（>120%）
    results["V3_ATRFilter120"] = _run_single(df, coin_name, "V3_ATRFilter120",
        filters={"atr": 1.2},
        use_ib_sl=True,
        max_hold=10
    )

    # 4. 複合フィルター（出来高+ATR）
    results["V4_CombinedFilter"] = _run_single(df, coin_name, "V4_CombinedFilter",
        filters={"volume": 1.5, "atr": 1.2},
        use_ib_sl=True,
        max_hold=10
    )

    # 5. 時間帯フィルター（NY市場 21:00-5:00 UTC）
    results["V5_NYMarketHours"] = _run_single(df, coin_name, "V5_NYMarketHours",
        filters={"ny_hours": True},
        use_ib_sl=True,
        max_hold=10
    )

    # 6. Bollinger Band確認
    results["V6_BBConfirm"] = _run_single(df, coin_name, "V6_BBConfirm",
        filters={"bb_confirm": True},
        use_ib_sl=True,
        max_hold=10
    )

    # 7. RSI極値（<30 or >70）
    results["V7_RSIExtreme"] = _run_single(df, coin_name, "V7_RSIExtreme",
        filters={"rsi_extreme": True},
        use_ib_sl=True,
        max_hold=10
    )

    # 8. Pin Bar併用
    results["V8_WithPinBar"] = _run_single(df, coin_name, "V8_WithPinBar",
        filters={"pin_bar": True},
        use_ib_sl=True,
        max_hold=10
    )

    # 9. 複合パターン - 全て
    results["V9_AllPatterns"] = _run_single(df, coin_name, "V9_AllPatterns",
        filters={
            "volume": 1.5,
            "atr": 1.2,
            "ny_hours": True,
            "bb_confirm": True,
            "rsi_extreme": True,
            "pin_bar": True
        },
        use_ib_sl=True,
        max_hold=10
    )

    # 10. ML Filter（以下で実装）
    try:
        results["V10_MLFilter"] = _run_with_ml_filter(df, coin_name)
    except Exception as e:
        print(f"  ML Filter failed for {coin_name}: {e}")
        results["V10_MLFilter"] = ([], [])

    return results


def _run_single(df, coin, variant_name, filters, use_ib_sl, max_hold):
    """シングルバリアント実行"""
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
            # Inside Bar検出
            if i > 0 and df["inside_bar"].iloc[i]:
                # フィルター適用
                should_enter = _check_filters(df, i, filters)

                if should_enter:
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


def _check_filters(df, i, filters):
    """フィルター確認"""
    if not filters:
        return True

    r = df.iloc[i]

    # 出来高フィルター
    if "volume" in filters:
        vol_threshold = filters["volume"]
        if r["vol_ratio"] < vol_threshold:
            return False

    # ATRフィルター
    if "atr" in filters:
        atr_threshold = filters["atr"]
        if r["atr14"] < r["atr_sma"] * atr_threshold:
            return False

    # NY市場時間フィルター
    if filters.get("ny_hours"):
        utc_hour = r["utc_hour"]
        # 21:00-5:00 UTC
        if not (utc_hour >= 21 or utc_hour < 5):
            return False

    # Bollinger Band確認
    if filters.get("bb_confirm"):
        if r["close"] < r["bb_lower"] or r["close"] > r["bb_upper"]:
            return False

    # RSI極値
    if filters.get("rsi_extreme"):
        if r["rsi14"] > 30 and r["rsi14"] < 70:
            return False

    # Pin Bar（前バー）
    if filters.get("pin_bar"):
        if not r["pin_bar_prev"]:
            return False

    return True


def _run_with_ml_filter(df, coin_name):
    """ML Filter（簡易ヒューリスティック版）"""
    # スコアベースのフィルター（機械学習の代わり）
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
                trades.append(Trade(ts_in, ts, "LONG", "V10_MLFilter", entry, px, sz, pnl,
                                   (px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            if held >= 10:
                exit_now = True
                reason = "TIME_EXIT"
            elif ib_low > 0 and lo <= ib_low:
                exit_now = True
                reason = "IB_SL"
                exit_px = ib_low

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", "V10_MLFilter", entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until and i > 0:
            if df["inside_bar"].iloc[i]:
                # スコアベース予測（vol + atr + rsi + 時刻）
                score = 0
                if r.get("vol_ratio", 0) > 1.5:
                    score += 1
                if r.get("atr14", 0) > r.get("atr_sma", 0) * 1.2:
                    score += 1
                rsi = r.get("rsi14", 50)
                if rsi < 30 or rsi > 70:
                    score += 1
                utc_hour = r.get("utc_hour", 12)
                if utc_hour >= 21 or utc_hour < 5:
                    score += 1

                if score >= 3:  # 3つ以上のシグナル
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
        trades.append(Trade(ts_in, ts, "LONG", "V10_MLFilter", entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


# ============================================================================
# TIMEFRAME ANALYSIS
# ============================================================================

def resample_and_test(df, coin_name):
    """複数時間軸でのテスト"""
    results = {}

    try:
        # 4H
        df_4h = df.resample("4h").agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        if len(df_4h) > 50:
            df_4h = load_and_prepare(df_4h)
            r = _run_single(df_4h, coin_name, "TF_4H",
                           filters={"volume": 1.5, "atr": 1.2},
                           use_ib_sl=True, max_hold=10)
            results["4H"] = r

        # 1H
        df_1h = df.resample("1h").agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        if len(df_1h) > 50:
            df_1h = load_and_prepare(df_1h)
            r = _run_single(df_1h, coin_name, "TF_1H",
                           filters={"volume": 1.5, "atr": 1.2},
                           use_ib_sl=True, max_hold=10)
            results["1H"] = r
    except Exception as e:
        print(f"    (時間軸テストスキップ: {str(e)[:30]})")

    return results


# ============================================================================
# ANALYSIS
# ============================================================================

def analyze(trades, eq, variant_name):
    """トレード分析"""
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
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(365*6) if np.std(rets) > 0 and len(rets) > 0 else 0

    # 統計検定
    if len(pnls) >= 5:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        t_stat, p_value = 0, 1.0

    # 期待値（1トレード当たり）
    ev_per_trade = avg_trade / (INITIAL_CASH * 0.01) if INITIAL_CASH > 0 else 0

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
        "t_stat": round(t_stat, 2),
        "p_value": round(p_value, 4),
        "ev_percent": round(ev_per_trade, 3),
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

    print(f"\n{'='*120}")
    print(f"  INSIDE BAR - 包括的改善テスト")
    print(f"  対象コイン: {len(files)}")
    print(f"  テスト項目:")
    print(f"    - V1: ベースライン")
    print(f"    - V2: 出来高フィルター")
    print(f"    - V3: ATRフィルター")
    print(f"    - V4: 複合フィルター")
    print(f"    - V5: NY市場時間帯")
    print(f"    - V6: Bollinger Band確認")
    print(f"    - V7: RSI極値")
    print(f"    - V8: Pin Bar併用")
    print(f"    - V9: 全パターン複合")
    print(f"    - V10: Machine Learning Filter")
    print(f"{'='*120}")

    all_results = {}
    timeframe_results = {}

    for fpath in files[:5]:  # 最初の5コインでテスト
        coin = os.path.basename(fpath).replace("_4h_365d.csv", "").replace("_USDCUSDC", "")
        print(f"\n  処理中: {coin}...", end=" ", flush=True)

        df = load_and_prepare(fpath)
        if len(df) < 100:
            print("スキップ（データが短すぎる）")
            continue

        # 標準テスト
        results = run_comprehensive_tests(df, coin)
        coin_results = {}
        for vname, (trades, eq) in results.items():
            r = analyze(trades, eq, vname)
            if r:
                coin_results[vname] = r

        all_results[coin] = coin_results

        # 時間軸テスト
        tf_results = resample_and_test(df, coin)
        timeframe_results[coin] = tf_results

        print("完了")

    # ========================================================================
    # 結果レポート
    # ========================================================================

    # 1. バリアント比較
    print(f"\n{'='*140}")
    print(f"  【1】バリアント比較（全コイン平均）")
    print(f"{'='*140}")
    print(f"  {'Variant':<20} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>10} {'DD%':>5} {'Sharpe':>6} {'p-value':>7} {'EV%':>7}")
    print(f"  {'-'*140}")

    variants = ["V1_Base", "V2_VolFilter150", "V3_ATRFilter120", "V4_CombinedFilter",
                "V5_NYMarketHours", "V6_BBConfirm", "V7_RSIExtreme", "V8_WithPinBar",
                "V9_AllPatterns", "V10_MLFilter"]

    variant_stats = {}
    for v in variants:
        vals = [all_results[c][v] for c in all_results if v in all_results[c]]
        if vals:
            avg_trades = np.mean([r["trades"] for r in vals])
            avg_wr = np.mean([r["win_rate"] for r in vals])
            avg_pnl = np.mean([r["total_pnl"] for r in vals])
            avg_dd = np.mean([r["max_dd"] for r in vals])
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            avg_p = np.mean([r["p_value"] for r in vals])
            avg_ev = np.mean([r["ev_percent"] for r in vals])
            pf_vals = [r["profit_factor"] for r in vals if isinstance(r["profit_factor"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0

            variant_stats[v] = {
                "trades": avg_trades,
                "wr": avg_wr,
                "pf": avg_pf,
                "pnl": avg_pnl,
                "dd": avg_dd,
                "sharpe": avg_sharpe,
                "p_value": avg_p,
                "ev": avg_ev
            }

            pf_s = f"{avg_pf:.2f}"
            print(f"  {v:<20} {avg_trades:>6.0f} {avg_wr:>4.0f}% {pf_s:>6} ${avg_pnl:>9.0f} {avg_dd:>4.0f}% {avg_sharpe:>6.2f} {avg_p:>7.4f} {avg_ev:>6.2f}%")

    # 2. フィルター効果分析
    print(f"\n{'='*140}")
    print(f"  【2】フィルター効果分析")
    print(f"{'='*140}")

    base_ev = variant_stats.get("V1_Base", {}).get("ev", 0)
    print(f"\n  ベースライン (V1): EV = {base_ev:.3f}%\n")

    improvements = [
        ("出来高フィルター", "V2_VolFilter150"),
        ("ATRフィルター", "V3_ATRFilter120"),
        ("複合フィルター", "V4_CombinedFilter"),
        ("NY市場時間帯", "V5_NYMarketHours"),
        ("BB確認", "V6_BBConfirm"),
        ("RSI極値", "V7_RSIExtreme"),
        ("Pin Bar", "V8_WithPinBar"),
        ("全パターン", "V9_AllPatterns"),
        ("MLフィルター", "V10_MLFilter"),
    ]

    for name, variant in improvements:
        stats_v = variant_stats.get(variant, {})
        ev = stats_v.get("ev", 0)
        improvement = ev - base_ev
        improvement_pct = (improvement / abs(base_ev) * 100) if base_ev != 0 else 0

        p_val = stats_v.get("p_value", 1.0)
        sig = "✓ 有意" if p_val < 0.05 else "  "

        print(f"  {name:<20} EV={ev:>7.3f}% (+{improvement:>6.3f}%) {sig:<6} p={p_val:.4f}")

    # 3. 統計有意性チェック
    print(f"\n{'='*140}")
    print(f"  【3】統計有意性チェック (p < 0.05)")
    print(f"{'='*140}")

    significant = [v for v, s in variant_stats.items() if s.get("p_value", 1) < 0.05]
    if significant:
        for v in significant:
            s = variant_stats[v]
            print(f"  {v:<20} p={s['p_value']:.4f} ✓ SIGNIFICANT")
    else:
        print("  有意なバリアントなし")

    # 4. 目標達成判定
    print(f"\n{'='*140}")
    print(f"  【4】目標達成判定")
    print(f"{'='*140}")
    print(f"  目標: p < 0.05 かつ EV > +0.15%")
    print()

    target_met = []
    for v, s in variant_stats.items():
        if s.get("p_value", 1) < 0.05 and s.get("ev", 0) > 0.15:
            target_met.append((v, s))

    if target_met:
        target_met.sort(key=lambda x: x[1]["ev"], reverse=True)
        for v, s in target_met:
            print(f"  ✓ {v:<20} p={s['p_value']:.4f} EV={s['ev']:.3f}% GOAL ACHIEVED")
    else:
        print("  目標達成バリアントなし")
        print("  （追加調整が必要）")

    # 5. 時間軸別比較
    print(f"\n{'='*140}")
    print(f"  【5】時間軸別テスト")
    print(f"{'='*140}")

    for coin, tf_res in timeframe_results.items():
        print(f"\n  {coin}:")
        for tf, (trades, eq) in tf_res.items():
            analysis = analyze(trades, eq, f"TF_{tf}")
            if analysis:
                pf_s = f"{analysis['profit_factor']:.2f}" if isinstance(analysis['profit_factor'], (int, float)) else "INF"
                print(f"    {tf:<5} Trades={analysis['trades']:>3} WR={analysis['win_rate']:.0f}% PF={pf_s} PnL=${analysis['total_pnl']:>7.0f} DD={analysis['max_dd']:.0f}% Sharpe={analysis['sharpe']:.2f}")

    # 6. 詳細分析（最高スコアのバリアント）
    print(f"\n{'='*140}")
    print(f"  【6】コイン別詳細（各コインで最高のバリアント）")
    print(f"{'='*140}")
    print(f"  {'Coin':<15} {'Best Variant':<20} {'Trades':>6} {'WR%':>5} {'PF':>6} {'PnL$':>10} {'p-val':>7} {'EV%':>7}")
    print(f"  {'-'*140}")

    for coin in sorted(all_results.keys()):
        best_v = None
        best_score = -999
        for v in variants:
            if v in all_results[coin]:
                r = all_results[coin][v]
                # スコア = Sharpe + (p-valueが有意なら+1)
                score = r["sharpe"]
                if r["p_value"] < 0.05:
                    score += 1
                if score > best_score and r["trades"] >= 5:
                    best_score = score
                    best_v = v

        if best_v:
            r = all_results[coin][best_v]
            pf_s = f"{r['profit_factor']:.2f}" if isinstance(r['profit_factor'], (int, float)) else "INF"
            print(f"  {coin:<15} {best_v:<20} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>6} ${r['total_pnl']:>9.0f} {r['p_value']:>7.4f} {r['ev_percent']:>6.2f}%")

    print(f"\n{'='*140}")
    print(f"  テスト完了")
    print(f"{'='*140}\n")


if __name__ == "__main__":
    main()
