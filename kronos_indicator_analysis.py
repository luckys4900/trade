"""
Kronos Contrarian Strategy - Indicator Edge Analysis
=====================================================
目的: 追加テクニカル指標をKronos Contrarian戦略に組み合わせ、
      バックテストで統計的有意な期待値改善が可能か調査する。

Phase 1: 全候補指標を計算し、各バーでのContrarian成績との相関を分析
Phase 2: 複合フィルタ条件を系統的に探索（グリッドサーチ）
Phase 3: 最良条件をIS/OOS分割で検証（データスヌーピング防止）
"""

import sys
import pathlib
import itertools
import pandas as pd
import numpy as np
from dataclasses import dataclass

sys.path.append(str(pathlib.Path(__file__).parent))
from SYSTEM import qwen_unified_live as live


def compute_extended_indicators(df, cfg):
    df = live.compute_indicators(df.copy(), cfg)
    df["return"] = df["close"].pct_change()
    df["return_next"] = df["return"].shift(-1)

    # --- Volume indicators ---
    df["vol_sma20"] = df["volume"].rolling(20).mean()
    df["vol_sma50"] = df["volume"].rolling(50).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma20"]
    df["vol_ratio50"] = df["volume"] / df["vol_sma50"]
    df["vol_pct_rank"] = df["volume"].rolling(50).rank(pct=True) * 100
    df["vol_surge"] = (df["vol_ratio"] > 1.5).astype(int)
    df["vol_dry"] = (df["vol_ratio"] < 0.5).astype(int)
    df["vol_trend"] = df["vol_sma20"] / df["vol_sma50"]

    # --- Momentum indicators ---
    df["roc_3"] = df["close"].pct_change(3) * 100
    df["roc_6"] = df["close"].pct_change(6) * 100
    df["roc_12"] = df["close"].pct_change(12) * 100

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["macd_cross_up"] = (
        (df["macd"] > df["macd_signal"])
        & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    ).astype(int)
    df["macd_cross_dn"] = (
        (df["macd"] < df["macd_signal"])
        & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
    ).astype(int)

    # --- Volatility indicators ---
    df["atr_pct"] = df["atr"] / df["close"] * 100
    df["atr_change"] = df["atr"].pct_change() * 100
    df["atr_sma20"] = df["atr"].rolling(20).mean()
    df["atr_ratio"] = df["atr"] / df["atr_sma20"]

    # BB Width
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100
    df["bb_pos"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    df["bb_pos"] = df["bb_pos"].clip(0, 1)

    # --- Trend strength ---
    df["adx"] = df.get("adx", pd.Series(0, index=df.index))
    df["ema_spread"] = (df["ema_f"] - df["ema_s"]) / df["close"] * 100

    # --- Candle pattern features ---
    df["body"] = abs(df["close"] - df["open"]) / df["close"] * 100
    df["upper_shadow"] = (
        (df["high"] - df[["close", "open"]].max(axis=1)) / df["close"] * 100
    )
    df["lower_shadow"] = (
        (df[["close", "open"]].min(axis=1) - df["low"]) / df["close"] * 100
    )
    df["range_pct"] = (df["high"] - df["low"]) / df["close"] * 100

    # --- Support/Resistance proximity ---
    df["high_20"] = df["high"].rolling(20).max()
    df["low_20"] = df["low"].rolling(20).min()
    df["dist_from_high20"] = (df["high_20"] - df["close"]) / df["close"] * 100
    df["dist_from_low20"] = (df["close"] - df["low_20"]) / df["close"] * 100
    df["range_position"] = (df["close"] - df["low_20"]) / (df["high_20"] - df["low_20"])

    # --- Consecutive direction ---
    df["dir_bar"] = np.where(df["close"] > df["open"], 1, -1)
    streak = []
    cur = 0
    for d in df["dir_bar"]:
        cur = cur + 1 if d == (cur / abs(cur) if cur != 0 else 0) or cur == 0 else d
        if len(streak) == 0:
            cur = d
        elif d == (1 if streak[-1] > 0 else -1):
            cur = streak[-1] + d
        else:
            cur = d
        streak.append(cur)
    df["candle_streak"] = streak

    # --- RSI divergence (simplified) ---
    df["rsi_slope"] = df["rsi"].diff(3)
    df["price_slope"] = df["close"].diff(3)
    df["bearish_div"] = ((df["price_slope"] > 0) & (df["rsi_slope"] < 0)).astype(int)
    df["bullish_div"] = ((df["price_slope"] < 0) & (df["rsi_slope"] > 0)).astype(int)

    df.dropna(subset=["atr", "rsi", "vol_ratio", "atr_pct"], inplace=True)
    return df


def run_backtest(
    df_sub, kronos_map, start_bal=200_000.0, sl_mult=2.0, tp_mult=4.0, max_hold=8
):
    """Simplified full-fidelity backtest returning trade list"""
    fee_rate = 0.00035
    slippage = 0.001
    balance = start_bal
    pool_pct = 0.70
    risk_pct = 0.04
    pos_cap_pct = 0.30

    trades = []
    pos = None

    for i in range(len(df_sub)):
        row = df_sub.iloc[i]
        high, low, close = row["high"], row["low"], row["close"]
        atr = row["atr"]

        if pos is not None:
            held = i - pos["entry_bar"]
            if held >= max_hold:
                fill = close * (1 - slippage if pos["side"] == "LONG" else 1 + slippage)
                fee = pos["size"] * fill * fee_rate
                balance -= fee
                pnl = (
                    (fill - pos["entry_px"]) * pos["size"]
                    if pos["side"] == "LONG"
                    else (pos["entry_px"] - fill) * pos["size"]
                )
                trades.append(
                    {
                        "bar": pos["entry_bar"],
                        "exit_bar": i,
                        "side": pos["side"],
                        "pnl": pnl,
                        "fee": fee,
                        "reason": "MAX_HOLD",
                    }
                )
                pos = None
            elif pos["side"] == "LONG":
                if low <= pos["stop"]:
                    fill = pos["stop"]
                    fee = pos["size"] * fill * fee_rate
                    balance -= fee
                    pnl = (fill - pos["entry_px"]) * pos["size"]
                    trades.append(
                        {
                            "bar": pos["entry_bar"],
                            "exit_bar": i,
                            "side": pos["side"],
                            "pnl": pnl,
                            "fee": fee,
                            "reason": "SL",
                        }
                    )
                    pos = None
                elif high >= pos["tp"]:
                    fill = pos["tp"]
                    fee = pos["size"] * fill * fee_rate
                    balance -= fee
                    pnl = (fill - pos["entry_px"]) * pos["size"]
                    trades.append(
                        {
                            "bar": pos["entry_bar"],
                            "exit_bar": i,
                            "side": pos["side"],
                            "pnl": pnl,
                            "fee": fee,
                            "reason": "TP",
                        }
                    )
                    pos = None
            else:
                if high >= pos["stop"]:
                    fill = pos["stop"]
                    fee = pos["size"] * fill * fee_rate
                    balance -= fee
                    pnl = (pos["entry_px"] - fill) * pos["size"]
                    trades.append(
                        {
                            "bar": pos["entry_bar"],
                            "exit_bar": i,
                            "side": pos["side"],
                            "pnl": pnl,
                            "fee": fee,
                            "reason": "SL",
                        }
                    )
                    pos = None
                elif low <= pos["tp"]:
                    fill = pos["tp"]
                    fee = pos["size"] * fill * fee_rate
                    balance -= fee
                    pnl = (pos["entry_px"] - fill) * pos["size"]
                    trades.append(
                        {
                            "bar": pos["entry_bar"],
                            "exit_bar": i,
                            "side": pos["side"],
                            "pnl": pnl,
                            "fee": fee,
                            "reason": "TP",
                        }
                    )
                    pos = None

        if pos is not None:
            continue
        if i not in kronos_map:
            continue

        pred_dir = kronos_map[i]
        if atr <= 0 or np.isnan(atr):
            continue

        side = "SHORT" if pred_dir == 1 else "LONG"
        pool = balance * pool_pct
        risk_budget = pool * risk_pct
        pos_cap = pool * pos_cap_pct
        sl_dist = sl_mult * atr
        sz = min(risk_budget / sl_dist, pos_cap / close)
        sz = round(sz, 4)
        if sz <= 0:
            continue

        entry_px = close * (1 + slippage if side == "LONG" else 1 - slippage)
        fee = sz * entry_px * fee_rate
        balance -= fee

        sl = entry_px - sl_dist if side == "LONG" else entry_px + sl_dist
        tp = entry_px + tp_mult * atr if side == "LONG" else entry_px - tp_mult * atr

        pos = {
            "side": side,
            "size": sz,
            "entry_px": entry_px,
            "stop": sl,
            "tp": tp,
            "entry_bar": i,
        }

    if pos is not None:
        close = df_sub.iloc[-1]["close"]
        fill = close * (1 - slippage if pos["side"] == "LONG" else 1 + slippage)
        fee = pos["size"] * fill * fee_rate
        balance -= fee
        pnl = (
            (fill - pos["entry_px"]) * pos["size"]
            if pos["side"] == "LONG"
            else (pos["entry_px"] - fill) * pos["size"]
        )
        trades.append(
            {
                "bar": pos["entry_bar"],
                "exit_bar": len(df_sub) - 1,
                "side": pos["side"],
                "pnl": pnl,
                "fee": fee,
                "reason": "END",
            }
        )

    return trades


def calc_metrics(trades):
    if not trades:
        return {
            "n": 0,
            "pnl": 0,
            "wr": 0,
            "pf": 0,
            "avg": 0,
            "fees": 0,
            "tp_n": 0,
            "sl_n": 0,
            "mh_n": 0,
        }
    pnls = [t["pnl"] for t in trades]
    fees = sum(t["fee"] for t in trades)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    return {
        "n": len(trades),
        "pnl": round(sum(pnls), 2),
        "wr": round(len(wins) / len(trades) * 100, 1),
        "pf": round(sum(wins) / sum(losses), 3) if losses else 0,
        "avg": round(sum(pnls) / len(trades), 2),
        "fees": round(fees, 2),
        "tp_n": reasons.get("TP", 0),
        "sl_n": reasons.get("SL", 0),
        "mh_n": reasons.get("MAX_HOLD", 0),
    }


def main():
    csv_path = pathlib.Path(__file__).parent / "btc_usdt_4h_unified.csv"
    raw = pd.read_csv(
        csv_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    cfg_ind = live.Config()
    df = compute_extended_indicators(raw.copy(), cfg_ind)

    preds = pd.read_csv(pathlib.Path(__file__).parent / "kronos_4h_preds_full.csv")
    kronos_bar_map = {}
    for _, row in preds.iterrows():
        bar_idx = int(row["bar"])
        if 0 <= bar_idx < len(df):
            kronos_bar_map[bar_idx] = int(row["dir"])

    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    km_is = {k: v for k, v in kronos_bar_map.items() if k < split_idx}
    km_oos = {k - split_idx: v for k, v in kronos_bar_map.items() if k >= split_idx}

    print(
        f"Total: {len(df)} bars | IS: {len(df_is)} ({df_is.index[0].date()} ~ {df_is.index[-1].date()}) | OOS: {len(df_oos)} ({df_oos.index[0].date()} ~ {df_oos.index[-1].date()})"
    )
    print(f"Kronos: IS={len(km_is)} OOS={len(km_oos)}")
    print()

    # ======================================================================
    # PHASE 1: Baseline + single-indicator filter analysis (IS only)
    # ======================================================================
    print("=" * 120)
    print("PHASE 1: SINGLE-INDICATOR FILTER ANALYSIS (In-Sample)")
    print("=" * 120)

    indicator_filters = {
        "Baseline (no filter)": None,
        # Volume filters
        "vol_ratio > 1.2 (high vol)": lambda r: r["vol_ratio"] > 1.2,
        "vol_ratio > 1.5 (surge)": lambda r: r["vol_ratio"] > 1.5,
        "vol_ratio < 0.8 (low vol)": lambda r: r["vol_ratio"] < 0.8,
        "vol_ratio < 0.6 (dry)": lambda r: r["vol_ratio"] < 0.6,
        "vol_pct_rank > 60": lambda r: r["vol_pct_rank"] > 60,
        "vol_pct_rank > 70": lambda r: r["vol_pct_rank"] > 70,
        "vol_pct_rank < 30": lambda r: r["vol_pct_rank"] < 30,
        "vol_trend > 1.0 (rising)": lambda r: r["vol_trend"] > 1.0,
        "vol_trend > 1.1 (strong rise)": lambda r: r["vol_trend"] > 1.1,
        # ATR filters
        "atr_ratio > 1.0 (expanding)": lambda r: r["atr_ratio"] > 1.0,
        "atr_ratio > 1.2 (high vol)": lambda r: r["atr_ratio"] > 1.2,
        "atr_ratio < 0.8 (low vol)": lambda r: r["atr_ratio"] < 0.8,
        "atr_pct < 2.0": lambda r: r["atr_pct"] < 2.0,
        "atr_pct > 2.5": lambda r: r["atr_pct"] > 2.5,
        # BB position
        "bb_pos < 0.3 (near lower)": lambda r: r["bb_pos"] < 0.3,
        "bb_pos > 0.7 (near upper)": lambda r: r["bb_pos"] > 0.7,
        "bb_pos 0.3-0.7 (mid)": lambda r: 0.3 <= r["bb_pos"] <= 0.7,
        "bb_width > median": lambda r: r["bb_width"] > r.get("_bb_width_med", 0),
        "bb_width < median": lambda r: r["bb_width"] < r.get("_bb_width_med", 0),
        # RSI
        "RSI 40-55": lambda r: 40 <= r["rsi"] <= 55,
        "RSI 55-70": lambda r: 55 <= r["rsi"] <= 70,
        "RSI > 55": lambda r: r["rsi"] > 55,
        "RSI < 45": lambda r: r["rsi"] < 45,
        "RSI > 55 & UPTREND": lambda r: r["rsi"] > 55 and r["ocpm_trend"] == "UPTREND",
        # Trend + Volume
        "UPTREND & vol_ratio>1.2": lambda r: (
            r["ocpm_trend"] == "UPTREND" and r["vol_ratio"] > 1.2
        ),
        "DOWNTREND & vol_ratio>1.2": lambda r: (
            r["ocpm_trend"] == "DOWNTREND" and r["vol_ratio"] > 1.2
        ),
        # MACD
        "MACD > signal (bullish)": lambda r: r["macd"] > r["macd_signal"],
        "MACD < signal (bearish)": lambda r: r["macd"] < r["macd_signal"],
        "MACD cross up": lambda r: r["macd_cross_up"] == 1,
        "MACD cross dn": lambda r: r["macd_cross_dn"] == 1,
        # Momentum
        "ROC_6 > 0": lambda r: r["roc_6"] > 0,
        "ROC_6 < 0": lambda r: r["roc_6"] < 0,
        "ROC_6 > 2%": lambda r: r["roc_6"] > 2,
        "ROC_6 < -2%": lambda r: r["roc_6"] < -2,
        # ADX
        "ADX > 25 (strong trend)": lambda r: r["adx"] > 25,
        "ADX < 20 (weak trend)": lambda r: r["adx"] < 20,
        # Range position
        "range_pos > 0.7 (near high)": lambda r: r["range_position"] > 0.7,
        "range_pos < 0.3 (near low)": lambda r: r["range_position"] < 0.3,
        "range_pos 0.3-0.7": lambda r: 0.3 <= r["range_position"] <= 0.7,
        # Divergence
        "Bearish divergence": lambda r: r["bearish_div"] == 1,
        "Bullish divergence": lambda r: r["bullish_div"] == 1,
        # Candle
        "body > 0.5%": lambda r: r["body"] > 0.5,
        "body < 0.2% (doji)": lambda r: r["body"] < 0.2,
    }

    bb_width_med = df_is["bb_width"].median()

    results_is = []
    for name, filt_fn in indicator_filters.items():
        if filt_fn is None:
            filtered_km = km_is
        else:
            filtered_km = {}
            for k, v in km_is.items():
                if k < len(df_is):
                    row = df_is.iloc[k]
                    row_dict = row.to_dict()
                    row_dict["_bb_width_med"] = bb_width_med
                    try:
                        if filt_fn(row_dict):
                            filtered_km[k] = v
                    except Exception:
                        continue

        trades = run_backtest(df_is, filtered_km)
        m = calc_metrics(trades)
        m["name"] = name
        m["filtered_signals"] = len(filtered_km)
        results_is.append(m)

    print(
        "{:<40} {:>4} {:>8} {:>12} {:>6} {:>6} {:>8} {:>3} {:>3} {:>3}".format(
            "Filter", "N", "Signals", "PnL", "WR", "PF", "Avg", "TP", "SL", "MH"
        )
    )
    print("-" * 120)
    for m in sorted(results_is, key=lambda x: x["pnl"], reverse=True):
        print(
            f"{m['name']:<40} {m['n']:>4} {m['filtered_signals']:>8} {m['pnl']:>+12,.2f} {m['wr']:>5.1f}% {m['pf']:>6.3f} {m['avg']:>+8.2f} {m['tp_n']:>3} {m['sl_n']:>3} {m['mh_n']:>3}"
        )

    # ======================================================================
    # PHASE 2: Top-5 combo exploration (IS only)
    # ======================================================================
    print()
    print("=" * 120)
    print("PHASE 2: MULTI-INDICATOR COMBO ANALYSIS (In-Sample)")
    print("=" * 120)

    top_filters = [
        m
        for m in results_is
        if m["pnl"] > -5000 and m["n"] >= 20 and m["name"] != "Baseline (no filter)"
    ]
    top_filters.sort(key=lambda x: x["pnl"], reverse=True)
    top_names = [t["name"] for t in top_filters[:10]]

    combo_results = []
    for r in range(2, min(4, len(top_names) + 1)):
        for combo in itertools.combinations(top_names, r):
            fns = [indicator_filters[n] for n in combo if n in indicator_filters]
            if not fns:
                continue

            filtered_km = {}
            for k, v in km_is.items():
                if k >= len(df_is):
                    continue
                row = df_is.iloc[k]
                row_dict = row.to_dict()
                row_dict["_bb_width_med"] = bb_width_med
                try:
                    if all(fn(row_dict) for fn in fns):
                        filtered_km[k] = v
                except Exception:
                    continue

            trades = run_backtest(df_is, filtered_km)
            m = calc_metrics(trades)
            m["name"] = " & ".join(combo)
            m["filtered_signals"] = len(filtered_km)
            combo_results.append(m)

    combo_results.sort(key=lambda x: x["pnl"], reverse=True)
    print(
        "{:<80} {:>4} {:>8} {:>12} {:>6} {:>6} {:>8} {:>3} {:>3} {:>3}".format(
            "Combo", "N", "Signals", "PnL", "WR", "PF", "Avg", "TP", "SL", "MH"
        )
    )
    print("-" * 150)
    for m in combo_results[:30]:
        if m["n"] >= 10:
            print(
                f"{m['name'][:80]:<80} {m['n']:>4} {m['filtered_signals']:>8} {m['pnl']:>+12,.2f} {m['wr']:>5.1f}% {m['pf']:>6.3f} {m['avg']:>+8.2f} {m['tp_n']:>3} {m['sl_n']:>3} {m['mh_n']:>3}"
            )

    # ======================================================================
    # PHASE 3: OOS validation of top combos
    # ======================================================================
    print()
    print("=" * 120)
    print("PHASE 3: OUT-OF-SAMPLE VALIDATION (locked parameters)")
    print("=" * 120)

    candidates = combo_results[:15] + [
        m for m in results_is if m["name"] == "Baseline (no filter)"
    ]
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c["name"] not in seen and c["n"] >= 15:
            seen.add(c["name"])
            unique_candidates.append(c)

    print(
        "\n{:80} {:>4} {:>12} {:>6} {:>6} {:>8}".format(
            "Strategy", "N", "PnL", "WR", "PF", "Avg"
        )
    )
    print("-" * 120)

    oos_results = []
    for cand in unique_candidates[:10]:
        name = cand["name"]
        if name == "Baseline (no filter)":
            trades_oos = run_backtest(df_oos, km_oos)
        else:
            if " & " in name:
                parts = name.split(" & ")
                fns = [indicator_filters[p] for p in parts if p in indicator_filters]
            else:
                fns = [indicator_filters[name]] if name in indicator_filters else []

            if not fns:
                continue

            filtered_km_oos = {}
            for k, v in km_oos.items():
                if k >= len(df_oos):
                    continue
                row = df_oos.iloc[k]
                row_dict = row.to_dict()
                row_dict["_bb_width_med"] = df_oos["bb_width"].median()
                try:
                    if all(fn(row_dict) for fn in fns):
                        filtered_km_oos[k] = v
                except Exception:
                    continue

            trades_oos = run_backtest(df_oos, filtered_km_oos)

        m = calc_metrics(trades_oos)
        m["name"] = name
        oos_results.append(m)

        is_match = next((r for r in results_is if r["name"] == name), None)
        is_pnl = is_match["pnl"] if is_match else 0
        delta = m["pnl"] - is_pnl

        print(
            f"  {name[:78]:<78} {m['n']:>4} {m['pnl']:>+12,.2f} {m['wr']:>5.1f}% {m['pf']:>6.3f} {m['avg']:>+8.2f}  (IS PnL: {is_pnl:>+10,.2f}  Delta: {delta:>+10,.2f})"
        )

    # ======================================================================
    # VERDICT
    # ======================================================================
    print()
    print("=" * 120)
    print("VERDICT")
    print("=" * 120)

    baseline_oos = next(
        (r for r in oos_results if r["name"] == "Baseline (no filter)"), None
    )
    if baseline_oos:
        print(
            f"\nBaseline OOS: PnL={baseline_oos['pnl']:>+,.2f}  WR={baseline_oos['wr']}%  PF={baseline_oos['pf']}  N={baseline_oos['n']}"
        )

    improvements = [
        r
        for r in oos_results
        if r["name"] != "Baseline (no filter)"
        and r["pnl"] > (baseline_oos["pnl"] if baseline_oos else 0)
    ]
    if improvements:
        print(f"\nFilters that BEAT baseline in OOS ({len(improvements)} found):")
        for r in sorted(improvements, key=lambda x: x["pnl"], reverse=True)[:5]:
            print(
                f"  {r['name'][:70]:<70} PnL={r['pnl']:>+10,.2f}  WR={r['wr']}%  PF={r['pf']}  N={r['n']}"
            )
    else:
        print(
            "\nNO filter beat baseline in OOS. Additional indicators do not provide reliable edge."
        )

    print("\nKey metrics to check:")
    print("  - OOS PnL > Baseline OOS PnL => marginal improvement")
    print("  - OOS N >= 30 => statistically meaningful sample")
    print("  - OOS WR > 50% AND PF > 1.0 => positive expectancy")
    print("  - IS->OOS consistency => not overfit")


if __name__ == "__main__":
    main()
