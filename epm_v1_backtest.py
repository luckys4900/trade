"""
EPM v1.0 - EMA Pullback Momentum - Full-Fidelity Backtest
==========================================================
Single-file backtest: BTC 4H + Daily regime filter
70/30 IS/OOS split, fee/slippage, full exit logic

Entry:
  1. Daily close > Daily EMA200 (Bull Regime)
  2. 4H close > 4H EMA55 (trend intact)
  3. 4H EMA21 > EMA55 (alignment)
  4. Price near EMA21 (distance < 0.5 ATR)
  5. RSI dipped <= 38 then recovered >= 48 (within last 5 bars)
  6. Volume surge: prev bar volume > 1.6x 20-bar avg
  7. Bullish candle + price rising

Exit:
  - Initial SL: entry - 2.2 ATR
  - Trail activation: 1.5R reached -> trail on EMA21
  - Partial TP: 2.5R -> 50% close (simplified: full close at trail)
  - Time stop: 30 bars (5 days)
"""

import pathlib
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class EPMConfig:
    regime_ema_period: int = 200
    fast_ema: int = 21
    slow_ema: int = 55
    rsi_period: int = 14
    rsi_oversold: float = 38.0
    rsi_recovery: float = 48.0
    volume_surge: float = 1.6
    atr_period: int = 14
    atr_stop_mult: float = 2.2
    trail_activation_r: float = 1.5
    profit_target_r: float = 2.5
    time_stop_bars: int = 30
    risk_per_trade: float = 0.01
    pullback_atr_dist: float = 0.5
    rsi_lookback: int = 5
    taker_fee: float = 0.00045
    slippage: float = 0.001


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


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


def resample_daily(df_4h):
    daily = (
        df_4h.resample("D")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )
    return daily


