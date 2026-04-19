# -*- coding: utf-8 -*-
"""
Pro Strategy Backtest - BTC 4h/1h
===================================
エビデンスベースのプロトレーダー戦略をBTCで検証
出典: QuantifiedStrategies.com, Larry Connors, Curtis Faith

検証戦略:
1. RSI2 Mean Reversion (Larry Connors)
2. Connors RSI (3-component)
3. Momentum Breakout (Turtle-style 25-bar)
4. RSI Momentum (Crypto-specific)
5. EMA Pullback (Trend Following)
"""

import os, sys, argparse, datetime as dt, logging, numpy as np, pandas as pd
from pathlib import Path
from dataclasses import dataclass

# =============================================================================
# Strategy Parameters
# =============================================================================

# --- Strategy 1: RSI2 Mean Reversion (Larry Connors) ---
# 出典: "Short Term Trading Strategies That Work" - Larry Connors
# 株式で91%勝率実証。BTCでの再現性を検証
RSI2_PERIOD = 2
RSI2_ENTRY_LONG = 10      # RSI2 < 10 でロング
RSI2_EXIT_LONG = 90       # RSI2 > 90 で決済
RSI2_TREND_FILTER = True  # 長期トレンドフィルター使用
RSI2_TREND_EMA = 200      # 200EMAより上でのみロング

# --- Strategy 2: Connors RSI (3-component) ---
# 出典: Larry Connors "ConnorsRSI"
# RSI + UpDownLength + ROC の複合
CRSI_RSI_PERIOD = 3
CRSI_STREAK_PERIOD = 2
CRSI_ROC_PERIOD = 100
CRSI_ENTRY_LONG = 15      # ConnorsRSI < 15 でロング
CRSI_EXIT_LONG = 85       # ConnorsRSI > 85 で決済
CRSI_TREND_EMA = 200

# --- Strategy 3: Momentum Breakout (Turtle-style) ---
# 出典: QuantifiedStrategies.com BTC backtest実証済み
# 246トレード, CAGR 46%, PF 2.0, MaxDD 23%
MOMENTUM_LOOKBACK = 25    # 25バー高値でエントリー
MOMENTUM_EXIT_LOOKBACK = 10  # 10バー安値で決済
MOMENTUM_TREND_FILTER = True
MOMENTUM_TREND_EMA = 55

# --- Strategy 4: RSI Momentum (Crypto-specific) ---
# 出典: QuantifiedStrategies.com "RSI momentum works on crypto"
# RSIが50より上でモメンタム、ロング
RSI_MOM_PERIOD = 14
RSI_MOM_ENTRY = 55        # RSI > 55 でモメンタム確認
RSI_MOM_EXIT = 45         # RSI < 45 で決済
RSI_MOM_TREND_EMA = 55

# --- Strategy 5: EMA Pullback (Trend Following) ---
# 出典: OCPM改良版。EMA55トレンド中のEMA21プルバック
EMA_PULL_FAST = 21
EMA_PULL_SLOW = 55
EMA_PULL_RSI_PERIOD = 14
EMA_PULL_RSI_ENTRY = 45   # プルバックでRSIが45以下
EMA_PULL_RSI_EXIT = 65    # RSIが65以上で決済
EMA_PULL_ATR_PERIOD = 14
EMA_PULL_ATR_SL = 2.0
EMA_PULL_ATR_TP = 4.0
EMA_PULL_MAX_HOLD = 15

# --- Shared ---
INITIAL_CASH = 10000.0
COMM_PCT = 0.0005
RISK_PCT = 0.02
MAX_POS_PCT = 0.40
MAX_LOSSES = 5
COOLDOWN = 3
DD_HALT = 0.20


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
    """Load OHLCV CSV with flexible column names"""
    if not os.path.exists(path):
        print(f"  [WARN] {path} not found")
        return None
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    # Normalize column names
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl == 'open' or cl == 'o': col_map[c] = 'open'
        elif cl == 'high' or cl == 'h': col_map[c] = 'high'
        elif cl == 'low' or cl == 'l': col_map[c] = 'low'
        elif cl == 'close' or cl == 'c': col_map[c] = 'close'
        elif cl == 'volume' or cl == 'v': col_map[c] = 'volume'
    df = df.rename(columns=col_map)
    df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df = df.sort_index()
    print(f"  Loaded {path}: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return df


# =============================================================================
# Indicator Computation
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


def compute_connors_rsi(df, rsi_period=3, streak_period=2, roc_period=100):
    """Connors RSI = (RSI(close) + RSI(streak) + ROC_percentile) / 3"""
    # Component 1: RSI of close
    rsi_close = compute_rsi(df["close"], rsi_period)

    # Component 2: RSI of streak (consecutive up/down days)
    streak = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] + 1 if streak.iloc[i-1] > 0 else 1
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            streak.iloc[i] = streak.iloc[i-1] - 1 if streak.iloc[i-1] < 0 else -1
    rsi_streak = compute_rsi(streak, streak_period)

    # Component 3: Percentile rank of ROC
    roc = df["close"].pct_change(roc_period) * 100
    roc_pct = roc.rolling(roc_period).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False)

    connors_rsi = (rsi_close + rsi_streak + roc_pct) / 3
    return connors_rsi


