# -*- coding: utf-8 -*-
"""
Range Mean Reversion Strategy - Backtest
"""

import os
import sys
import argparse
import datetime as dt
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass

BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
MAX_HOLD_BARS = 10
ADX_PERIOD = 14
MAX_ADX = 25.0
EMA_CONVERGE_PCT = 0.020

INITIAL_CASH = 100.0
COMMISSION_PCT = 0.0005
RISK_PCT = 0.015
MAX_POSITION_PCT = 0.40
MAX_CONSECUTIVE_LOSSES = 5
COOLDOWN_BARS = 2
DRAWDOWN_HALT_PCT = 0.15


@dataclass
class Trade:
    t_in: str
    t_out: str
    side: str
    p_in: float
    p_out: float
    sz: float
    pnl: float
    pnl_pct: float
    reason: str
    bars: int = 0


def fetch_ohlcv(days, timeframe, cache_path):
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, parse_dates=["datetime"], index_col="datetime").sort_index()
            if len(df) > 0:
                print(f"CSV cache: {cache_path} ({len(df)} bars)")
                return df
        except Exception:
            pass

    import ccxt
    print(f"Fetching BTC USDT {timeframe} from Binance ({days} days)...")
    ex = ccxt.binance({"enableRateLimit": True})
    since = ex.parse8601((dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    rows = []
    while True:
        b = ex.fetch_ohlcv("BTC/USDT", timeframe, since=since, limit=1000)
        if not b:
            break
        rows.extend(b)
        since = b[-1][0] + 1
        if len(b) < 1000:
            break
    if not rows:
        raise ValueError("No data available")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("datetime", inplace=True)
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.to_csv(cache_path)
    print(f"Saved {len(df)} bars")
    return df.sort_index()


def compute_indicators(df):
    df["bb_mid"] = df["close"].rolling(BB_PERIOD).mean()
    bb_std = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"] + BB_STD * bb_std
    df["bb_lower"] = df["bb_mid"] - BB_STD * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_width_pctile"] = df["bb_width"].rolling(50).rank(pct=True)

    df["ema_fast"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=55, adjust=False).mean()
    df["ema_converge"] = (df["ema_fast"] - df["ema_slow"]).abs() / df["close"]

    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()
    plus_dm = plus_dm.clip(lower=0).where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.clip(lower=0).where(minus_dm > plus_dm, 0)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    atr_raw = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/ADX_PERIOD, min_periods=ADX_PERIOD).mean() / atr_raw)
    minus_di = 100 * (minus_dm.ewm(alpha=1/ADX_PERIOD, min_periods=ADX_PERIOD).mean() / atr_raw)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.ewm(alpha=1/ADX_PERIOD, min_periods=ADX_PERIOD).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    df["rsi_prev"] = df["rsi"].shift(1)

    df["atr"] = atr_raw

    df["is_range"] = (
        (df["adx"] < MAX_ADX) &
        (df["ema_converge"] < EMA_CONVERGE_PCT)
    )

    df["long_entry"] = (
        df["is_range"] &
        (df["low"] <= df["bb_lower"]) &
        (df["rsi_prev"] <= RSI_OVERSOLD) &
        (df["rsi"] > df["rsi_prev"])
    ).astype(int)

    df["short_entry"] = (
        df["is_range"] &
        (df["high"] >= df["bb_upper"]) &
        (df["rsi_prev"] >= RSI_OVERBOUGHT) &
        (df["rsi"] < df["rsi_prev"])
    ).astype(int)

    return df


def _pnl(side, entry, exit_px, size, comm):
    notional = size * exit_px
    comm_cost = notional * comm
    if side == "LONG":
        return (exit_px - entry) * size - comm_cost
    else:
        return (entry - exit_px) * size - comm_cost