def prepare_data(btc_path):
    df = pd.read_csv(
        btc_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()

    daily = resample_daily(df)
    daily["ema_200"] = ema(daily["close"], 200)
    daily["bull_regime"] = (daily["close"] > daily["ema_200"]).astype(int)

    df["ema_fast"] = ema(df["close"], 21)
    df["ema_slow"] = ema(df["close"], 55)
    df["atr"] = calc_atr(df, 14)
    df["rsi"] = calc_rsi(df["close"], 14)

    df["vol_ma20"] = df["volume"].rolling(20).mean()

    df["date"] = df.index.date
    regime_map = daily["bull_regime"].to_dict()
    date_to_regime = {}
    for idx, val in regime_map.items():
        date_to_regime[idx.date()] = val
    df["bull_regime"] = df["date"].map(date_to_regime).ffill().fillna(0).astype(int)

    df.dropna(subset=["ema_fast", "ema_slow", "atr", "rsi", "vol_ma20"], inplace=True)
    return df


class EPMBacktest:
    def __init__(self, cfg: EPMConfig, start_balance: float = 10_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.in_pos = False
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.entry_bar = 0
        self.size_usd = 0.0
        self.trail_active = False
        self.trades: List[Dict] = []
        self.bar_idx = 0

    def _apply_slippage(self, px, side):
        if side == "buy":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _open(self, row, idx):
        entry_px = self._apply_slippage(row["close"], "buy")
        stop_px = entry_px - self.cfg.atr_stop_mult * row["atr"]
        risk_budget = self.balance * self.cfg.risk_per_trade
        risk_per_unit = abs(entry_px - stop_px)
        if risk_per_unit <= 0:
            return
        size_usd = min(risk_budget / risk_per_unit, self.balance * 0.25)

        fee = size_usd * self.cfg.taker_fee
        self.balance -= fee

        self.in_pos = True
        self.entry_px = entry_px
        self.stop_px = stop_px
        self.entry_bar = idx
        self.size_usd = size_usd
        self.trail_active = False

    def _close(self, exit_px, reason):
        fill_px = self._apply_slippage(exit_px, "sell")
        fee = self.size_usd * self.cfg.taker_fee
        self.balance -= fee

        pnl = (fill_px - self.entry_px) / self.entry_px * self.size_usd
        pnl -= fee

        initial_risk = abs(self.entry_px - self.stop_px)
        r_multiple = (fill_px - self.entry_px) / initial_risk if initial_risk > 0 else 0

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "entry_px": self.entry_px,
                "exit_px": fill_px,
                "size_usd": self.size_usd,
                "pnl": pnl,
                "pnl_pct": (fill_px - self.entry_px) / self.entry_px,
                "r_multiple": r_multiple,
                "reason": reason,
                "balance_after": self.balance,
            }
        )
        self.in_pos = False

    def check_entry(self, df, idx):
        if idx < self.cfg.rsi_lookback + 5:
            return False
        row = df.iloc[idx]
        prev = df.iloc[idx - 1]

        if row.get("bull_regime", 0) != 1:
            return False

        close = row["close"]
        ema_fast = row["ema_fast"]
        ema_slow = row["ema_slow"]
        current_atr = row["atr"]
        current_rsi = row["rsi"]

        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(current_atr):
            return False

        distance_to_ema = abs(close - ema_fast) / current_atr
        near_ema = distance_to_ema <= self.cfg.pullback_atr_dist

        above_slow = close > ema_slow
        ema_alignment = ema_fast > ema_slow

        recent_rsi = df["rsi"].iloc[max(0, idx - self.cfg.rsi_lookback) : idx + 1]
        rsi_dipped = recent_rsi.min() <= self.cfg.rsi_oversold
        rsi_recovered = current_rsi >= self.cfg.rsi_recovery

        vol_avg = df["volume"].iloc[max(0, idx - 20) : idx].mean()
        volume_surge = prev["volume"] > vol_avg * self.cfg.volume_surge

        price_rising = close > prev["close"]
        bullish_candle = close > row["open"]

        return all(
            [
                near_ema,
                above_slow,
                ema_alignment,
                rsi_dipped,
                rsi_recovered,
                volume_surge,
                price_rising,
                bullish_candle,
            ]
        )

    def check_exit(self, df, idx):
        if not self.in_pos:
            return False, 0.0, ""

        row = df.iloc[idx]
        bars_held = idx - self.entry_bar
        initial_risk = abs(self.entry_px - self.stop_px)
        current_r = (
            (row["close"] - self.entry_px) / initial_risk if initial_risk > 0 else 0
        )

        if bars_held >= self.cfg.time_stop_bars:
            return True, row["close"], "TIME_STOP"

        if current_r >= self.cfg.trail_activation_r:
            self.trail_active = True

        if self.trail_active and row["close"] < row["ema_fast"]:
            return True, row["close"], "TRAIL_EMA"

        if row["low"] <= self.stop_px:
            return True, self.stop_px, "STOP_LOSS"

        if current_r >= self.cfg.profit_target_r and not self.trail_active:
            return True, row["close"], "PROFIT_TARGET"

        return False, 0.0, ""

    def run(self, df):
        for i in range(30, len(df)):
            self.bar_idx = i

            should_exit, exit_px, reason = self.check_exit(df, i)
            if should_exit:
                self._close(exit_px, reason)
                continue

            if self.in_pos:
                continue

            if self.check_entry(df, i):
                self._open(df.iloc[i], i)

        if self.in_pos:
            self._close(df.iloc[-1]["close"], "END_OF_DATA")


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
            "fees": 0,
            "final": start_bal,
            "reasons": {},
            "avg_r": 0,
            "sharpe": 0,
            "t_stat": 0,
            "rr": 0,
            "significant": False,
        }

    pnls = [t["pnl"] for t in trades]
    pnl_pcts = [t["pnl_pct"] for t in trades]
    r_mults = [t["r_multiple"] for t in trades]
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

    pcts = np.array(pnl_pcts)
    t_stat = (
        float(pcts.mean() / (pcts.std() / np.sqrt(len(pcts))))
        if len(pcts) > 1 and pcts.std() > 0
        else 0
    )

    daily_chunks = np.array_split(pnls, max(1, len(pnls) // 6))
    daily_sums = [sum(c) for c in daily_chunks]
    darr = np.array(daily_sums)
    sharpe = (
        darr.mean() / darr.std() * np.sqrt(365)
        if len(darr) > 1 and darr.std() > 0
        else 0
    )

    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr": round(rr, 2),
        "avg_r": round(np.mean(r_mults), 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "fees": round(sum(abs(t["pnl"]) * 0 for t in trades), 2),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "significant": abs(t_stat) > 1.96,
    }


def print_stats(label, s):
    print(
        "  {:<40} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "RR={:>4.2f} | AvgR={:>5.2f} | Sharpe={:>6.3f} | DD={:>6.1f}% | Final={:>10,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["rr"],
            s["avg_r"],
            s["sharpe"],
            s["max_dd_pct"],
            s["final"],
        )
    )
    if s.get("reasons"):
        print(
            "    {:<40} Reasons: {}  t-stat={:.3f} sig={}".format(
                "", s["reasons"], s["t_stat"], s["significant"]
            )
        )


def main():
    base = pathlib.Path(__file__).parent
    btc_path = base / "btc_usdt_4h_unified.csv"

    print("Loading data...")
    df = prepare_data(btc_path)
    print("Total: {} bars ({} ~ {})".format(len(df), df.index[0], df.index[-1]))
    print(
        "Bull Regime bars: {} / {} ({:.1f}%)".format(
            df["bull_regime"].sum(), len(df), df["bull_regime"].mean() * 100
        )
    )
    print()

    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    print(
        "IS: {} bars ({} ~ {})".format(
            len(df_is), df_is.index[0].date(), df_is.index[-1].date()
        )
    )
    print(
        "OOS: {} bars ({} ~ {})".format(
            len(df_oos), df_oos.index[0].date(), df_oos.index[-1].date()
        )
    )
    print()

    start_bal = 10_000.0

    # ==================================================================
    # PHASE 1: IS Parameter Sensitivity
    # ==================================================================
    print("=" * 140)
    print("PHASE 1: IN-SAMPLE PARAMETER SENSITIVITY")
    print("=" * 140)

    configs_is = [
        ("Default", EPMConfig()),
        ("No volume filter", EPMConfig(volume_surge=0.0)),
        ("No RSI filter", EPMConfig(rsi_oversold=100.0, rsi_recovery=0.0)),
        ("No pullback dist", EPMConfig(pullback_atr_dist=99.0)),
        ("No regime filter (test only)", EPMConfig()),
        ("RSI oversold=35", EPMConfig(rsi_oversold=35.0)),
        ("RSI oversold=40", EPMConfig(rsi_oversold=40.0)),
        ("RSI recovery=45", EPMConfig(rsi_recovery=45.0)),
        ("RSI recovery=50", EPMConfig(rsi_recovery=50.0)),
        ("Volume surge=1.3", EPMConfig(volume_surge=1.3)),
        ("Volume surge=2.0", EPMConfig(volume_surge=2.0)),
        ("ATR stop=1.8", EPMConfig(atr_stop_mult=1.8)),
        ("ATR stop=2.5", EPMConfig(atr_stop_mult=2.5)),
        ("ATR stop=3.0", EPMConfig(atr_stop_mult=3.0)),
        ("Time stop=20", EPMConfig(time_stop_bars=20)),
        ("Time stop=40", EPMConfig(time_stop_bars=40)),
        ("Trail at 1.0R", EPMConfig(trail_activation_r=1.0)),
        ("Trail at 2.0R", EPMConfig(trail_activation_r=2.0)),
        ("Pullback dist=0.3", EPMConfig(pullback_atr_dist=0.3)),
        ("Pullback dist=1.0", EPMConfig(pullback_atr_dist=1.0)),
    ]

    for name, cfg in configs_is:
        bt = EPMBacktest(cfg, start_bal)
        if name == "No regime filter (test only)":
            df_test = df_is.copy()
            df_test["bull_regime"] = 1
            bt.run(df_test)
        else:
            bt.run(df_is)
        s = calc_stats(bt.trades, start_bal)
        print_stats(name, s)

    # ==================================================================
    # PHASE 2: IS Grid Search
    # ==================================================================
    print()
    print("=" * 140)
    print("PHASE 2: IS GRID SEARCH")
    print("=" * 140)

    rsi_os_list = [35, 38, 40]
    rsi_rec_list = [45, 48, 50]
    vol_list = [0.0, 1.3, 1.6, 1.8]
    stop_list = [1.8, 2.0, 2.2, 2.5, 3.0]
    pb_list = [0.3, 0.5, 0.8, 1.0]

    grid_results = []
    total_combos = (
        len(rsi_os_list)
        * len(rsi_rec_list)
        * len(vol_list)
        * len(stop_list)
        * len(pb_list)
    )
    print(f"Testing {total_combos} combinations...")

    for rsi_os in rsi_os_list:
        for rsi_rec in rsi_rec_list:
            for vol in vol_list:
                for stop in stop_list:
                    for pb in pb_list:
                        cfg = EPMConfig(
                            rsi_oversold=float(rsi_os),
                            rsi_recovery=float(rsi_rec),
                            volume_surge=vol,
                            atr_stop_mult=stop,
                            pullback_atr_dist=pb,
                        )
                        bt = EPMBacktest(cfg, start_bal)
                        bt.run(df_is)
                        s = calc_stats(bt.trades, start_bal)
                        s["params"] = (
                            "RSI_OS={} RSI_REC={} VOL={} STOP={} PB={}".format(
                                rsi_os, rsi_rec, vol, stop, pb
                            )
                        )
                        grid_results.append(s)

    grid_results.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 15:")
    for s in grid_results[:15]:
        if s["n"] >= 5:
            print_stats(s["params"], s)

    # ==================================================================
    # PHASE 3: OOS Validation
    # ==================================================================
    print()
    print("=" * 140)
    print("PHASE 3: OUT-OF-SAMPLE VALIDATION")
    print("=" * 140)

    # Test top-5 IS configs on OOS
    tested = set()
    oos_results = []
    for is_result in grid_results:
        p = is_result["params"]
        if p in tested or is_result["n"] < 10:
            continue
        tested.add(p)

        parts = p.split()
        cfg = EPMConfig(
            rsi_oversold=float(parts[0].split("=")[1]),
            rsi_recovery=float(parts[1].split("=")[1]),
            volume_surge=float(parts[2].split("=")[1]),
            atr_stop_mult=float(parts[3].split("=")[1]),
            pullback_atr_dist=float(parts[4].split("=")[1]),
        )
        bt = EPMBacktest(cfg, start_bal)
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
            "    {:<40} IS: PnL={:>10,.2f} N={:>3} WR={:.1f}% PF={:.3f} | Delta={:>+10,.2f}".format(
                "", oos["is_pnl"], oos["is_n"], oos["is_wr"], oos["is_pf"], delta
            )
        )

    # Default on OOS
    print()
    bt_def = EPMBacktest(EPMConfig(), start_bal)
    bt_def.run(df_oos)
    oos_def = calc_stats(bt_def.trades, start_bal)
    print_stats("OOS Default", oos_def)

    # ==================================================================
    # VERDICT
    # ==================================================================
    print()
    print("=" * 140)
    print("VERDICT")
    print("=" * 140)

    best_oos = max(oos_results, key=lambda x: x["pnl"]) if oos_results else None
    if best_oos:
        print(f"\nBest OOS: {best_oos['params']}")
        print(
            f"  OOS: PnL={best_oos['pnl']:+,.2f}  N={best_oos['n']}  WR={best_oos['wr']}%  PF={best_oos['pf']}  DD={best_oos['max_dd_pct']}%"
        )
        print(
            f"  IS:  PnL={best_oos['is_pnl']:+,.2f}  N={best_oos['is_n']}  WR={best_oos['is_wr']}%  PF={best_oos['is_pf']}"
        )

    print(
        f"\nDefault OOS: PnL={oos_def['pnl']:+,.2f}  N={oos_def['n']}  WR={oos_def['wr']}%  PF={oos_def['pf']}"
    )

    print("\nAdoption Checklist:")
    checks = {}
    if best_oos:
        checks["IS Expectancy > 0"] = best_oos["is_pnl"] > 0
        checks["OOS Expectancy > 0"] = best_oos["pnl"] > 0
        checks["OOS N >= 20"] = best_oos["n"] >= 20
        checks["OOS PF > 1.2"] = best_oos["pf"] > 1.2
        checks["Max DD < 25%"] = best_oos["max_dd_pct"] < 25
        if best_oos["is_pnl"] != 0:
            divergence = (
                abs(best_oos["pnl"] - best_oos["is_pnl"])
                / abs(best_oos["is_pnl"])
                * 100
            )
            checks["IS/OOS divergence < 50%"] = divergence < 50
        else:
            checks["IS/OOS divergence < 50%"] = False
        checks["t-stat significant"] = best_oos.get("significant", False)

    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n>>> VALIDATED: Strategy shows positive EV in both IS and OOS <<<")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f"\n>>> NOT VALIDATED - Failed: {', '.join(failed)} <<<")
        print(">>> Do NOT deploy. <<<")


if __name__ == "__main__":
    main()
