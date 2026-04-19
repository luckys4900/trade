"""
CounterTrend EV Extraction - Deep Dive
=======================================
Focus: RSI filter + Friday filter combinations
Grid search with RSI filter ON, then OOS validation
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
    rsi_filter: bool = True
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    dow_filter: int = -1  # -1=all, 0=Mon..4=Fri, 5=Sat, 6=Sun
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
        if sl_dist <= 0:
            return
        risk_budget = self.balance * self.cfg.risk_per_trade
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
                "rsi": round(row["rsi"], 1),
                "balance_after": round(self.balance, 2),
            }
        )
        self.in_pos = False

    def run(self, df):
        for i in range(25, len(df)):
            self.bar_idx = i
            row = df.iloc[i]

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

            if self.cfg.dow_filter >= 0 and row["dow"] != self.cfg.dow_filter:
                continue

            body = row["body"]
            prev_body = row["prev_body"]
            is_large = (
                body > prev_body * self.cfg.size_ratio if prev_body > 0 else False
            )

            short_signal = (
                row["high"] > row["recent_high"] and row["is_bullish"] == 1 and is_large
            )
            if short_signal and self.cfg.rsi_filter:
                short_signal = row["rsi"] >= self.cfg.rsi_ob
            if short_signal and self.cfg.use_2nd_touch:
                short_signal = self.high_touch_count >= 2

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
            "t_stat": 0,
            "significant": False,
            "rr": 0,
        }
    pnls = [t["pnl"] for t in trades]
    n = len(trades)
    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    wr = len(wins) / n * 100
    pf = sum(wins) / sum(losses) if losses else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    rr = avg_win / avg_loss if avg_loss > 0 else 0
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
    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "rr": round(rr, 2),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "significant": abs(t_stat) > 1.96,
    }


def print_stats(label, s):
    print(
        "  {:<55} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "RR={:>4.2f} | DD={:>5.1f}% | t={:>5.2f} | Final={:>12,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["rr"],
            s["max_dd_pct"],
            s["t_stat"],
            s["final"],
        )
    )
    if s.get("reasons"):
        print("    {:<55} {}".format("", s["reasons"]))


def main():
    base = pathlib.Path(__file__).parent
    df = prepare_data(base / "btc_usdt_4h_unified.csv")
    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    is_mo = (df_is.index[-1] - df_is.index[0]).days / 30
    oos_mo = (df_oos.index[-1] - df_oos.index[0]).days / 30
    start_bal = 100_000.0

    print(
        "IS: {} bars ({:.0f}mo) | OOS: {} bars ({:.0f}mo)".format(
            len(df_is), is_mo, len(df_oos), oos_mo
        )
    )

    # ==================================================================
    # STEP 1: RSI filter ON - Day-of-week analysis (IS)
    # ==================================================================
    print("\n" + "=" * 150)
    print("STEP 1: RSI FILTER ON - DAY-OF-WEEK ANALYSIS (IS)")
    print("=" * 150)

    days = ["All", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for dow in range(-1, 7):
        cfg = CTConfig(rsi_filter=True, dow_filter=dow)
        bt = CTBacktest(cfg, start_bal)
        bt.run(df_is)
        s = calc_stats(bt.trades, start_bal)
        print_stats("RSI ON + {}".format(days[dow + 1]), s)

    # ==================================================================
    # STEP 2: Grid search with RSI filter ON (IS)
    # ==================================================================
    print("\n" + "=" * 150)
    print("STEP 2: GRID SEARCH - RSI FILTER ON (IS)")
    print("=" * 150)

    rsi_os_list = [25, 30, 35]
    rsi_ob_list = [65, 70, 75]
    sl_tp = [(1.5, 2.0), (1.5, 3.0), (2.0, 3.0), (2.0, 4.0), (2.5, 5.0)]
    ts_list = [10, 15, 20, 30]
    touch_list = [True, False]

    grid = []
    total = (
        len(rsi_os_list)
        * len(rsi_ob_list)
        * len(sl_tp)
        * len(ts_list)
        * len(touch_list)
    )
    print("Testing {} combos...".format(total))

    for rsi_os in rsi_os_list:
        for rsi_ob in rsi_ob_list:
            for sl, tp in sl_tp:
                for ts in ts_list:
                    for touch in touch_list:
                        cfg = CTConfig(
                            rsi_filter=True,
                            rsi_os=float(rsi_os),
                            rsi_ob=float(rsi_ob),
                            sl_atr_mult=sl,
                            tp_atr_mult=tp,
                            time_stop_bars=ts,
                            use_2nd_touch=touch,
                        )
                        bt = CTBacktest(cfg, start_bal)
                        bt.run(df_is)
                        s = calc_stats(bt.trades, start_bal)
                        s["params"] = "RSI_OS={} OB={} SL={} TP={} TS={} 2T={}".format(
                            rsi_os, rsi_ob, sl, tp, ts, touch
                        )
                        grid.append(s)

    grid.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 20:")
    for s in grid[:20]:
        if s["n"] >= 5:
            print_stats(s["params"], s)

    # ==================================================================
    # STEP 3: Grid search with RSI + Friday filter (IS)
    # ==================================================================
    print("\n" + "=" * 150)
    print("STEP 3: GRID SEARCH - RSI FILTER + FRIDAY ONLY (IS)")
    print("=" * 150)

    grid_fri = []
    for rsi_os in rsi_os_list:
        for rsi_ob in rsi_ob_list:
            for sl, tp in sl_tp:
                for ts in ts_list:
                    for touch in touch_list:
                        cfg = CTConfig(
                            rsi_filter=True,
                            rsi_os=float(rsi_os),
                            rsi_ob=float(rsi_ob),
                            sl_atr_mult=sl,
                            tp_atr_mult=tp,
                            time_stop_bars=ts,
                            use_2nd_touch=touch,
                            dow_filter=4,
                        )
                        bt = CTBacktest(cfg, start_bal)
                        bt.run(df_is)
                        s = calc_stats(bt.trades, start_bal)
                        s["params"] = (
                            "FRI RSI_OS={} OB={} SL={} TP={} TS={} 2T={}".format(
                                rsi_os, rsi_ob, sl, tp, ts, touch
                            )
                        )
                        grid_fri.append(s)

    grid_fri.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 15 (Friday only):")
    for s in grid_fri[:15]:
        if s["n"] >= 3:
            print_stats(s["params"], s)

    # ==================================================================
    # STEP 4: OOS Validation - Top from both grids
    # ==================================================================
    print("\n" + "=" * 150)
    print("STEP 4: OOS VALIDATION")
    print("=" * 150)

    def parse_params(p):
        parts = p.split()
        is_fri = parts[0] == "FRI"
        offset = 1 if is_fri else 0
        rsi_os = float(parts[offset].split("=")[1])
        rsi_ob = float(parts[offset + 1].split("=")[1])
        sl = float(parts[offset + 2].split("=")[1])
        tp = float(parts[offset + 3].split("=")[1])
        ts = int(parts[offset + 4].split("=")[1])
        touch = parts[offset + 5].split("=")[1] == "True"
        dow = 4 if is_fri else -1
        return CTConfig(
            rsi_filter=True,
            rsi_os=rsi_os,
            rsi_ob=rsi_ob,
            sl_atr_mult=sl,
            tp_atr_mult=tp,
            time_stop_bars=ts,
            use_2nd_touch=touch,
            dow_filter=dow,
        )

    all_candidates = grid[:20] + grid_fri[:10]
    tested = set()
    oos_results = []

    for cand in all_candidates:
        p = cand["params"]
        if p in tested or cand["n"] < 5:
            continue
        tested.add(p)

        cfg = parse_params(p)
        bt = CTBacktest(cfg, start_bal)
        bt.run(df_oos)
        oos = calc_stats(bt.trades, start_bal)
        oos["params"] = p
        oos["is_pnl"] = cand["pnl"]
        oos["is_n"] = cand["n"]
        oos["is_pf"] = cand["pf"]
        oos["is_wr"] = cand["wr"]
        oos["is_sig"] = cand["significant"]
        oos_results.append(oos)

    oos_results.sort(key=lambda x: x["pnl"], reverse=True)

    print("\nOOS Results (sorted by PnL):")
    for oos in oos_results[:15]:
        delta = oos["pnl"] - oos["is_pnl"]
        print_stats("OOS: " + oos["params"], oos)
        print(
            "    {:<55} IS: PnL={:>10,.2f} N={:>3} WR={:.1f}% PF={:.3f} sig={} | Delta={:>+10,.2f}".format(
                "",
                oos["is_pnl"],
                oos["is_n"],
                oos["is_wr"],
                oos["is_pf"],
                oos["is_sig"],
                delta,
            )
        )

    # ==================================================================
    # STEP 5: EV Verdict
    # ==================================================================
    print("\n" + "=" * 150)
    print("STEP 5: EV VERDICT")
    print("=" * 150)

    positive_oos = [o for o in oos_results if o["pnl"] > 0 and o["n"] >= 10]
    significant_oos = [o for o in oos_results if o["significant"] and o["n"] >= 10]
    consistent_oos = [
        o for o in oos_results if o["pnl"] > 0 and o["pf"] > 1.2 and o["n"] >= 10
    ]

    print("\nOOS results with PnL > 0 and N >= 10: {}".format(len(positive_oos)))
    print(
        "OOS results with t-stat significant and N >= 10: {}".format(
            len(significant_oos)
        )
    )
    print("OOS results with PnL > 0, PF > 1.2, N >= 10: {}".format(len(consistent_oos)))

    if positive_oos:
        print("\nPositive EV candidates:")
        for oos in positive_oos[:10]:
            ev_per_trade = oos["avg"]
            print(
                "  {} | PnL={:+,.2f} N={} WR={}% PF={} EV/trade={:+,.2f} DD={} t={}".format(
                    oos["params"][:60],
                    oos["pnl"],
                    oos["n"],
                    oos["wr"],
                    oos["pf"],
                    ev_per_trade,
                    oos["max_dd_pct"],
                    oos["t_stat"],
                )
            )

    if consistent_oos:
        print("\n*** CONSISTENT EV FOUND - Further validation recommended ***")
        for oos in consistent_oos:
            print("  >>> {}".format(oos["params"]))
            print(
                "      OOS: PnL={:+,.2f}  WR={}%  PF={}  t={}  sig={}".format(
                    oos["pnl"], oos["wr"], oos["pf"], oos["t_stat"], oos["significant"]
                )
            )
            print(
                "      IS:  PnL={:+,.2f}  WR={}%  PF={}".format(
                    oos["is_pnl"], oos["is_wr"], oos["is_pf"]
                )
            )
    elif positive_oos:
        print("\n*** MARGINAL EV - Some positive but PF < 1.2 or inconsistent ***")
    else:
        print("\n*** NO EV DETECTED in any configuration ***")


if __name__ == "__main__":
    main()