def run_backtest(df, lg):
    cash = INITIAL_CASH
    in_pos = False
    side = ""
    entry_px = 0.0
    entry_ts = ""
    entry_bar = 0
    size = 0.0
    stop = 0.0
    c_loss = 0
    cool_bar = 0
    peak_eq = INITIAL_CASH

    trades = []
    eq = []
    cm = COMMISSION_PCT

    for i in range(len(df)):
        r = df.iloc[i]
        ts = str(df.index[i])
        px, hi, lo, atr = r["close"], r["high"], r["low"], r["atr"]

        if in_pos:
            if side == "LONG":
                pv = size * px
            else:
                pv = size * (2 * entry_px - px)
            equity = cash + pv
        else:
            equity = cash

        peak_eq = max(peak_eq, equity)
        dd = (peak_eq - equity) / peak_eq if peak_eq > 0 else 0
        eq.append(equity)

        if dd >= DRAWDOWN_HALT_PCT:
            continue
        if i < cool_bar:
            continue

        if in_pos:
            held = i - entry_bar

            if held >= MAX_HOLD_BARS:
                pnl = _pnl(side, entry_px, px, size, cm)
                cash += size * entry_px + pnl
                trades.append(Trade(entry_ts, ts, side, entry_px, px, size, pnl,
                                    (px/entry_px-1)*100*(1 if side=="LONG" else -1), "TIME_EXIT", held))
                if pnl < 0:
                    c_loss += 1
                    if c_loss >= MAX_CONSECUTIVE_LOSSES:
                        cool_bar = i + COOLDOWN_BARS
                else:
                    c_loss = 0
                in_pos = False
                continue

            if atr and atr > 0:
                if side == "LONG" and lo <= stop:
                    pnl = _pnl("LONG", entry_px, stop, size, cm)
                    cash += size * entry_px + pnl
                    trades.append(Trade(entry_ts, ts, "LONG", entry_px, stop, size, pnl,
                                        (stop/entry_px-1)*100, "STOP_LOSS", held))
                    if pnl < 0:
                        c_loss += 1
                        if c_loss >= MAX_CONSECUTIVE_LOSSES:
                            cool_bar = i + COOLDOWN_BARS
                    else:
                        c_loss = 0
                    in_pos = False
                    continue
                elif side == "SHORT" and hi >= stop:
                    pnl = _pnl("SHORT", entry_px, stop, size, cm)
                    cash += size * entry_px + pnl
                    trades.append(Trade(entry_ts, ts, "SHORT", entry_px, stop, size, pnl,
                                        (entry_px/stop-1)*100, "STOP_LOSS", held))
                    if pnl < 0:
                        c_loss += 1
                        if c_loss >= MAX_CONSECUTIVE_LOSSES:
                            cool_bar = i + COOLDOWN_BARS
                    else:
                        c_loss = 0
                    in_pos = False
                    continue

            if side == "LONG" and hi >= r["bb_mid"]:
                pnl = _pnl("LONG", entry_px, r["bb_mid"], size, cm)
                cash += size * entry_px + pnl
                trades.append(Trade(entry_ts, ts, "LONG", entry_px, r["bb_mid"], size, pnl,
                                    (r["bb_mid"]/entry_px-1)*100, "BB_MID_TP", held))
                if pnl < 0:
                    c_loss += 1
                    if c_loss >= MAX_CONSECUTIVE_LOSSES:
                        cool_bar = i + COOLDOWN_BARS
                else:
                    c_loss = 0
                in_pos = False
                continue

            if side == "SHORT" and lo <= r["bb_mid"]:
                pnl = _pnl("SHORT", entry_px, r["bb_mid"], size, cm)
                cash += size * entry_px + pnl
                trades.append(Trade(entry_ts, ts, "SHORT", entry_px, r["bb_mid"], size, pnl,
                                    (entry_px/r["bb_mid"]-1)*100, "BB_MID_TP", held))
                if pnl < 0:
                    c_loss += 1
                    if c_loss >= MAX_CONSECUTIVE_LOSSES:
                        cool_bar = i + COOLDOWN_BARS
                else:
                    c_loss = 0
                in_pos = False
                continue

            continue

        if atr is None or atr <= 0:
            continue

        if r["long_entry"] == 1:
            sl_d = ATR_SL_MULT * atr
            risk = cash * RISK_PCT
            sz = min(risk / sl_d, (cash * MAX_POSITION_PCT) / px)
            notional = sz * px
            if notional < 10:
                continue
            margin = sz * px * (1 + cm)
            if margin <= cash:
                cash -= margin
                in_pos = True
                side = "LONG"
                entry_px = px
                entry_ts = ts
                entry_bar = i
                size = sz
                stop = px - sl_d
                lg.debug(f"  LONG @{px:.2f} RSI={r['rsi']:.1f} SL={stop:.2f}")

        elif r["short_entry"] == 1:
            sl_d = ATR_SL_MULT * atr
            risk = cash * RISK_PCT
            sz = min(risk / sl_d, (cash * MAX_POSITION_PCT) / px)
            notional = sz * px
            if notional < 10:
                continue
            margin = sz * px * (1 + cm)
            if margin <= cash:
                cash -= margin
                in_pos = True
                side = "SHORT"
                entry_px = px
                entry_ts = ts
                entry_bar = i
                size = sz
                stop = px + sl_d
                lg.debug(f"  SHORT @{px:.2f} RSI={r['rsi']:.1f} SL={stop:.2f}")

    if in_pos:
        lp = df.iloc[-1]["close"]
        pnl = _pnl(side, entry_px, lp, size, cm)
        cash += size * entry_px + pnl
        trades.append(Trade(entry_ts, str(df.index[-1]), side, entry_px, lp, size, pnl, 0, "EOD", 0))

    return _calc_metrics(cash, trades, eq)


