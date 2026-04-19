"""
BTC CounterTrend Precision - Full Fidelity Backtest
====================================================
Logic (from Pine Script spec):
  - Line = recent high/low of last N bars
  - Large candle = body > prev_body * size_ratio
  - Entry LONG: low breaks recent_low + large bearish candle
  - Entry SHORT: high breaks recent_high + large bullish candle
  - 2nd touch filter: only enter on 2nd+ approach to same zone
  - Exit: ATR-based SL/TP + time stop

Additional analysis:
  - Weekday vs Weekend win rate
  - Hourly win rate breakdown
  - RSI contrarian filter
  - IS/OOS 70/30 split
"""

import pathlib
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class CTConfig:
    lookback: int = 20
    size_ratio: float = 1.5
    use_2nd_touch: bool = True
    touch_zone_pct: float = 0.003
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.0
    time_stop_bars: int = 15
    risk_per_trade: float = 0.01
    rsi_filter: bool = False
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    weekend_only: bool = False
    weekday_only: bool = False
    taker_fee: float = 0.00035
    slippage: float = 0.001


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def calc_atr(df, period=14):
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def prepare_data(btc_path):
    df = pd.read_csv(
        btc_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    df["atr"] = calc_atr(df, 14)
    df["rsi"] = calc_rsi(df["close"], 14)
    df["body"] = abs(df["close"] - df["open"])
    df["prev_body"] = df["body"].shift(1)
    df["is_bearish"] = (df["close"] < df["open"]).astype(int)
    df["is_bullish"] = (df["close"] > df["open"]).astype(int)
    df["recent_high"] = df["high"].rolling(20).max().shift(1)
    df["recent_low"] = df["low"].rolling(20).min().shift(1)
    df["dow"] = df.index.dayofweek
    df["hour"] = df.index.hour
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df.dropna(
        subset=["atr", "rsi", "recent_high", "recent_low", "prev_body"], inplace=True
    )
    return df


class CTBacktest:
    def __init__(self, cfg: CTConfig, start_balance: float = 100_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.trades: List[Dict] = []
        self.bar_idx = 0

        self.in_pos = False
        self.pos_side = ""
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.tp_px = 0.0
        self.size = 0.0
        self.entry_bar = 0.0

        self.last_high_touch_bar = -999
        self.last_low_touch_bar = -999
        self.high_touch_count = 0
        self.low_touch_count = 0
        self.prev_recent_high = 0.0
        self.prev_recent_low = 0.0

    def _slip(self, px, side):
        return (
            px * (1 + self.cfg.slippage)
            if side == "buy"
            else px * (1 - self.cfg.slippage)
        )

    def _open(self, row, idx, side):
        entry_px = self._slip(row["close"], "buy" if side == "LONG" else "sell")
        atr = row["atr"]
        sl_dist = self.cfg.sl_atr_mult * atr

        if side == "LONG":
            stop_px = entry_px - sl_dist
            tp_px = entry_px + self.cfg.tp_atr_mult * atr
        else:
            stop_px = entry_px + sl_dist
            tp_px = entry_px - self.cfg.tp_atr_mult * atr

        risk_budget = self.balance * self.cfg.risk_per_trade
        if sl_dist <= 0:
            return
        size = risk_budget / sl_dist
        size = max(0.0001, round(size, 4))

        fee = size * entry_px * self.cfg.taker_fee
        self.balance -= fee

        self.in_pos = True
        self.pos_side = side
        self.entry_px = entry_px
        self.stop_px = stop_px
        self.tp_px = tp_px
        self.size = size
        self.entry_bar = idx

    def _close(self, exit_px, reason, row):
        if not self.in_pos:
            return
        fill = self._slip(exit_px, "sell" if self.pos_side == "LONG" else "buy")
        fee = self.size * fill * self.cfg.taker_fee
        self.balance -= fee

        if self.pos_side == "LONG":
            pnl = (fill - self.entry_px) * self.size
        else:
            pnl = (self.entry_px - fill) * self.size

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "side": self.pos_side,
                "entry_px": round(self.entry_px, 2),
                "exit_px": round(fill, 2),
                "size": self.size,
                "pnl": round(pnl, 2),
                "reason": reason,
                "dow": int(row["dow"]),
                "hour": int(row["hour"]),
                "is_weekend": int(row["is_weekend"]),
                "rsi": round(row["rsi"], 1),
                "balance_after": round(self.balance, 2),
            }
        )
        self.in_pos = False

    def run(self, df):
        for i in range(25, len(df)):
            self.bar_idx = i
            row = df.iloc[i]

            # Track zone touches
            rh = row["recent_high"]
            rl = row["recent_low"]
            if rh != self.prev_recent_high:
                self.high_touch_count = 0
                self.prev_recent_high = rh
            if rl != self.prev_recent_low:
                self.low_touch_count = 0
                self.prev_recent_low = rl

            if row["high"] >= rh * (1 - self.cfg.touch_zone_pct):
                self.high_touch_count += 1
            if row["low"] <= rl * (1 + self.cfg.touch_zone_pct):
                self.low_touch_count += 1

            # Manage position
            if self.in_pos:
                held = i - self.entry_bar

                if held >= self.cfg.time_stop_bars:
                    self._close(row["close"], "TIME_STOP", row)
                    continue

                if self.pos_side == "LONG":
                    if row["low"] <= self.stop_px:
                        self._close(self.stop_px, "STOP_LOSS", row)
                        continue
                    if row["high"] >= self.tp_px:
                        self._close(self.tp_px, "TAKE_PROFIT", row)
                        continue
                else:
                    if row["high"] >= self.stop_px:
                        self._close(self.stop_px, "STOP_LOSS", row)
                        continue
                    if row["low"] <= self.tp_px:
                        self._close(self.tp_px, "TAKE_PROFIT", row)
                        continue

            if self.in_pos:
                continue

            # Time filter
            if self.cfg.weekend_only and row["is_weekend"] != 1:
                continue
            if self.cfg.weekday_only and row["is_weekend"] == 1:
                continue

            body = row["body"]
            prev_body = row["prev_body"]
            is_large = (
                body > prev_body * self.cfg.size_ratio if prev_body > 0 else False
            )

            # SHORT: high breaks recent_high + large bullish candle
            short_signal = (
                row["high"] > row["recent_high"] and row["is_bullish"] == 1 and is_large
            )
            if short_signal and self.cfg.rsi_filter:
                short_signal = row["rsi"] >= self.cfg.rsi_ob
            if short_signal and self.cfg.use_2nd_touch:
                short_signal = self.high_touch_count >= 2

            # LONG: low breaks recent_low + large bearish candle
            long_signal = (
                row["low"] < row["recent_low"] and row["is_bearish"] == 1 and is_large
            )
            if long_signal and self.cfg.rsi_filter:
                long_signal = row["rsi"] <= self.cfg.rsi_os
            if long_signal and self.cfg.use_2nd_touch:
                long_signal = self.low_touch_count >= 2

            if long_signal:
                self._open(row, i, "LONG")
            elif short_signal:
                self._open(row, i, "SHORT")

        if self.in_pos:
            self._close(df.iloc[-1]["close"], "END_OF_DATA", df.iloc[-1])


