"""
BFR-M v2.0 - Bitcoin Funding Regime Momentum - Backtest Engine
===============================================================
Hyperliquid Funding Rate + BTC 4h Supertrend Momentum Strategy

Full-fidelity backtest:
- Taker fee 0.035%, Slippage 0.1%
- ATR-based trailing stop (Supertrend)
- Time stop
- 70/30 IS/OOS split validation

Data sources:
- btc_usdt_4h_unified.csv (OHLCV 4h)
- data/btc_funding_rate.csv (HL funding rate 1h -> resampled to 4h)
"""

import pathlib
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class BFRMConfig:
    max_funding_threshold: float = 0.00038
    funding_spike_threshold: float = 2.0
    rsi_threshold: float = 53.0
    volume_multiplier: float = 1.95
    atr_stop_multiplier: float = 2.65
    time_stop_bars: int = 33  # 132h / 4h = 33 bars
    risk_per_trade: float = 0.0075
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0
    rsi_period: int = 14
    ema200_period: int = 200
    high_lookback: int = 20
    taker_fee: float = 0.00035
    slippage: float = 0.001


@dataclass
class Position:
    side: str = ""
    size: float = 0.0
    entry_px: float = 0.0
    entry_bar: int = 0
    stop: float = 0.0
    trailing_stop: float = 0.0


def calculate_supertrend(df, period=10, multiplier=3.0):
    hl2 = (df["high"] + df["low"]) / 2
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    st = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)

    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            st.iloc[i] = (
                max(lower_band.iloc[i], st.iloc[i - 1])
                if not np.isnan(st.iloc[i - 1])
                else lower_band.iloc[i]
            )
        else:
            st.iloc[i] = (
                min(upper_band.iloc[i], st.iloc[i - 1])
                if not np.isnan(st.iloc[i - 1])
                else upper_band.iloc[i]
            )

    df["supertrend"] = st
    df["supertrend_direction"] = direction
    return df