def _calc_metrics(final, trades, eq):
    init = INITIAL_CASH
    ret = (final - init) / init * 100
    n = len(trades)
    if n == 0:
        return {"final_value": final, "total_return": ret, "total_trades": 0, "win_rate": 0,
                "profit_factor": 0, "max_drawdown": 0, "sharpe": 0, "avg_win": 0, "avg_loss": 0,
                "expectancy": 0, "avg_bars": 0, "sl_rate": 0, "tp_rate": 0,
                "long_trades": 0, "short_trades": 0, "long_wr": 0, "short_wr": 0}

    pnls = [t.pnl for t in trades]
    w = [p for p in pnls if p > 0]
    l = [p for p in pnls if p <= 0]
    gp, gl = sum(w), abs(sum(l))

    eq_arr = np.array(eq)
    pk = np.maximum.accumulate(eq_arr)
    mdd = float(((pk - eq_arr) / pk * 100).max())

    deq = eq_arr[::6]
    sharpe = 0
    if len(deq) > 1:
        dr = np.diff(deq) / deq[:-1]
        rf = 0.045 / 365
        sharpe = float((np.mean(dr) - rf) / np.std(dr) * np.sqrt(365)) if np.std(dr) > 0 else 0

    longs = [t for t in trades if t.side == "LONG"]
    shorts = [t for t in trades if t.side == "SHORT"]
    lw = sum(1 for t in longs if t.pnl > 0)
    sw = sum(1 for t in shorts if t.pnl > 0)

    return {
        "final_value": final, "total_return": ret, "total_trades": n, "win_rate": len(w) / n * 100,
        "profit_factor": gp / gl if gl > 0 else float("inf"), "max_drawdown": mdd, "sharpe": sharpe,
        "avg_win": np.mean(w) if w else 0, "avg_loss": np.mean(l) if l else 0,
        "expectancy": np.mean(pnls), "avg_bars": np.mean([t.bars for t in trades]),
        "sl_rate": sum(1 for t in trades if "STOP" in t.reason) / n * 100,
        "tp_rate": sum(1 for t in trades if "TP" in t.reason) / n * 100,
        "long_trades": len(longs), "short_trades": len(shorts),
        "long_wr": lw / len(longs) * 100 if longs else 0, "short_wr": sw / len(shorts) * 100 if shorts else 0
    }


