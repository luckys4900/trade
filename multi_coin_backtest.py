# -*- coding: utf-8 -*-
"""
Multi-Coin Pro Strategy Backtest
=================================
Hyperliquid対応アルトコイン × プロトレーダー戦略 のマトリクス検証

検証戦略 (全て出典明記):
1. RSI2 Mean Reversion (Larry Connors)
2. Connors RSI 3-component (Larry Connors)
3. Momentum Breakout 25-bar (QuantifiedStrategies BTC実証)
4. RSI Momentum Crypto (QS "RSI momentum works on crypto")
5. EMA Pullback (Trend Following)
6. Bollinger Band Squeeze Breakout (John Bollinger)
7. Inside Bar Breakout (Al Brooks Price Action)
8. VWAP Confluence Scalp (Institutional)
"""

import os, sys, json, glob, argparse, numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

# =============================================================================
# Strategy Parameters (all sourced from pro traders)
# =============================================================================

# S1: RSI2 Mean Reversion - Larry Connors "Short Term Trading Strategies That Work"
S1_RSI2_ENTRY = 10
S1_RSI2_EXIT = 90
S1_TREND_EMA = 200

# S2: Connors RSI - Larry Connors
S2_CRSI_ENTRY = 15
S2_CRSI_EXIT = 85
S2_TREND_EMA = 200

# S3: Momentum Breakout - QS BTC backtest (246 trades, CAGR 46%, PF 2.0)
S3_MOM_LOOKBACK = 25
S3_MOM_EXIT = 10
S3_TREND_EMA = 55

# S4: RSI Momentum Crypto - QS "RSI momentum works on crypto"
S4_RSI_ENTRY = 55
S4_RSI_EXIT = 45
S4_TREND_EMA = 55

# S5: EMA Pullback - Trend Following
S5_EMA_FAST = 21
S5_EMA_SLOW = 55
S5_RSI_ENTRY = 45
S5_RSI_EXIT = 65
S5_ATR_SL = 2.0
S5_MAX_HOLD = 15

# S6: Bollinger Band Squeeze - John Bollinger
S6_BB_PERIOD = 20
S6_BB_STD = 2.0
S6_SQUEEZE_PCT = 0.10  # BB width < 10% of price
S6_TP_MULT = 3.0
S6_MAX_HOLD = 20

# S7: Inside Bar Breakout - Al Brooks Price Action
S7_LOOKBACK = 10
S7_MAX_HOLD = 10

# S8: VWAP Confluence - Institutional
S8_VWAP_PERIOD = 20
S8_RSI_PERIOD = 14
S8_RSI_ENTRY = 40
S8_RSI_EXIT = 60
S8_MAX_HOLD = 15

# Shared
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


# =============================================================================
# Data Loading
# =============================================================================

def load_csv(path):
    """Load OHLCV CSV"""
    if not os.path.exists(path):
        return None
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
    needed = ['open', 'high', 'low', 'close', 'volume']
    if not all(c in df.columns for c in needed):
        return None
    df = df[needed].astype(float)
    df = df.sort_index()
    return df


# =============================================================================
# Indicators
# =============================================================================

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


def prepare_indicators(df):
    """Compute all indicators needed by all strategies"""
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["atr14"] = compute_atr(df, 14)
    df["rsi2"] = compute_rsi(df["close"], 2)
    df["rsi14"] = compute_rsi(df["close"], 14)
    df["high_25"] = df["high"].rolling(25).max()
    df["low_10"] = df["low"].rolling(10).min()

    # Connors RSI
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

    # Bollinger Bands
    df["bb_mid"] = df["close"].rolling(S6_BB_PERIOD).mean()
    bb_std = df["close"].rolling(S6_BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"] + S6_BB_STD * bb_std
    df["bb_lower"] = df["bb_mid"] - S6_BB_STD * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # Inside Bar
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))

    # VWAP
    df["vwap"] = compute_vwap(df, S8_VWAP_PERIOD)

    return df


# =============================================================================
# Signal Generation
# =============================================================================

