# -*- coding: utf-8 -*-
"""
Inside Bar Reversal Pattern - 改善版 v2
========================================

改善内容:
1. 出来高フィルター - 出来高ブレイク検出
2. ボラティリティ環境フィルター - ATR-based
3. 時間帯フィルター - UTC時刻を考慮
4. 複合パターン検出 - Inside Bar + 他のシグナル
5. ブレイクアウト確認メカニズム - 次バーでの確認

目標: p < 0.05達成, +0.2%～+0.3%/月
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
    filter_reason: str = ""


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

    # インジケーター計算
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["atr14_mean"] = df["atr14"].rolling(20).mean()  # ATR平均（環境判定用）
    df["rsi14"] = compute_rsi(df["close"], 14)

    # Inside Bar検出
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))

    # 出来高フィルター
    df["volume_sma"] = compute_volume_sma(df["volume"], 20)
    df["volume_ratio"] = df["volume"] / df["volume_sma"].replace(0, 1)

    # Bollinger Bands
    df["bb_upper"], df["bb_sma"], df["bb_lower"] = compute_bollinger_bands(df["close"], 20, 2)
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]
    df["bb_width_sma"] = df["bb_width"].rolling(20).mean()

    # ピンバー検出（前のバー）
    df["prev_range"] = df["high"].shift(1) - df["low"].shift(1)
    df["prev_body"] = (df["open"].shift(1) - df["close"].shift(1)).abs()
    df["prev_wick_ratio"] = (df["prev_range"] - df["prev_body"]) / df["prev_range"].replace(0, 1)
    df["is_pinbar"] = df["prev_wick_ratio"] > 0.6  # ウィック比率が高い

    # UTC時刻抽出（仮：インデックスがタイムゾーン対応と仮定）
    try:
        df["hour_utc"] = df.index.hour
    except:
        df["hour_utc"] = 0

    return df


# ============================================================================
# FILTER FUNCTIONS
# ============================================================================

class PatternFilter:
    """パターンフィルター集約クラス"""

    def __init__(self, df, i):
        self.df = df
        self.i = i
        self.r = df.iloc[i]

    def check_volume_filter(self, volume_threshold=1.5):
        """
        出来高フィルター
        出来高が平均の150%以上 = ブレイク可能性高
        """
        if self.i < 1:
            return True, "no_history"
        vol_ratio = self.r.get("volume_ratio", 0)
        if vol_ratio >= volume_threshold:
            return True, f"vol_ok_{vol_ratio:.2f}"
        return False, f"low_vol_{vol_ratio:.2f}"

    def check_volatility_filter(self, atr_threshold_high=1.2, atr_threshold_low=0.8):
        """
        ボラティリティ環境フィルター
        ATR > 平均 × 1.2 = OK
        ATR < 平均 × 0.8 = スキップ
        """
        atr = self.r.get("atr14", np.nan)
        atr_mean = self.r.get("atr14_mean", np.nan)

        if np.isnan(atr) or np.isnan(atr_mean) or atr_mean == 0:
            return True, "no_atr_data"

        atr_ratio = atr / atr_mean

        if atr_ratio >= atr_threshold_high:
            return True, f"high_vol_{atr_ratio:.2f}"
        elif atr_ratio <= atr_threshold_low:
            return False, f"low_vol_{atr_ratio:.2f}"
        return True, f"normal_vol_{atr_ratio:.2f}"

    def check_time_filter(self, enable_time_filter=False):
        """
        時間帯フィルター
        NY市場オープン（21:00 UTC）～ アジア市場オープン（23:00 UTC）
        を優先して取引
        """
        if not enable_time_filter:
            return True, "time_filter_disabled"

        hour = int(self.r.get("hour_utc", 0))

        # 優先時間帯: 21:00-23:59 UTC (NY market)
        if 21 <= hour <= 23:
            return True, f"optimal_hour_{hour}"

        # 許容時間帯: 0:00-8:00 UTC (Asia market overlap)
        if 0 <= hour <= 8:
            return True, f"acceptable_hour_{hour}"

        return False, f"poor_hour_{hour}"

    def check_bb_squeeze(self):
        """
        Bollinger Band絞られ条件
        Inside Bar + BB幅が狭い = ブレイク可能性高
        """
        if self.i < 1:
            return False, "no_history"

        bb_width = self.r.get("bb_width", np.nan)
        bb_width_sma = self.r.get("bb_width_sma", np.nan)

        if np.isnan(bb_width) or np.isnan(bb_width_sma) or bb_width_sma == 0:
            return False, "no_bb_data"

        bb_ratio = bb_width / bb_width_sma

        if bb_ratio < 0.8:
            return True, f"bb_squeeze_{bb_ratio:.2f}"
        return False, f"bb_normal_{bb_ratio:.2f}"

    def check_rsi_extreme(self):
        """
        RSI極値条件
        RSI < 30 or RSI > 70
        """
        rsi = self.r.get("rsi14", np.nan)
        if np.isnan(rsi):
            return False, "no_rsi_data"

        if rsi < 30:
            return True, f"rsi_oversold_{rsi:.0f}"
        elif rsi > 70:
            return True, f"rsi_overbought_{rsi:.0f}"
        return False, f"rsi_normal_{rsi:.0f}"

    def check_pinbar(self):
        """前のバーがピンバーか確認"""
        if self.i < 1:
            return False, "no_history"

        is_pinbar = self.r.get("is_pinbar", False)
        if is_pinbar:
            return True, "prev_pinbar"
        return False, "prev_not_pinbar"


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest_single(df, coin_name, variant_config):
    """
    単一バリアント実行

    variant_config:
        name: str
        use_volume_filter: bool
        use_volatility_filter: bool
        use_time_filter: bool
        use_bb_squeeze: bool (複合パターン)
        use_rsi_extreme: bool (複合パターン)
        use_pinbar: bool (複合パターン)
        require_breakout_confirmation: bool
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
    ib_high = 0
    ib_low = 0
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
                trades.append(Trade(ts_in, ts, "LONG", variant_config["name"], entry, px, sz, pnl,
                                   (px/entry-1)*100, "DD_HALT", i - bar_in))
                in_pos = False
            continue

        if in_pos:
            held = i - bar_in
            exit_now = False
            reason = ""
            exit_px = px

            # 時間切りで決済
            if held >= 10:
                exit_now = True
                reason = "TIME_EXIT"
            # Inside Bar安値でSL
            elif lo <= ib_low:
                exit_now = True
                reason = "IB_SL"
                exit_px = ib_low

            if exit_now:
                pnl = _pnl("LONG", entry, exit_px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, "LONG", variant_config["name"], entry, exit_px, sz, pnl,
                                   (exit_px/entry-1)*100, reason, held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        if not in_pos and i >= cool_until and i > 0:
            # Inside Bar検出
            if df["inside_bar"].iloc[i-1]:
                pf = PatternFilter(df, i)

                # フィルター適用
                filter_passed = True
                filter_reasons = []

                if variant_config.get("use_volume_filter", False):
                    vol_ok, vol_msg = pf.check_volume_filter()
                    filter_reasons.append(vol_msg)
                    if not vol_ok:
                        filter_passed = False

                if filter_passed and variant_config.get("use_volatility_filter", False):
                    vol_ok, vol_msg = pf.check_volatility_filter()
                    filter_reasons.append(vol_msg)
                    if not vol_ok:
                        filter_passed = False

                if filter_passed and variant_config.get("use_time_filter", False):
                    time_ok, time_msg = pf.check_time_filter(True)
                    filter_reasons.append(time_msg)
                    if not time_ok:
                        filter_passed = False

                # 複合パターン
                if filter_passed and variant_config.get("use_bb_squeeze", False):
                    bb_ok, bb_msg = pf.check_bb_squeeze()
                    filter_reasons.append(bb_msg)
                    if not bb_ok:
                        filter_passed = False

                if filter_passed and variant_config.get("use_rsi_extreme", False):
                    rsi_ok, rsi_msg = pf.check_rsi_extreme()
                    filter_reasons.append(rsi_msg)
                    if not rsi_ok:
                        filter_passed = False

                if filter_passed and variant_config.get("use_pinbar", False):
                    pin_ok, pin_msg = pf.check_pinbar()
                    filter_reasons.append(pin_msg)
                    if not pin_ok:
                        filter_passed = False

                # ブレイクアウト確認
                if filter_passed and variant_config.get("require_breakout_confirmation", False):
                    # Inside Barの上下限
                    ib_high_prev = df["high"].iloc[i-1]
                    ib_low_prev = df["low"].iloc[i-1]

                    # 現在のバーで確認
                    long_breakout = px > ib_high_prev
                    short_breakout = px < ib_low_prev

                    if not (long_breakout or short_breakout):
                        filter_passed = False
                        filter_reasons.append("no_breakout_confirmation")

                if filter_passed:
                    risk = cash * RISK_PCT
                    sz = (cash * MAX_POS_PCT) / px
                    if sz * px >= 10 and sz * px * (1 + cm) <= cash:
                        cash -= sz * px * (1 + cm)
                        in_pos = True
                        entry = px
                        ts_in = ts
                        bar_in = i
                        ib_high = df["high"].iloc[i-1]
                        ib_low = df["low"].iloc[i-1]

    if in_pos:
        pnl = _pnl("LONG", entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, "LONG", variant_config["name"], entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


# ============================================================================
# ANALYSIS
# ============================================================================

def analyze(trades, eq, variant_name):
    """取引分析"""
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
    max_dd = np.max(dd) * 100 if len(dd) > 0 else 0

    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(365*6) if np.std(rets) > 0 else 0

    # 統計有意性
    if len(pnls) >= 2:
        t_stat, p_value = stats.ttest_1samp(pnls, 0)
    else:
        t_stat, p_value = np.nan, 1.0

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
        "p_value": round(p_value, 4),
        "t_stat": round(t_stat, 4),
        "exit_reasons": exit_reasons,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    """メイン実行"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_365d.csv")))
    files = [f for f in files if "BTC" in os.path.basename(f)]  # BTCのみ

    if not files:
        print("BTC data files not found. Searching for any 4h data...")
        files = sorted(glob.glob(os.path.join(data_dir, "*_4h_*.csv")))[:1]

    print(f"\n{'='*120}")
    print(f"  INSIDE BAR STRATEGY - 改善版 v2")
    print(f"  データ: {len(files)} coins")
    print(f"{'='*120}")

    # テスト対象バリアント
    variants = [
        {
            "name": "V1_Baseline",
            "use_volume_filter": False,
            "use_volatility_filter": False,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V2_VolFilter",
            "use_volume_filter": True,
            "use_volatility_filter": False,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V3_ATRFilter",
            "use_volume_filter": False,
            "use_volatility_filter": True,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V4_Vol+ATR",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V5_TimeFilter",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": True,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V6_Composite1",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": False,
            "use_bb_squeeze": True,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V7_Composite2",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": True,
            "use_pinbar": False,
            "require_breakout_confirmation": False,
        },
        {
            "name": "V8_BreakoutConfirm",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": False,
            "use_bb_squeeze": False,
            "use_rsi_extreme": False,
            "use_pinbar": False,
            "require_breakout_confirmation": True,
        },
        {
            "name": "V9_Full",
            "use_volume_filter": True,
            "use_volatility_filter": True,
            "use_time_filter": True,
            "use_bb_squeeze": True,
            "use_rsi_extreme": False,
            "use_pinbar": True,
            "require_breakout_confirmation": False,
        },
    ]

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        print(f"\nProcessing: {coin}")

        try:
            df = load_and_prepare(fpath)
            if len(df) < 100:
                print(f"  Skipped: insufficient data ({len(df)} bars)")
                continue

            coin_results = {}
            for variant in variants:
                trades, eq = run_backtest_single(df, coin, variant)
                r = analyze(trades, eq, variant["name"])
                if r:
                    coin_results[variant["name"]] = r
                    print(f"  {variant['name']:<20} trades={r['trades']:>3} wr={r['win_rate']:>5.1f}% "
                          f"pf={str(r['profit_factor']):>6} pnl=${r['total_pnl']:>8.0f} "
                          f"sharpe={r['sharpe']:>6.2f} p={r['p_value']:.4f}")

            all_results[coin] = coin_results
        except Exception as e:
            print(f"  Error: {e}")
            continue

    # 結果サマリー
    print(f"\n{'='*140}")
    print(f"  SUMMARY BY VARIANT")
    print(f"{'='*140}")

    for variant in variants:
        vname = variant["name"]
        vals = [all_results[c][vname] for c in all_results if vname in all_results[c]]
        if vals:
            avg_trades = np.mean([r["trades"] for r in vals])
            avg_wr = np.mean([r["win_rate"] for r in vals])
            avg_pnl = np.mean([r["total_pnl"] for r in vals])
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            avg_p = np.mean([r["p_value"] for r in vals])
            pf_vals = [r["profit_factor"] for r in vals if isinstance(r["profit_factor"], (int, float))]
            avg_pf = np.mean(pf_vals) if pf_vals else 0

            sig = "✓ p<0.05" if avg_p < 0.05 else "✗ p>=0.05"
            print(f"  {vname:<20} Trades={avg_trades:>5.0f} WR={avg_wr:>5.1f}% PF={avg_pf:>5.2f} "
                  f"PnL=${avg_pnl:>8.0f} Sharpe={avg_sharpe:>6.2f} {sig}")

    # ベストバリアント
    print(f"\n{'='*140}")
    print(f"  BEST VARIANT (by avg Sharpe)")
    print(f"{'='*140}")
    best_variant = None
    best_sharpe = -999
    for variant in variants:
        vname = variant["name"]
        vals = [all_results[c][vname] for c in all_results if vname in all_results[c]]
        if vals:
            avg_sharpe = np.mean([r["sharpe"] for r in vals])
            if avg_sharpe > best_sharpe:
                best_sharpe = avg_sharpe
                best_variant = vname

    if best_variant:
        print(f"  Best: {best_variant} (Avg Sharpe={best_sharpe:.2f})")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