def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def prepare_data(btc_path, funding_path):
    btc = pd.read_csv(
        btc_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    funding = pd.read_csv(
        funding_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()

    funding_4h = funding.resample("4h").last().ffill()
    funding_4h.rename(columns={"fundingRate": "funding_rate"}, inplace=True)

    df = btc.join(funding_4h[["funding_rate"]], how="left")
    df["funding_rate"] = df["funding_rate"].ffill().bfill()

    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["rsi"] = calculate_rsi(df["close"], 14)
    df["rsi_prev"] = df["rsi"].shift(1)

    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, min_periods=14).mean()

    df = calculate_supertrend(df, period=10, multiplier=3.0)

    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["high_20"] = df["close"].rolling(20).max()

    df["funding_ma_6"] = df["funding_rate"].rolling(6).mean()

    df.dropna(
        subset=[
            "atr",
            "rsi",
            "supertrend",
            "ema_200",
            "funding_rate",
            "vol_ma20",
            "high_20",
        ],
        inplace=True,
    )
    return df


class BFRMBacktest:
    def __init__(self, cfg: BFRMConfig, start_balance: float = 10_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.pos: Optional[Position] = None
        self.trades: List[Dict] = []
        self.bar_idx = 0

    def _apply_slippage(self, px: float, side: str) -> float:
        if side == "LONG":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _open(self, row, idx: int):
        entry_px = self._apply_slippage(row["close"], "LONG")
        risk_budget = self.balance * self.cfg.risk_per_trade
        atr = row["atr"]
        sl_dist = self.cfg.atr_stop_multiplier * atr
        sz = risk_budget / sl_dist if sl_dist > 0 else 0
        sz = round(sz, 4)
        if sz <= 0:
            return

        fee = sz * entry_px * self.cfg.taker_fee
        self.balance -= fee

        self.pos = Position(
            side="LONG",
            size=sz,
            entry_px=entry_px,
            entry_bar=idx,
            stop=entry_px - sl_dist,
            trailing_stop=row["supertrend"],
        )

    def _close(self, exit_px: float, reason: str):
        if not self.pos:
            return
        fill_px = self._apply_slippage(exit_px, "sell")
        fee = self.pos.size * fill_px * self.cfg.taker_fee
        self.balance -= fee

        pnl = (fill_px - self.pos.entry_px) * self.pos.size

        self.trades.append(
            {
                "bar": self.pos.entry_bar,
                "exit_bar": self.bar_idx,
                "side": self.pos.side,
                "entry_px": self.pos.entry_px,
                "exit_px": fill_px,
                "size": self.pos.size,
                "pnl": pnl,
                "fee": fee,
                "reason": reason,
                "balance_after": self.balance,
            }
        )
        self.pos = None

    def _is_valid_regime(self, row) -> bool:
        current_fr = row["funding_rate"]
        recent_fr = row["funding_ma_6"]
        is_overheated = current_fr > self.cfg.max_funding_threshold
        is_spiking = (
            current_fr > recent_fr * self.cfg.funding_spike_threshold
            if recent_fr > 0
            else False
        )
        is_bull_trend = row["close"] > row["ema_200"]
        return not (is_overheated or is_spiking) and is_bull_trend

    def _generate_signal(self, df, idx: int) -> bool:
        row = df.iloc[idx]
        prev = df.iloc[idx - 1]

        if not self._is_valid_regime(row):
            return False

        cond_supertrend = row["supertrend_direction"] == 1
        cond_rsi = row["rsi"] >= self.cfg.rsi_threshold and row["rsi"] > prev["rsi"]
        cond_breakout = row["close"] >= row["high_20"]
        cond_volume = row["volume"] > row["vol_ma20"] * self.cfg.volume_multiplier

        return cond_supertrend and cond_rsi and cond_breakout and cond_volume

    def run(self, df):
        for i in range(30, len(df)):
            self.bar_idx = i
            row = df.iloc[i]

            if self.pos is not None:
                held = i - self.pos.entry_bar

                if held >= self.cfg.time_stop_bars:
                    self._close(row["close"], "TIME_STOP")
                    continue

                if row["supertrend"] > self.pos.trailing_stop:
                    self.pos.trailing_stop = row["supertrend"]

                if row["low"] <= self.pos.trailing_stop:
                    self._close(self.pos.trailing_stop, "TRAILING_STOP")
                    continue

            if self.pos is not None:
                continue

            if self._generate_signal(df, i):
                self._open(row, i)

        if self.pos is not None:
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
        }

    pnls = [t["pnl"] for t in trades]
    fees = sum(t["fee"] for t in trades)
    total_pnl = sum(pnls)
    n = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    wr = len(wins) / n * 100
    pf = sum(wins) / sum(losses) if losses else 0

    equity = np.cumsum(pnls) + start_bal
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = dd.max()
    max_dd_pct = max_dd / peak.max() * 100 if peak.max() > 0 else 0

    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1

    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

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
        "rr": round(rr_ratio, 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "fees": round(fees, 2),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
    }


def print_stats(label, s):
    print(
        "  {:<35} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "RR={:>4.2f} | Sharpe={:>6.3f} | DD={:>7,.2f} ({:.1f}%) | Fees={:>7,.2f} | Final={:>10,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["rr"],
            s["sharpe"],
            s["max_dd"],
            s["max_dd_pct"],
            s["fees"],
            s["final"],
        )
    )
    if s.get("reasons"):
        print("    {:<35} Reasons: {}".format("", s["reasons"]))


def main():
    base = pathlib.Path(__file__).parent
    btc_path = base / "btc_usdt_4h_unified.csv"
    funding_path = base / "data" / "btc_funding_rate.csv"

    print("Loading data...")
    df = prepare_data(btc_path, funding_path)
    print(f"Total: {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    print(
        f"Funding Rate range: {df['funding_rate'].min():.6f} ~ {df['funding_rate'].max():.6f}"
    )
    print(f"Mean FR: {df['funding_rate'].mean():.6f}")
    print()

    # Split 70/30
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
    # PHASE 1: IS Exploration - Parameter Sensitivity
    # ==================================================================
    print("=" * 130)
    print("PHASE 1: IN-SAMPLE EXPLORATION")
    print("=" * 130)

    configs_is = [
        ("Default params", BFRMConfig()),
        ("Lower FR threshold (0.0003)", BFRMConfig(max_funding_threshold=0.0003)),
        ("Higher FR threshold (0.0005)", BFRMConfig(max_funding_threshold=0.0005)),
        ("Lower volume mult (1.5)", BFRMConfig(volume_multiplier=1.5)),
        ("Higher volume mult (2.5)", BFRMConfig(volume_multiplier=2.5)),
        ("Lower RSI (50)", BFRMConfig(rsi_threshold=50.0)),
        ("Higher RSI (55)", BFRMConfig(rsi_threshold=55.0)),
        ("Tighter stop (2.0 ATR)", BFRMConfig(atr_stop_multiplier=2.0)),
        ("Wider stop (3.5 ATR)", BFRMConfig(atr_stop_multiplier=3.5)),
        ("Shorter time stop (24 bars)", BFRMConfig(time_stop_bars=24)),
        ("Longer time stop (44 bars)", BFRMConfig(time_stop_bars=44)),
        (
            "No FR filter",
            BFRMConfig(max_funding_threshold=99.0, funding_spike_threshold=99.0),
        ),
        ("No volume filter", BFRMConfig(volume_multiplier=0.0)),
        ("No breakout", BFRMConfig(volume_multiplier=0.0, rsi_threshold=0.0)),
        ("FR only + Supertrend", BFRMConfig(rsi_threshold=0.0, volume_multiplier=0.0)),
    ]

    is_results = []
    for name, cfg in configs_is:
        bt = BFRMBacktest(cfg, start_bal)
        bt.run(df_is)
        s = calc_stats(bt.trades, start_bal)
        s["name"] = name
        is_results.append(s)
        print_stats(name, s)

    # ==================================================================
    # PHASE 2: IS Grid Search for optimal combo
    # ==================================================================
    print()
    print("=" * 130)
    print("PHASE 2: IS GRID SEARCH")
    print("=" * 130)

    fr_thresholds = [0.00025, 0.0003, 0.00035, 0.00038, 0.0004, 0.0005]
    rsi_thresholds = [48, 50, 53, 55]
    vol_mults = [1.5, 1.8, 1.95, 2.2]
    stop_mults = [2.0, 2.5, 2.65, 3.0]

    grid_results = []
    for fr in fr_thresholds:
        for rsi in rsi_thresholds:
            for vm in vol_mults:
                for sm in stop_mults:
                    cfg = BFRMConfig(
                        max_funding_threshold=fr,
                        rsi_threshold=float(rsi),
                        volume_multiplier=vm,
                        atr_stop_multiplier=sm,
                    )
                    bt = BFRMBacktest(cfg, start_bal)
                    bt.run(df_is)
                    s = calc_stats(bt.trades, start_bal)
                    s["params"] = f"FR={fr} RSI={rsi} Vol={vm} Stop={sm}"
                    grid_results.append(s)

    grid_results.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 20 grid results (by PnL):")
    print_stats(
        "Config",
        {
            "pnl": 0,
            "n": 0,
            "wr": 0,
            "pf": 0,
            "rr": 0,
            "sharpe": 0,
            "max_dd": 0,
            "max_dd_pct": 0,
            "fees": 0,
            "final": 0,
            "reasons": {},
        },
    )
    for s in grid_results[:20]:
        print_stats(s["params"], s)

    # ==================================================================
    # PHASE 3: OOS Validation with locked top params
    # ==================================================================
    print()
    print("=" * 130)
    print("PHASE 3: OUT-OF-SAMPLE VALIDATION")
    print("=" * 130)

    top_n = min(5, len(grid_results))
    for i, is_result in enumerate(grid_results[:top_n]):
        p = is_result["params"]
        parts = p.split()
        fr = float(parts[0].split("=")[1])
        rsi = float(parts[1].split("=")[1])
        vm = float(parts[2].split("=")[1])
        sm = float(parts[3].split("=")[1])

        cfg = BFRMConfig(
            max_funding_threshold=fr,
            rsi_threshold=rsi,
            volume_multiplier=vm,
            atr_stop_multiplier=sm,
        )
        bt = BFRMBacktest(cfg, start_bal)
        bt.run(df_oos)
        oos = calc_stats(bt.trades, start_bal)

        print_stats(f"OOS #{i + 1}: {p}", oos)
        print(
            "    {:<35} IS PnL={:>10,.2f}  Delta={:>+10,.2f}".format(
                "", is_result["pnl"], oos["pnl"] - is_result["pnl"]
            )
        )

    # Also test default params on OOS
    print()
    bt_default = BFRMBacktest(BFRMConfig(), start_bal)
    bt_default.run(df_oos)
    oos_default = calc_stats(bt_default.trades, start_bal)
    print_stats("OOS Default params", oos_default)

    # ==================================================================
    # VERDICT
    # ==================================================================
    print()
    print("=" * 130)
    print("VERDICT")
    print("=" * 130)

    has_positive_oos = any(
        grid_results[i]["pnl"] > 0 for i in range(min(top_n, len(grid_results)))
    )

    best_oos = None
    best_is_params = grid_results[0]["params"] if grid_results else "N/A"
    for i in range(min(top_n, len(grid_results))):
        p = grid_results[i]["params"]
        parts = p.split()
        fr = float(parts[0].split("=")[1])
        rsi = float(parts[1].split("=")[1])
        vm = float(parts[2].split("=")[1])
        sm = float(parts[3].split("=")[1])

        cfg = BFRMConfig(
            max_funding_threshold=fr,
            rsi_threshold=rsi,
            volume_multiplier=vm,
            atr_stop_multiplier=sm,
        )
        bt = BFRMBacktest(cfg, start_bal)
        bt.run(df_oos)
        oos = calc_stats(bt.trades, start_bal)
        if best_oos is None or oos["pnl"] > best_oos["pnl"]:
            best_oos = oos
            best_oos["params"] = p

    print(f"\nBest IS params: {best_is_params}")
    if best_oos:
        print(f"Best OOS result: {best_oos['params']}")
        print(
            f"  OOS PnL={best_oos['pnl']:+,.2f}  WR={best_oos['wr']}%  PF={best_oos['pf']}  N={best_oos['n']}"
        )

    if best_oos and best_oos["pnl"] > 0 and best_oos["pf"] > 1.0:
        print("\n*** STRATEGY VALIDATED: OOS positive PnL + PF > 1.0 ***")
        print(f"*** Recommended params: {best_oos['params']} ***")
    elif best_oos and best_oos["pnl"] > 0:
        print("\n*** MARGINAL: OOS positive PnL but PF <= 1.0. Use with caution. ***")
    else:
        print("\n*** NOT VALIDATED: OOS PnL is negative. Do NOT deploy. ***")

    print(
        f"\nDefault params OOS: PnL={oos_default['pnl']:+,.2f}  WR={oos_default['wr']}%  PF={oos_default['pf']}  N={oos_default['n']}"
    )


if __name__ == "__main__":
    main()