def generate_signals(df):
    df = prepare_indicators(df)

    # S1: RSI2 Mean Reversion
    df["s1_long"] = (df["rsi2"] < S1_RSI2_ENTRY) & (df["close"] > df["ema200"])
    df["s1_exit"] = df["rsi2"] > S1_RSI2_EXIT

    # S2: Connors RSI
    df["s2_long"] = (df["connors_rsi"] < S2_CRSI_ENTRY) & (df["close"] > df["ema200"])
    df["s2_exit"] = df["connors_rsi"] > S2_CRSI_EXIT

    # S3: Momentum Breakout
    df["s3_long"] = (df["close"] >= df["high_25"].shift(1)) & (df["close"] > df["ema55"])
    df["s3_exit"] = df["close"] <= df["low_10"].shift(1)

    # S4: RSI Momentum
    df["s4_long"] = (df["rsi14"] > S4_RSI_ENTRY) & (df["close"] > df["ema55"])
    df["s4_exit"] = df["rsi14"] < S4_RSI_EXIT

    # S5: EMA Pullback
    df["s5_long"] = (
        (df["close"] > df["ema55"]) &
        (df["ema21"] > df["ema55"]) &
        (df["rsi14"] < S5_RSI_ENTRY)
    )
    df["s5_exit"] = df["rsi14"] > S5_RSI_EXIT

    # S6: BB Squeeze Breakout
    squeeze = df["bb_width"] < df["bb_width"].rolling(50).quantile(0.10)
    df["s6_long"] = squeeze & (df["close"] > df["bb_upper"].shift(1))
    df["s6_exit"] = (df["close"] < df["bb_mid"])

    # S7: Inside Bar Breakout
    df["s7_long"] = df["inside_bar"].shift(1) & (df["close"] > df["high"].shift(2))
    df["s7_exit"] = df["close"] < df["low"].rolling(S7_LOOKBACK).min().shift(1)

    # S8: VWAP Confluence
    df["s8_long"] = (
        (df["close"] > df["vwap"]) &
        (df["rsi14"] > S8_RSI_ENTRY) &
        (df["rsi14"].shift(1) <= S8_RSI_ENTRY)
    )
    df["s8_exit"] = df["rsi14"] > S8_RSI_EXIT

    return df


# =============================================================================
# Backtest Engine
# =============================================================================

def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    return (entry - exit_px) * sz - notional * comm