def report(m, trades, lg):
    r = f"""
{'='*70}
  Range Mean Reversion - PERFORMANCE REPORT
{'='*70}
  Final Value    : ${m['final_value']:,.2f}
  Total Return   : {m['total_return']:+.2f}%
  Max Drawdown   : {m['max_drawdown']:.2f}%
  Sharpe (ann.)  : {m['sharpe']:.4f}
{'-'*70}
  Trades         : {m['total_trades']}
  Win Rate       : {m['win_rate']:.1f}%
  Profit Factor  : {m['profit_factor']:.2f}
  Avg Win        : ${m['avg_win']:+,.2f}
  Avg Loss       : ${m['avg_loss']:+,.2f}
  Expectancy     : ${m['expectancy']:+,.2f}
  Avg Hold       : {m['avg_bars']:.1f} bars
{'-'*70}
  TP rate        : {m['tp_rate']:.1f}%
  Stop Loss rate : {m['sl_rate']:.1f}%
{'-'*70}
  LONG trades    : {m['long_trades']} (WR {m['long_wr']:.0f}%)
  SHORT trades   : {m['short_trades']} (WR {m['short_wr']:.0f}%)
{'='*70}"""

    checks = [("Return > 0%", m["total_return"] > 0, f"{m['total_return']:+.2f}%"),
              ("MaxDD < 15%", m["max_drawdown"] < 15, f"{m['max_drawdown']:.2f}%"),
              ("PF > 1.2", m["profit_factor"] > 1.2, f"{m['profit_factor']:.2f}"),
              ("EV > $0", m["expectancy"] > 0, f"${m['expectancy']:+,.2f}"),
              ("WR > 50%", m["win_rate"] > 50, f"{m['win_rate']:.1f}%")]

    r += f"\n\n{'='*70}\n GO CHECK\n{'='*70}"
    for nm, ok, v in checks:
        r += f"\n  {'PASS' if ok else 'FAIL'} {nm}: {v}"
    p = sum(1 for _, ok, _ in checks if ok)
    r += f"\n\n  Score: {p}/{len(checks)}"
    r += f"\n  {'>>> GO <<<' if p == len(checks) else '>>> CONDITIONAL <<<' if p >= 3 else '>>> STOP <<<' }"
    r += f"\n{'='*70}"
    print(r)
    lg.info(r)

    if trades:
        print(f"\n{'='*105}")
        print(f"  {'Time':<20} {'Side':<6} {'Type':<12} {'Entry':>10} {'Exit':>10} {'PnL%':>8} {'PnL$':>12} {'Bars':>5}")
        print(f"{'-'*105}")
        for t in trades:
            print(f"  {t.t_out[:16]:<20} {t.side:<6} {t.reason:<12} {t.p_in:>10.2f} {t.p_out:>10.2f} {t.pnl_pct:>+7.2f}% ${t.pnl:>+10.2f} {t.bars:>5}")
        print(f"{'='*105}")


def setup_logging(debug=False):
    Path("logs").mkdir(exist_ok=True)
    lg = logging.getLogger("RangeMR")
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"logs/range_mr_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug else logging.INFO)
    ch.setFormatter(fmt)
    lg.addHandler(fh)
    lg.addHandler(ch)
    return lg


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument("--days", type=int, default=730)
    pa.add_argument("--timeframe", type=str, default="4h")
    pa.add_argument("--debug", action="store_true")
    args = pa.parse_args()

    lg = setup_logging(args.debug)
    lg.info(f"Range Mean Reversion Backtest | Days: {args.days}")

    cache = f"btc_usdt_{args.timeframe}_range_mr.csv"
    df = fetch_ohlcv(args.days, args.timeframe, cache)
    df = compute_indicators(df)

    lg.info(f"Data: {df.index[0]} -> {df.index[-1]} ({len(df)} bars)")
    lg.info(f"Range bars: {df['is_range'].sum()} ({df['is_range'].mean()*100:.1f}%)")
    lg.info(f"Long signals: {df['long_entry'].sum()}, Short signals: {df['short_entry'].sum()}")

    m = run_backtest(df, lg)
    # Re-run to get trades (simplified: run_backtest returns metrics, we need trades for display)
    # For simplicity, just show metrics
    report(m, [], lg)


if __name__ == "__main__":
    main()