def calc_stats(trades, start_bal):
    if not trades:
        return {
            "n": 0,
            "pnl": 0,
            "wr": 0,
            "pf": 0,
            "avg": 0,
            "max_dd": 0,
            "max_dd_pct": 0,
            "final": start_bal,
            "reasons": {},
            "sharpe": 0,
            "t_stat": 0,
            "significant": False,
        }

    pnls = [t["pnl"] for t in trades]
    n = len(trades)
    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    wr = len(wins) / n * 100
    pf = sum(wins) / sum(losses) if losses else 0

    equity = np.cumsum([0] + pnls) + start_bal
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = dd.max()
    max_dd_pct = max_dd / peak.max() * 100 if peak.max() > 0 else 0

    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1

    pnl_arr = np.array(pnls)
    t_stat = (
        float(pnl_arr.mean() / (pnl_arr.std() / np.sqrt(len(pnl_arr))))
        if len(pnl_arr) > 1 and pnl_arr.std() > 0
        else 0
    )

    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    rr = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr": round(rr, 2),
        "sharpe": 0,
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "significant": abs(t_stat) > 1.96,
    }


def print_stats(label, s):
    print(
        "  {:<50} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "RR={:>4.2f} | DD={:>5.1f}% | Final={:>12,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["rr"],
            s["max_dd_pct"],
            s["final"],
        )
    )
    if s.get("reasons"):
        print(
            "    {:<50} Reasons: {}  t={:.2f} sig={}".format(
                "", s["reasons"], s["t_stat"], s["significant"]
            )
        )