def run_backtest(df, strat_name, long_col, exit_col, use_atr_sl=False, atr_sl_mult=0, max_hold=999):
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
                trades.append(Trade(ts_in, ts, "LONG", strat_name, entry, px, sz, pnl,
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
                trades.append(Trade(ts_in, ts, "LONG", strat_name, entry, exit_px, sz, pnl,
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
        trades.append(Trade(ts_in, ts, "LONG", strat_name, entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


def analyze(trades, eq):
    if not trades:
        return None
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(trades) * 100
    avg_w = np.mean(wins) if wins else 0
    avg_l = np.mean(losses) if losses else 0
    pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')

    eq_arr = np.array(eq)
    peak = np.maximum.accumulate(eq_arr)
    dd = (peak - eq_arr) / peak
    max_dd = np.max(dd) * 100

    final = eq[-1] if eq else INITIAL_CASH
    n = len(eq)
    years = n / (365 * 6)
    cagr = ((final / INITIAL_CASH) ** (1/max(years, 0.01)) - 1) * 100

    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(365*6) if np.std(rets) > 0 else 0

    return {
        "trades": len(trades),
        "win_rate": round(wr, 1),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "profit_factor": round(pf, 2) if pf != float('inf') else "INF",
        "total_pnl": round(sum(pnls), 2),
        "cagr": round(cagr, 1),
        "max_dd": round(max_dd, 1),
        "sharpe": round(sharpe, 2),
        "final_eq": round(final, 2),
    }


# =============================================================================
# Main
# =============================================================================

STRATEGIES = [
    {"name": "RSI2 MeanRev (Connors)", "long": "s1_long", "exit": "s1_exit", "atr": False, "hold": 20},
    {"name": "Connors RSI (3-comp)", "long": "s2_long", "exit": "s2_exit", "atr": False, "hold": 20},
    {"name": "Momentum Breakout (Turtle)", "long": "s3_long", "exit": "s3_exit", "atr": False, "hold": 999},
    {"name": "RSI Momentum (Crypto)", "long": "s4_long", "exit": "s4_exit", "atr": False, "hold": 30},
    {"name": "EMA Pullback (Trend)", "long": "s5_long", "exit": "s5_exit", "atr": True, "atr_m": S5_ATR_SL, "hold": S5_MAX_HOLD},
    {"name": "BB Squeeze Breakout", "long": "s6_long", "exit": "s6_exit", "atr": False, "hold": S6_MAX_HOLD},
    {"name": "Inside Bar Breakout (Brooks)", "long": "s7_long", "exit": "s7_exit", "atr": False, "hold": S7_MAX_HOLD},
    {"name": "VWAP Confluence (Inst)", "long": "s8_long", "exit": "s8_exit", "atr": False, "hold": S8_MAX_HOLD},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", default="data")
    parser.add_argument("--cash", type=float, default=10000.0)
    parser.add_argument("--output", default="backtest_results_multi.json")
    args = parser.parse_args()

    global INITIAL_CASH
    INITIAL_CASH = args.cash

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.datadir)
    files = sorted(glob.glob(os.path.join(data_dir, "*_4h_*.csv")))
    # Exclude BTC
    files = [f for f in files if "BTC" not in os.path.basename(f)]

    print(f"\n{'#'*70}")
    print(f"  Multi-Coin Pro Strategy Backtest")
    print(f"  Coins: {len(files)}, Strategies: {len(STRATEGIES)}")
    print(f"{'#'*70}")

    all_results = {}

    for fpath in files:
        coin = os.path.basename(fpath).replace("_4h_", " ").replace(".csv", "").replace("_USDCUSDC", "").replace("_365d", "")
        print(f"\n  [{coin}] Loading...")
        df = load_csv(fpath)
        if df is None or len(df) < 100:
            print(f"    SKIP: insufficient data ({len(df) if df is not None else 0} bars)")
            continue

        print(f"    {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
        df = generate_signals(df)

        coin_results = {}
        for s in STRATEGIES:
            print(f"    Running {s['name']}...", end=" ", flush=True)
            trades, eq = run_backtest(
                df, s["name"], s["long"], s["exit"],
                use_atr_sl=s.get("atr", False),
                atr_sl_mult=s.get("atr_m", 0),
                max_hold=s.get("hold", 999)
            )
            r = analyze(trades, eq)
            if r:
                coin_results[s["name"]] = r
                wr = r["win_rate"]
                pf = r["profit_factor"]
                print(f"Trades={r['trades']}, WR={wr}%, PF={pf}")
            else:
                print("No trades")

        all_results[coin] = coin_results

    # Save results
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.output)
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": str(datetime.utcnow()),
            "initial_cash": INITIAL_CASH,
            "results": all_results
        }, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")

    # Summary table
    print(f"\n\n{'='*100}")
    print(f"  FULL RESULTS MATRIX")
    print(f"{'='*100}")

    # Per-strategy summary
    for si, s in enumerate(STRATEGIES):
        print(f"\n  --- Strategy {si+1}: {s['name']} ---")
        print(f"  {'Coin':<20} {'Trades':>6} {'WR%':>5} {'PF':>5} {'CAGR%':>6} {'MaxDD%':>6} {'Sharpe':>6} {'PnL$':>10}")
        print(f"  {'-'*75}")
        for coin, cres in sorted(all_results.items()):
            if s["name"] in cres:
                r = cres[s["name"]]
                pf_s = str(r["profit_factor"]) if isinstance(r["profit_factor"], str) else f"{r['profit_factor']:.2f}"
                print(f"  {coin:<20} {r['trades']:>6} {r['win_rate']:>4.0f}% {pf_s:>5} {r['cagr']:>5.0f}% {r['max_dd']:>5.0f}% {r['sharpe']:>6.2f} ${r['total_pnl']:>9.0f}")

    # Top performing combos
    print(f"\n\n{'='*100}")
    print(f"  TOP 10 COIN-STRATEGY COMBOS (by Sharpe)")
    print(f"{'='*100}")
    combos = []
    for coin, cres in all_results.items():
        for sn, r in cres.items():
            combos.append({"coin": coin, "strategy": sn, **r})
    combos.sort(key=lambda x: x.get("sharpe", -999), reverse=True)
    for i, c in enumerate(combos[:10]):
        pf_s = str(c["profit_factor"]) if isinstance(c["profit_factor"], str) else f"{c['profit_factor']:.2f}"
        print(f"  {i+1}. {c['coin']:>15} | {c['strategy']:<30} | WR={c['win_rate']:.0f}% PF={pf_s} CAGR={c['cagr']:.0f}% DD={c['max_dd']:.0f}% Sharpe={c['sharpe']:.2f}")

    # Viable strategies (PF>1.2, MaxDD<25%, Trades>10)
    print(f"\n\n{'='*100}")
    print(f"  VIABLE STRATEGIES (PF>1.2, MaxDD<25%, Trades>10)")
    print(f"{'='*100}")
    viable = [c for c in combos if c.get("profit_factor", 0) != "INF" and c.get("profit_factor", 0) > 1.2 and c.get("max_dd", 100) < 25 and c.get("trades", 0) > 10]
    if viable:
        for i, c in enumerate(viable[:15]):
            pf_s = str(c["profit_factor"]) if isinstance(c["profit_factor"], str) else f"{c['profit_factor']:.2f}"
            print(f"  {i+1}. {c['coin']:>15} | {c['strategy']:<30} | WR={c['win_rate']:.0f}% PF={pf_s} CAGR={c['cagr']:.0f}% DD={c['max_dd']:.0f}% Sharpe={c['sharpe']:.2f}")
    else:
        print("  No combos meet strict criteria. Showing best available:")
        for i, c in enumerate(combos[:10]):
            pf_s = str(c["profit_factor"]) if isinstance(c["profit_factor"], str) else f"{c['profit_factor']:.2f}"
            print(f"  {i+1}. {c['coin']:>15} | {c['strategy']:<30} | WR={c['win_rate']:.0f}% PF={pf_s} CAGR={c['cagr']:.0f}% DD={c['max_dd']:.0f}%")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