def compute_indicators(df):
    """Compute all indicators for all strategies"""
    # EMA
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema55"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # ATR
    df["atr14"] = compute_atr(df, 14)

    # RSI variants
    df["rsi2"] = compute_rsi(df["close"], 2)
    df["rsi14"] = compute_rsi(df["close"], 14)

    # Connors RSI
    df["connors_rsi"] = compute_connors_rsi(df)

    # Momentum signals
    df["high_25"] = df["high"].rolling(25).max()
    df["low_10"] = df["low"].rolling(10).min()
    df["high_20"] = df["high"].rolling(20).max()

    return df


# =============================================================================
# Strategy Signal Generation
# =============================================================================

def generate_signals(df):
    """Generate entry/exit signals for all 5 strategies"""
    df = compute_indicators(df)

    # --- Strategy 1: RSI2 Mean Reversion ---
    if RSI2_TREND_FILTER:
        df["s1_long"] = (df["rsi2"] < RSI2_ENTRY_LONG) & (df["close"] > df["ema200"])
        df["s1_exit"] = df["rsi2"] > RSI2_EXIT_LONG
    else:
        df["s1_long"] = df["rsi2"] < RSI2_ENTRY_LONG
        df["s1_exit"] = df["rsi2"] > RSI2_EXIT_LONG

    # --- Strategy 2: Connors RSI ---
    df["s2_long"] = (df["connors_rsi"] < CRSI_ENTRY_LONG) & (df["close"] > df["ema200"])
    df["s2_exit"] = df["connors_rsi"] > CRSI_EXIT_LONG

    # --- Strategy 3: Momentum Breakout (Turtle) ---
    if MOMENTUM_TREND_FILTER:
        df["s3_long"] = (df["close"] >= df["high_25"].shift(1)) & (df["close"] > df["ema55"])
        df["s3_exit"] = df["close"] <= df["low_10"].shift(1)
    else:
        df["s3_long"] = df["close"] >= df["high_25"].shift(1)
        df["s3_exit"] = df["close"] <= df["low_10"].shift(1)

    # --- Strategy 4: RSI Momentum ---
    df["s4_long"] = (df["rsi14"] > RSI_MOM_ENTRY) & (df["close"] > df["ema55"])
    df["s4_exit"] = df["rsi14"] < RSI_MOM_EXIT

    # --- Strategy 5: EMA Pullback ---
    df["s5_long"] = (
        (df["close"] > df["ema55"]) &
        (df["ema21"] > df["ema55"]) &
        (df["rsi14"] < EMA_PULL_RSI_ENTRY)
    )
    df["s5_exit"] = df["rsi14"] > EMA_PULL_RSI_EXIT

    return df


# =============================================================================
# Backtest Engine
# =============================================================================

def _pnl(side, entry, exit_px, sz, comm):
    notional = sz * exit_px
    if side == "LONG":
        return (exit_px - entry) * sz - notional * comm
    else:
        return (entry - exit_px) * sz - notional * comm


