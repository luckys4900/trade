"""
BTC-ETH Pair Trading Strategy - Full Fidelity Backtest
======================================================
Cointegration-based statistical arbitrage on Hyperliquid

1. Statistical Analysis:
   - Engle-Granger cointegration test
   - Z-Score of price ratio (BTC/ETH)
   - Half-life estimation (mean reversion speed)

2. Entry: Z-Score > +2.0 (short BTC, long ETH) or < -2.0 (long BTC, short ETH)
3. Exit: Z-Score reverts to 0, or SL/TP/time stop
4. IS/OOS 70/30 split validation
"""

import pathlib
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional
from statsmodels.tsa.stattools import coint, adfuller
from scipy import stats as scipy_stats


@dataclass
class PairConfig:
    lookback: int = 100
    z_entry: float = 2.0
    z_exit: float = 0.0
    z_stop: float = 3.5
    hedge_ratio_method: str = "ols"
    risk_per_trade: float = 0.01
    time_stop_bars: int = 40
    taker_fee: float = 0.00035
    slippage: float = 0.001


def load_pair_data(btc_path, eth_path):
    btc = pd.read_csv(
        btc_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    eth = pd.read_csv(
        eth_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()

    common = btc.index.intersection(eth.index)
    btc = btc.loc[common].copy()
    eth = eth.loc[common].copy()

    btc.columns = [f"btc_{c}" if c not in ["datetime"] else c for c in btc.columns]
    eth.columns = [f"eth_{c}" if c not in ["datetime"] else c for c in eth.columns]

    df = pd.concat([btc, eth], axis=1).dropna()
    return df


def cointegration_test(df):
    btc_close = df["btc_close"]
    eth_close = df["eth_close"]

    score, pvalue, critical = coint(btc_close, eth_close)
    adf_result = adfuller(btc_close / eth_close)

    X = np.column_stack([np.ones(len(eth_close)), eth_close.values])
    beta = np.linalg.lstsq(X, btc_close.values, rcond=None)[0]
    hedge_ratio = beta[1]
    spread = btc_close.values - hedge_ratio * eth_close.values

    spread_series = pd.Series(spread, index=df.index)
    half_life = (
        -np.log(2) / adfuller(spread_series.dropna())[0]
        if adfuller(spread_series.dropna())[0] < 0
        else 999
    )

    return {
        "coint_stat": round(score, 4),
        "coint_pvalue": round(pvalue, 6),
        "coint_critical": {
            "1%": round(critical[0], 4),
            "5%": round(critical[1], 4),
            "10%": round(critical[2], 4),
        },
        "adf_stat": round(adf_result[0], 4),
        "adf_pvalue": round(adf_result[1], 6),
        "hedge_ratio": round(hedge_ratio, 6),
        "half_life_bars": round(half_life, 1) if half_life < 999 else "inf",
        "spread_mean": round(spread_series.mean(), 2),
        "spread_std": round(spread_series.std(), 2),
        "is_cointegrated": pvalue < 0.05,
    }


class PairBacktest:
    def __init__(self, cfg: PairConfig, start_balance: float = 10_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.trades: List[Dict] = []
        self.bar_idx = 0
        self.in_pos = False
        self.pos_direction = 0
        self.entry_bar = 0
        self.entry_zscore = 0.0
        self.btc_size = 0.0
        self.eth_size = 0.0
        self.btc_entry_px = 0.0
        self.eth_entry_px = 0.0
        self.hedge_ratio = 0.0

    def _fee(self, notional):
        return notional * self.cfg.taker_fee

    def _apply_slip(self, px, side):
        if side == "buy":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _open(self, row, z_score, hedge_ratio, direction):
        btc_px = self._apply_slip(row["btc_close"], "sell" if direction > 0 else "buy")
        eth_px = self._apply_slip(row["eth_close"], "buy" if direction > 0 else "sell")

        risk_budget = self.balance * self.cfg.risk_per_trade

        btc_notional = risk_budget / 2
        eth_notional = btc_notional * hedge_ratio

        self.btc_size = btc_notional / btc_px
        self.eth_size = eth_notional / eth_px

        self.balance -= self._fee(btc_notional)
        self.balance -= self._fee(eth_notional)

        self.in_pos = True
        self.pos_direction = direction
        self.entry_bar = self.bar_idx
        self.entry_zscore = z_score
        self.btc_entry_px = btc_px
        self.eth_entry_px = eth_px
        self.hedge_ratio = hedge_ratio

    def _close(self, row, reason):
        if not self.in_pos:
            return

        if self.pos_direction > 0:
            btc_fill = self._apply_slip(row["btc_close"], "buy")
            eth_fill = self._apply_slip(row["eth_close"], "sell")
            btc_pnl = (self.btc_entry_px - btc_fill) * self.btc_size
            eth_pnl = (eth_fill - self.eth_entry_px) * self.eth_size
        else:
            btc_fill = self._apply_slip(row["btc_close"], "sell")
            eth_fill = self._apply_slip(row["eth_close"], "buy")
            btc_pnl = (btc_fill - self.btc_entry_px) * self.btc_size
            eth_pnl = (self.eth_entry_px - eth_fill) * self.eth_size

        self.balance -= self._fee(abs(self.btc_size * btc_fill))
        self.balance -= self._fee(abs(self.eth_size * eth_fill))

        total_pnl = btc_pnl + eth_pnl

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "direction": "SHORT_BTC_LONG_ETH"
                if self.pos_direction > 0
                else "LONG_BTC_SHORT_ETH",
                "entry_z": round(self.entry_zscore, 2),
                "pnl": round(total_pnl, 2),
                "btc_pnl": round(btc_pnl, 2),
                "eth_pnl": round(eth_pnl, 2),
                "reason": reason,
                "balance_after": round(self.balance, 2),
            }
        )
        self.in_pos = False

    def run(self, df, hedge_ratio):
        btc_c = df["btc_close"].values
        eth_c = df["eth_close"].values
        spread = btc_c - hedge_ratio * eth_c
        spread_series = pd.Series(spread, index=df.index)

        z_scores = np.full(len(df), np.nan)

        for i in range(self.cfg.lookback, len(df)):
            window = spread_series.iloc[i - self.cfg.lookback : i]
            mean = window.mean()
            std = window.std()
            if std > 0:
                z_scores[i] = (spread[i] - mean) / std

        z_series = pd.Series(z_scores, index=df.index)

        for i in range(self.cfg.lookback + 1, len(df)):
            self.bar_idx = i
            z = z_series.iloc[i]
            if np.isnan(z):
                continue

            row = df.iloc[i]

            if self.in_pos:
                held = i - self.entry_bar

                if self.pos_direction > 0 and z <= self.cfg.z_exit:
                    self._close(row, "Z_REVERT")
                    continue
                elif self.pos_direction < 0 and z >= self.cfg.z_exit:
                    self._close(row, "Z_REVERT")
                    continue

                if abs(z) >= self.cfg.z_stop:
                    self._close(row, "Z_STOP")
                    continue

                if held >= self.cfg.time_stop_bars:
                    self._close(row, "TIME_STOP")
                    continue

            if self.in_pos:
                continue

            if z >= self.cfg.z_entry:
                self._open(row, z, hedge_ratio, 1)
            elif z <= -self.cfg.z_entry:
                self._open(row, z, hedge_ratio, -1)


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

    daily_chunks = np.array_split(pnls, max(1, len(pnls) // 6))
    daily_sums = [sum(c) for c in daily_chunks]
    darr = np.array(daily_sums)
    sharpe = (
        darr.mean() / darr.std() * np.sqrt(365)
        if len(darr) > 1 and darr.std() > 0
        else 0
    )

    months = max(1, (len(trades) * 6 * 4) / (len(pnls) * 30))
    tpm = n / max(1, len(pnls) * 4 * 30 / (len(pnls)))

    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "significant": abs(t_stat) > 1.96,
    }


def print_stats(label, s):
    print(
        "  {:<45} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "Sharpe={:>6.3f} | DD={:>5.1f}% | Final={:>10,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["sharpe"],
            s["max_dd_pct"],
            s["final"],
        )
    )
    if s.get("reasons"):
        print(
            "    {:<45} Reasons: {}  t={:.2f} sig={}".format(
                "", s["reasons"], s["t_stat"], s["significant"]
            )
        )


def main():
    base = pathlib.Path(__file__).parent
    btc_path = base / "btc_usdt_4h_unified.csv"
    eth_path = base / "data" / "eth_usdt_4h.csv"

    print("Loading pair data...")
    df = load_pair_data(btc_path, eth_path)
    print("Combined: {} bars ({} ~ {})".format(len(df), df.index[0], df.index[-1]))
    print()

    # ==================================================================
    # STATISTICAL ANALYSIS
    # ==================================================================
    print("=" * 130)
    print("STATISTICAL ANALYSIS")
    print("=" * 130)

    coint_result = cointegration_test(df)
    print("Cointegration test:")
    for k, v in coint_result.items():
        print("  {}: {}".format(k, v))
    print()
    print("Cointegrated (p<0.05)? {}".format(coint_result["is_cointegrated"]))
    print("Hedge ratio (BTC per ETH): {}".format(coint_result["hedge_ratio"]))
    print("Half-life: {} bars".format(coint_result["half_life_bars"]))
    print()

    # Split
    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    is_months = (df_is.index[-1] - df_is.index[0]).days / 30
    oos_months = (df_oos.index[-1] - df_oos.index[0]).days / 30
    print("IS: {} bars ({:.0f} months)".format(len(df_is), is_months))
    print("OOS: {} bars ({:.0f} months)".format(len(df_oos), oos_months))

    # Cointegration per period
    print("\nIS cointegration:")
    is_coint = cointegration_test(df_is)
    print(
        "  p-value: {}  Cointegrated: {}".format(
            is_coint["coint_pvalue"], is_coint["is_cointegrated"]
        )
    )
    print("  Hedge ratio: {}".format(is_coint["hedge_ratio"]))
    print("\nOOS cointegration:")
    oos_coint = cointegration_test(df_oos)
    print(
        "  p-value: {}  Cointegrated: {}".format(
            oos_coint["coint_pvalue"], oos_coint["is_cointegrated"]
        )
    )
    print()

    # Lock hedge ratio from IS
    hr_locked = is_coint["hedge_ratio"]

    # ==================================================================
    # PHASE 1: IS Parameter Sensitivity
    # ==================================================================
    print("=" * 130)
    print("PHASE 1: IN-SAMPLE PARAMETER SENSITIVITY")
    print("=" * 130)

    start_bal = 10_000.0

    configs_is = [
        ("Default (Z=2.0, LB=100)", PairConfig()),
        ("Z=1.5, LB=100", PairConfig(z_entry=1.5)),
        ("Z=2.5, LB=100", PairConfig(z_entry=2.5)),
        ("Z=3.0, LB=100", PairConfig(z_entry=3.0)),
        ("Z=2.0, LB=60", PairConfig(lookback=60)),
        ("Z=2.0, LB=200", PairConfig(lookback=200)),
        ("Z=1.5, LB=60", PairConfig(z_entry=1.5, lookback=60)),
        ("Z=1.5, LB=200", PairConfig(z_entry=1.5, lookback=200)),
        ("Z=2.5, LB=60", PairConfig(z_entry=2.5, lookback=60)),
        ("Z=2.0, TimeStop=20", PairConfig(time_stop_bars=20)),
        ("Z=2.0, TimeStop=60", PairConfig(time_stop_bars=60)),
        ("Z=1.5, TimeStop=30", PairConfig(z_entry=1.5, time_stop_bars=30)),
        ("Z=2.0, ZStop=4.0", PairConfig(z_stop=4.0)),
        ("Z=2.0, ZStop=2.5", PairConfig(z_stop=2.5)),
    ]

    is_results = []
    for name, cfg in configs_is:
        bt = PairBacktest(cfg, start_bal)
        bt.run(df_is, hr_locked)
        s = calc_stats(bt.trades, start_bal)
        s["name"] = name
        is_results.append(s)
        print_stats(name, s)

    # ==================================================================
    # PHASE 2: IS Grid Search
    # ==================================================================
    print()
    print("=" * 130)
    print("PHASE 2: IS GRID SEARCH")
    print("=" * 130)

    z_entries = [1.5, 2.0, 2.5]
    lookbacks = [60, 100, 150, 200]
    time_stops = [20, 30, 40, 60]
    z_stops = [2.5, 3.0, 3.5, 4.0]

    grid_results = []
    total = len(z_entries) * len(lookbacks) * len(time_stops) * len(z_stops)
    print("Testing {} combinations...".format(total))

    for z_e in z_entries:
        for lb in lookbacks:
            for ts in time_stops:
                for z_s in z_stops:
                    cfg = PairConfig(
                        z_entry=z_e, lookback=lb, time_stop_bars=ts, z_stop=z_s
                    )
                    bt = PairBacktest(cfg, start_bal)
                    bt.run(df_is, hr_locked)
                    s = calc_stats(bt.trades, start_bal)
                    s["params"] = "Z={} LB={} TS={} ZS={}".format(z_e, lb, ts, z_s)
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
    print("=" * 130)
    print("PHASE 3: OUT-OF-SAMPLE VALIDATION")
    print("=" * 130)

    tested = set()
    oos_results = []
    for is_result in grid_results:
        p = is_result["params"]
        if p in tested or is_result["n"] < 5:
            continue
        tested.add(p)

        parts = p.split()
        z_e = float(parts[0].split("=")[1])
        lb = int(parts[1].split("=")[1])
        ts = int(parts[2].split("=")[1])
        z_s = float(parts[3].split("=")[1])

        cfg = PairConfig(z_entry=z_e, lookback=lb, time_stop_bars=ts, z_stop=z_s)
        bt = PairBacktest(cfg, start_bal)
        bt.run(df_oos, hr_locked)
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
            "    {:<45} IS: PnL={:>10,.2f} N={:>3} WR={:.1f}% PF={:.3f} | Delta={:>+10,.2f}".format(
                "", oos["is_pnl"], oos["is_n"], oos["is_wr"], oos["is_pf"], delta
            )
        )

    # Default OOS
    print()
    bt_def = PairBacktest(PairConfig(), start_bal)
    bt_def.run(df_oos, hr_locked)
    oos_def = calc_stats(bt_def.trades, start_bal)
    print_stats("OOS Default", oos_def)

    # ==================================================================
    # VERDICT
    # ==================================================================
    print()
    print("=" * 130)
    print("VERDICT")
    print("=" * 130)

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
        checks["Cointegrated (IS)"] = is_coint["is_cointegrated"]
        checks["Cointegrated (OOS)"] = oos_coint["is_cointegrated"]
        checks["OOS Expectancy > 0"] = target["pnl"] > 0
        checks["OOS N >= 20"] = target["n"] >= 20
        checks["OOS PF > 1.2"] = target["pf"] > 1.2
        checks["Max DD < 15%"] = target["max_dd_pct"] < 15
        checks["OOS WR >= 50%"] = target["wr"] >= 50
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