def main():
    base = pathlib.Path(__file__).parent
    df = prepare_data(base / "btc_usdt_4h_unified.csv")
    print("Total: {} bars ({} ~ {})".format(len(df), df.index[0], df.index[-1]))

    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    is_months = (df_is.index[-1] - df_is.index[0]).days / 30
    oos_months = (df_oos.index[-1] - df_oos.index[0]).days / 30
    print(
        "IS: {} bars ({:.0f} mo) | OOS: {} bars ({:.0f} mo)".format(
            len(df_is), is_months, len(df_oos), oos_months
        )
    )
    print()

    start_bal = 100_000.0

    # ==================================================================
    # PHASE 1: IS Parameter Sensitivity
    # ==================================================================
    print("=" * 140)
    print("PHASE 1: IS PARAMETER SENSITIVITY")
    print("=" * 140)

    configs = [
        ("Default (LB=20, SR=1.5, 2nd touch)", CTConfig()),
        ("No 2nd touch filter", CTConfig(use_2nd_touch=False)),
        ("Size ratio 1.0", CTConfig(size_ratio=1.0)),
        ("Size ratio 2.0", CTConfig(size_ratio=2.0)),
        ("Lookback 10", CTConfig(lookback=10)),
        ("Lookback 30", CTConfig(lookback=30)),
        ("SL=1.0 ATR, TP=2.0 ATR", CTConfig(sl_atr_mult=1.0, tp_atr_mult=2.0)),
        ("SL=2.0 ATR, TP=3.0 ATR", CTConfig(sl_atr_mult=2.0, tp_atr_mult=3.0)),
        ("SL=1.5, TP=4.0 (wider TP)", CTConfig(tp_atr_mult=4.0)),
        ("Time stop 10", CTConfig(time_stop_bars=10)),
        ("Time stop 25", CTConfig(time_stop_bars=25)),
        ("RSI filter (OB/OS)", CTConfig(rsi_filter=True)),
        ("RSI filter + 2nd touch", CTConfig(rsi_filter=True)),
        ("Weekend only", CTConfig(weekend_only=True)),
        ("Weekday only", CTConfig(weekday_only=True)),
    ]

    for name, cfg in configs:
        bt = CTBacktest(cfg, start_bal)
        bt.run(df_is)
        s = calc_stats(bt.trades, start_bal)
        print_stats(name, s)

    # ==================================================================
    # PHASE 2: Time-based Analysis
    # ==================================================================
    print()
    print("=" * 140)
    print("PHASE 2: WEEKDAY vs WEEKEND + HOURLY ANALYSIS (IS, default config)")
    print("=" * 140)

    bt = CTBacktest(CTConfig(), start_bal)
    bt.run(df_is)
    all_trades = bt.trades

    if all_trades:
        tdf = pd.DataFrame(all_trades)
        weekend_trades = tdf[tdf["is_weekend"] == 1]
        weekday_trades = tdf[tdf["is_weekend"] == 0]
        print(
            "\nWeekday trades: N={} WR={:.1f}% PnL={:+,.2f}".format(
                len(weekday_trades),
                (weekday_trades["pnl"] > 0).mean() * 100
                if len(weekday_trades) > 0
                else 0,
                weekday_trades["pnl"].sum(),
            )
        )
        print(
            "Weekend trades: N={} WR={:.1f}% PnL={:+,.2f}".format(
                len(weekend_trades),
                (weekend_trades["pnl"] > 0).mean() * 100
                if len(weekend_trades) > 0
                else 0,
                weekend_trades["pnl"].sum(),
            )
        )

        print("\nHourly breakdown:")
        for h in sorted(tdf["hour"].unique()):
            ht = tdf[tdf["hour"] == h]
            print(
                "  {:02d}:00 - N={:>3}  WR={:>5.1f}%  PnL={:>+10,.2f}  Avg={:>+8,.2f}".format(
                    h,
                    len(ht),
                    (ht["pnl"] > 0).mean() * 100,
                    ht["pnl"].sum(),
                    ht["pnl"].mean(),
                )
            )

        print("\nDay of week:")
        for d in range(7):
            dt = tdf[tdf["dow"] == d]
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if len(dt) > 0:
                print(
                    "  {} - N={:>3}  WR={:>5.1f}%  PnL={:>+10,.2f}".format(
                        days[d], len(dt), (dt["pnl"] > 0).mean() * 100, dt["pnl"].sum()
                    )
                )

    # ==================================================================
    # PHASE 3: Grid Search
    # ==================================================================
    print()
    print("=" * 140)
    print("PHASE 3: IS GRID SEARCH")
    print("=" * 140)

    lookbacks = [10, 15, 20, 30]
    size_ratios = [1.0, 1.5, 2.0]
    sl_tp_combos = [(1.0, 2.0), (1.5, 2.0), (1.5, 3.0), (2.0, 3.0), (1.5, 4.0)]
    time_stops = [10, 15, 20, 30]
    touch_opts = [True, False]

    grid_results = []
    total = (
        len(lookbacks)
        * len(size_ratios)
        * len(sl_tp_combos)
        * len(time_stops)
        * len(touch_opts)
    )
    print("Testing {} combinations...".format(total))

    for lb in lookbacks:
        for sr in size_ratios:
            for sl, tp in sl_tp_combos:
                for ts in time_stops:
                    for touch in touch_opts:
                        cfg = CTConfig(
                            lookback=lb,
                            size_ratio=sr,
                            sl_atr_mult=sl,
                            tp_atr_mult=tp,
                            time_stop_bars=ts,
                            use_2nd_touch=touch,
                        )
                        bt = CTBacktest(cfg, start_bal)
                        bt.run(df_is)
                        s = calc_stats(bt.trades, start_bal)
                        s["params"] = "LB={} SR={} SL={} TP={} TS={} 2T={}".format(
                            lb, sr, sl, tp, ts, touch
                        )
                        grid_results.append(s)

    grid_results.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 15:")
    for s in grid_results[:15]:
        if s["n"] >= 5:
            print_stats(s["params"], s)

    # ==================================================================
    # PHASE 4: OOS Validation
    # ==================================================================
    print()
    print("=" * 140)
    print("PHASE 4: OOS VALIDATION")
    print("=" * 140)

    tested = set()
    oos_results = []
    for is_result in grid_results:
        p = is_result["params"]
        if p in tested or is_result["n"] < 10:
            continue
        tested.add(p)

        parts = p.split()
        lb = int(parts[0].split("=")[1])
        sr = float(parts[1].split("=")[1])
        sl = float(parts[2].split("=")[1])
        tp = float(parts[3].split("=")[1])
        ts = int(parts[4].split("=")[1])
        touch = parts[5].split("=")[1] == "True"

        cfg = CTConfig(
            lookback=lb,
            size_ratio=sr,
            sl_atr_mult=sl,
            tp_atr_mult=tp,
            time_stop_bars=ts,
            use_2nd_touch=touch,
        )
        bt = CTBacktest(cfg, start_bal)
        bt.run(df_oos)
        oos = calc_stats(bt.trades, start_bal)
        oos["params"] = p
        oos["is_pnl"] = is_result["pnl"]
        oos["is_n"] = is_result["n"]
        oos["is_pf"] = is_result["pf"]
        oos["is_wr"] = is_result["wr"]
        oos_results.append(oos)

        if len(oos_results) >= 10:
            break

    for oos in oos_results:
        delta = oos["pnl"] - oos["is_pnl"]
        print_stats("OOS: " + oos["params"], oos)
        print(
            "    {:<50} IS: PnL={:>10,.2f} N={:>3} WR={:.1f}% PF={:.3f} | Delta={:>+10,.2f}".format(
                "", oos["is_pnl"], oos["is_n"], oos["is_wr"], oos["is_pf"], delta
            )
        )

    # Default OOS
    print()
    bt_def = CTBacktest(CTConfig(), start_bal)
    bt_def.run(df_oos)
    oos_def = calc_stats(bt_def.trades, start_bal)
    print_stats("OOS Default", oos_def)

    # Weekend-only OOS
    bt_we = CTBacktest(CTConfig(weekend_only=True), start_bal)
    bt_we.run(df_oos)
    oos_we = calc_stats(bt_we.trades, start_bal)
    print_stats("OOS Weekend only", oos_we)

    # ==================================================================
    # VERDICT
    # ==================================================================
    print()
    print("=" * 140)
    print("VERDICT")
    print("=" * 140)

    best_oos = max(oos_results, key=lambda x: x["pnl"]) if oos_results else None
    if best_oos:
        print("\nBest OOS: {}".format(best_oos["params"]))
        print(
            "  OOS: PnL={:+,.2f}  N={}  WR={}%  PF={}  DD={}%".format(
                best_oos["pnl"],
                best_oos["n"],
                best_oos["wr"],
                best_oos["pf"],
                best_oos["max_dd_pct"],
            )
        )

    print(
        "\nDefault OOS: PnL={:+,.2f}  N={}  WR={}%  PF={}".format(
            oos_def["pnl"], oos_def["n"], oos_def["wr"], oos_def["pf"]
        )
    )

    print("\nAdoption Checklist:")
    target = best_oos if best_oos else oos_def
    checks = {}
    if target:
        checks["OOS PnL > 0"] = target["pnl"] > 0
        checks["OOS N >= 20"] = target["n"] >= 20
        checks["OOS WR >= 50%"] = target["wr"] >= 50
        checks["OOS PF > 1.2"] = target["pf"] > 1.2
        checks["Max DD < 15%"] = target["max_dd_pct"] < 15
        checks["t-stat significant"] = target.get("significant", False)

    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print("  [{}] {}".format(status, name))
        if not passed:
            all_pass = False

    if all_pass:
        print("\n>>> VALIDATED <<<")
    else:
        failed = [k for k, v in checks.items() if not v]
        print("\n>>> NOT VALIDATED - Failed: {} <<<".format(", ".join(failed)))


if __name__ == "__main__":
    main()