def run_backtest(df, strategy_name, long_col, exit_col, use_atr_sl=False, atr_sl_mult=0, max_hold=999, lg=None):
    """Generic backtest engine for any strategy"""
    cash = INITIAL_CASH
    peak_eq = INITIAL_CASH
    eq = []
    trades = []
    cm = COMM_PCT

    in_pos = False
    side = ""
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

        # Equity tracking
        pv = sz * px if in_pos else 0
        equity = cash + pv
        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DD_HALT:
            continue

        # Position management
        if in_pos:
            held = i - bar_in

            # Max hold exit
            if held >= max_hold:
                pnl = _pnl(side, entry, px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, side, strategy_name, entry, px, sz, pnl,
                                   (px/entry-1)*100, "TIME_EXIT", held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

            # ATR trailing stop
            elif use_atr_sl and atr and atr > 0:
                new_sl = px - atr_sl_mult * atr
                if new_sl > stop:
                    stop = new_sl
                if lo <= stop:
                    pnl = _pnl("LONG", entry, stop, sz, cm)
                    cash += sz * entry + pnl
                    trades.append(Trade(ts_in, ts, "LONG", strategy_name, entry, stop, sz, pnl,
                                       (stop/entry-1)*100, "TRAILING_STOP", held))
                    if pnl < 0:
                        loss_count += 1
                        if loss_count >= MAX_LOSSES:
                            cool_until = i + COOLDOWN
                    else:
                        loss_count = 0
                    in_pos = False

            # Signal-based exit
            elif not use_atr_sl and r.get(exit_col, False):
                pnl = _pnl(side, entry, px, sz, cm)
                cash += sz * entry + pnl
                trades.append(Trade(ts_in, ts, side, strategy_name, entry, px, sz, pnl,
                                   (px/entry-1)*100, "SIGNAL_EXIT", held))
                if pnl < 0:
                    loss_count += 1
                    if loss_count >= MAX_LOSSES:
                        cool_until = i + COOLDOWN
                else:
                    loss_count = 0
                in_pos = False

        # Entry
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
                    side = "LONG"
                    entry = px
                    ts_in = ts
                    bar_in = i
                    stop = px - (atr_sl_mult * atr if use_atr_sl and atr else px * 0.05)

    # Close remaining position
    if in_pos:
        pnl = _pnl(side, entry, px, sz, cm)
        cash += sz * entry + pnl
        trades.append(Trade(ts_in, ts, side, strategy_name, entry, px, sz, pnl,
                           (px/entry-1)*100, "END_OF_DATA", i - bar_in))

    return trades, eq


# =============================================================================
# Report Generation
# =============================================================================

def analyze_trades(trades, strategy_name, equity_curve):
    """Generate performance report"""
    if not trades:
        print(f"\n{'='*60}")
        print(f"  {strategy_name}: No trades")
        print(f"{'='*60}")
        return

    pnls = [t.pnl for t in trades]
    pnl_pct = [t.pnl_pct for t in trades]
    total_pnl = sum(pnls)
    win_trades = [p for p in pnls if p > 0]
    loss_trades = [p for p in pnls if p <= 0]
    win_rate = len(win_trades) / len(trades) * 100 if trades else 0
    avg_win = np.mean(win_trades) if win_trades else 0
    avg_loss = np.mean(loss_trades) if loss_trades else 0
    profit_factor = abs(sum(win_trades) / sum(loss_trades)) if loss_trades and sum(loss_trades) != 0 else float('inf')

    # Drawdown
    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd = np.max(dd) * 100

    # CAGR
    final_eq = equity_curve[-1] if equity_curve else INITIAL_CASH
    n_bars = len(equity_curve)
    years = n_bars / (365 * 24 / 4)  # 4h bars
    cagr = ((final_eq / INITIAL_CASH) ** (1/max(years, 0.01)) - 1) * 100

    # Sharpe (annualized)
    returns = np.diff(eq) / eq[:-1]
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(365*6) if np.std(returns) > 0 else 0

    bars_held = [t.bars for t in trades]

    print(f"\n{'='*60}")
    print(f"  {strategy_name}")
    print(f"{'='*60}")
    print(f"  Total Trades:        {len(trades)}")
    print(f"  Win Rate:            {win_rate:.1f}%")
    print(f"  Avg Win:             {avg_win:+.2f} ({avg_win/INITIAL_CASH*100:+.2f}%)")
    print(f"  Avg Loss:            {avg_loss:+.2f} ({avg_loss/INITIAL_CASH*100:+.2f}%)")
    print(f"  Profit Factor:       {profit_factor:.2f}")
    print(f"  Total PnL:           {total_pnl:+.2f} ({total_pnl/INITIAL_CASH*100:+.2f}%)")
    print(f"  CAGR:                {cagr:.1f}%")
    print(f"  Max Drawdown:        {max_dd:.1f}%")
    print(f"  Sharpe Ratio:        {sharpe:.2f}")
    print(f"  Avg Bars Held:       {np.mean(bars_held):.1f}")
    print(f"  Final Equity:        ${final_eq:,.2f}")
    print(f"{'='*60}")

    return {
        "strategy": strategy_name,
        "trades": len(trades),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "avg_bars": np.mean(bars_held),
        "final_eq": final_eq,
    }


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="btc_usdt_4h_1500d.csv", help="CSV file path")
    parser.add_argument("--cash", type=float, default=INITIAL_CASH)
    args = parser.parse_args()

    global INITIAL_CASH
    INITIAL_CASH = args.cash

    print(f"\n{'#'*60}")
    print(f"  Pro Strategy Backtest - BTC")
    print(f"{'#'*60}")
    print(f"  Data: {args.data}")
    print(f"  Initial Cash: ${INITIAL_CASH:,.2f}")

    # Load data
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.data)
    df = load_csv(data_path)
    if df is None:
        print("ERROR: Data file not found. Run ccxt_data_loader.py first.")
        sys.exit(1)

    # Generate signals
    print("\n  Computing indicators...")
    df = generate_signals(df)

    # Run all 5 strategies
    results = []

    strategies = [
        {
            "name": "1. RSI2 Mean Reversion (Connors)",
            "long_col": "s1_long",
            "exit_col": "s1_exit",
            "use_atr_sl": False,
            "max_hold": 20,
        },
        {
            "name": "2. Connors RSI (3-component)",
            "long_col": "s2_long",
            "exit_col": "s2_exit",
            "use_atr_sl": False,
            "max_hold": 20,
        },
        {
            "name": "3. Momentum Breakout (Turtle 25-bar)",
            "long_col": "s3_long",
            "exit_col": "s3_exit",
            "use_atr_sl": False,
            "max_hold": 999,
        },
        {
            "name": "4. RSI Momentum (Crypto-specific)",
            "long_col": "s4_long",
            "exit_col": "s4_exit",
            "use_atr_sl": False,
            "max_hold": 30,
        },
        {
            "name": "5. EMA Pullback (Trend Following)",
            "long_col": "s5_long",
            "exit_col": "s5_exit",
            "use_atr_sl": True,
            "atr_sl_mult": EMA_PULL_ATR_SL,
            "max_hold": EMA_PULL_MAX_HOLD,
        },
    ]

    for s in strategies:
        print(f"\n  Running: {s['name']}...")
        trades, eq = run_backtest(
            df,
            s["name"],
            s["long_col"],
            s["exit_col"],
            use_atr_sl=s.get("use_atr_sl", False),
            atr_sl_mult=s.get("atr_sl_mult", 0),
            max_hold=s.get("max_hold", 999),
        )
        r = analyze_trades(trades, s["name"], eq)
        if r:
            results.append(r)

    # Summary table
    if results:
        print(f"\n\n{'='*80}")
        print(f"  STRATEGY COMPARISON")
        print(f"{'='*80}")
        print(f"  {'Strategy':<35} {'Trades':>6} {'WR%':>6} {'PF':>6} {'CAGR%':>7} {'MaxDD%':>7} {'Sharpe':>7}")
        print(f"  {'-'*78}")
        for r in results:
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float('inf') else "INF"
            print(f"  {r['strategy']:<35} {r['trades']:>6} {r['win_rate']:>5.1f}% {pf_str:>6} {r['cagr']:>6.1f}% {r['max_dd']:>6.1f}% {r['sharpe']:>7.2f}")
        print(f"{'='*80}")

        # Recommendation
        print(f"\n  RECOMMENDATION:")
        viable = [r for r in results if r['profit_factor'] > 1.2 and r['max_dd'] < 25 and r['trades'] > 10]
        if viable:
            best = max(viable, key=lambda x: x['sharpe'])
            print(f"  => Best risk-adjusted: {best['strategy']}")
            print(f"     PF={best['profit_factor']:.2f}, Sharpe={best['sharpe']:.2f}, MaxDD={best['max_dd']:.1f}%")
        else:
            print(f"  => No strategy meets criteria (PF>1.2, MaxDD<25%, Trades>10)")
            best = max(results, key=lambda x: x['profit_factor'])
            print(f"     Highest PF: {best['strategy']} (PF={best['profit_factor']:.2f})")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
