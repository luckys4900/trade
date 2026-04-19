# bt_full_fidelity.py
"""
Full-fidelity backtest reproducing qwen_unified_live.py contrarian logic.
- SL/TP/max_hold exactly as live code
- Taker fee 0.035% per trade (open + close)
- Slippage 0.1% on entry/exit
- Out-of-sample validation (70/30 split)
- Uses REAL kronos_4h_preds_full.csv predictions
"""

import sys, pathlib, json
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

sys.path.append(str(pathlib.Path(__file__).parent))
from SYSTEM import qwen_unified_live as live


# ------------------------------------------------------------------
# Config (matches live bot exactly)
# ------------------------------------------------------------------
@dataclass
class BTConfig:
    contrarian_capital_pct: float = 0.70
    contrarian_risk_pct: float = 0.04
    contrarian_sl_atr_mult: float = 2.0
    contrarian_tp_atr_mult: float = 4.0
    contrarian_max_hold: int = 8
    contrarian_max_position_pct: float = 0.30
    edge_filter_enabled: bool = False
    edge_filter_rsi_threshold: float = 55.0
    edge_filter_trend: str = "UPTREND"
    taker_fee: float = 0.00035
    slippage: float = 0.001


# ------------------------------------------------------------------
# Position State
# ------------------------------------------------------------------
@dataclass
class Position:
    side: str = ""
    size: float = 0.0
    entry_px: float = 0.0
    stop: float = 0.0
    tp: float = 0.0
    entry_bar: int = 0
    entry_ts: str = ""


# ------------------------------------------------------------------
# Full-Fidelity Backtest Engine
# ------------------------------------------------------------------
class FullFidelityBT:
    def __init__(self, cfg: BTConfig, start_balance: float = 200_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.pos: Optional[Position] = None
        self.trades = []
        self.bar_idx = 0

    def _pool_total(self) -> float:
        return self.balance * self.cfg.contrarian_capital_pct

    def _risk_budget(self) -> float:
        return self._pool_total() * self.cfg.contrarian_risk_pct

    def _position_cap(self) -> float:
        return self._pool_total() * self.cfg.contrarian_max_position_pct

    def _available_notional(self, px: float) -> float:
        used = (self.pos.size * px) if self.pos and self.pos.side else 0.0
        return max(0.0, self._pool_total() - used)

    def _apply_slippage(self, px: float, side: str) -> float:
        if side == "LONG":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _calc_size(self, atr: float, px: float) -> float:
        sl_d = self.cfg.contrarian_sl_atr_mult * atr
        if sl_d <= 0:
            return 0.0
        risk = self._risk_budget()
        cap = self._position_cap()
        avail = self._available_notional(px)
        sz = min(risk / sl_d, cap / px, avail / px)
        sz = live.round_order_size(sz, 4)
        return sz

    def _open(self, side: str, sz: float, px: float, atr: float):
        fill_px = self._apply_slippage(px, side)
        fee = sz * fill_px * self.cfg.taker_fee
        self.balance -= fee

        sl = (
            fill_px - self.cfg.contrarian_sl_atr_mult * atr
            if side == "LONG"
            else fill_px + self.cfg.contrarian_sl_atr_mult * atr
        )
        tp = (
            fill_px + self.cfg.contrarian_tp_atr_mult * atr
            if side == "LONG"
            else fill_px - self.cfg.contrarian_tp_atr_mult * atr
        )

        self.pos = Position(
            side=side,
            size=sz,
            entry_px=fill_px,
            stop=sl,
            tp=tp,
            entry_bar=self.bar_idx,
        )

    def _close(self, exit_px: float, reason: str):
        if not self.pos:
            return
        side = self.pos.side
        fill_px = self._apply_slippage(exit_px, "sell" if side == "LONG" else "buy")
        fee = self.pos.size * fill_px * self.cfg.taker_fee
        self.balance -= fee

        if side == "LONG":
            pnl = (fill_px - self.pos.entry_px) * self.pos.size
        else:
            pnl = (self.pos.entry_px - fill_px) * self.pos.size

        self.trades.append(
            {
                "bar": self.pos.entry_bar,
                "exit_bar": self.bar_idx,
                "side": side,
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

    def _manage_exit(self, high: float, low: float, close: float):
        if not self.pos:
            return
        held = self.bar_idx - self.pos.entry_bar

        # Max hold
        if held >= self.cfg.contrarian_max_hold:
            self._close(close, "MAX_HOLD")
            return

        # SL/TP check using bar high/low (more realistic than close-only)
        if self.pos.side == "LONG":
            if self.pos.stop > 0 and low <= self.pos.stop:
                self._close(self.pos.stop, "STOP_LOSS")
                return
            if self.pos.tp > 0 and high >= self.pos.tp:
                self._close(self.pos.tp, "TAKE_PROFIT")
                return
        else:
            if self.pos.stop > 0 and high >= self.pos.stop:
                self._close(self.pos.stop, "STOP_LOSS")
                return
            if self.pos.tp > 0 and low <= self.pos.tp:
                self._close(self.pos.tp, "TAKE_PROFIT")
                return

    def run(self, df, kronos_bar_map):
        """df: subset of the full dataframe. kronos_bar_map: {local_bar_idx: pred_dir}"""
        for i in range(len(df)):
            self.bar_idx = i
            row = df.iloc[i]
            high, low, close = row["high"], row["low"], row["close"]
            atr = row["atr"]

            # Manage existing position
            self._manage_exit(high, low, close)

            # Check new entry
            if self.pos is not None:
                continue
            if i not in kronos_bar_map:
                continue

            pred_dir = kronos_bar_map[i]
            if atr <= 0 or np.isnan(atr):
                continue

            # Edge filter
            if self.cfg.edge_filter_enabled:
                rsi = row.get("rsi", 0)
                trend = row.get("ocpm_trend", "")
                if not (
                    rsi > self.cfg.edge_filter_rsi_threshold
                    and trend == self.cfg.edge_filter_trend
                ):
                    continue

            sz = self._calc_size(atr, close)
            if sz <= 0:
                continue

            # Contrarian: reverse Kronos direction
            side = "SHORT" if pred_dir == 1 else "LONG"
            self._open(side, sz, close, atr)

        # Force-close any remaining position
        if self.pos:
            self._close(df.iloc[-1]["close"], "END_OF_DATA")


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------
def compute_stats(trades, start_bal):
    if not trades:
        return {
            "pnl": 0,
            "trades": 0,
            "wr": 0,
            "pf": 0,
            "sharpe": 0,
            "max_dd": 0,
            "max_dd_pct": 0,
            "total_fees": 0,
            "final_bal": start_bal,
        }

    pnls = [t["pnl"] for t in trades]
    fees = [t["fee"] for t in trades]
    total_pnl = sum(pnls)
    total_fees = sum(fees)
    n = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    wr = len(wins) / n * 100
    pf = sum(wins) / sum(losses) if losses else 0

    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = dd.max()
    max_dd_pct = max_dd / start_bal * 100

    # Sharpe (daily, ~6 bars/day)
    daily_chunks = np.array_split(pnls, max(1, len(pnls) // 6))
    daily_sums = [sum(c) for c in daily_chunks if len(c) > 0]
    darr = np.array(daily_sums)
    sharpe = darr.mean() / darr.std() if len(darr) > 1 and darr.std() > 0 else 0

    # Exit reason breakdown
    reasons = {}
    for t in trades:
        r = t["reason"]
        reasons[r] = reasons.get(r, 0) + 1

    return {
        "pnl": round(total_pnl, 2),
        "trades": n,
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "total_fees": round(total_fees, 2),
        "final_bal": round(start_bal + total_pnl, 2),
        "exit_reasons": reasons,
    }


def print_stats(label, stats):
    print(
        f"  {label:<30} PnL={stats['pnl']:>+12,.2f} | N={stats['trades']:>4} | "
        f"WR={stats['wr']:>5.1f}% | PF={stats['pf']:>5.3f} | "
        f"Sharpe={stats['sharpe']:>6.3f} | DD={stats['max_dd']:>10,.2f} ({stats['max_dd_pct']:.1f}%) | "
        f"Fees={stats['total_fees']:>8,.2f} | Final={stats['final_bal']:>12,.2f}"
    )
    if stats.get("exit_reasons"):
        print(f"    {'':30} Exit reasons: {stats['exit_reasons']}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    csv_path = pathlib.Path(__file__).parent / "btc_usdt_4h_unified.csv"
    raw = pd.read_csv(
        csv_path, parse_dates=["datetime"], index_col="datetime"
    ).sort_index()
    cfg_ind = live.Config()
    df = live.compute_indicators(raw.copy(), cfg_ind).dropna(subset=["atr", "rsi"])

    preds = pd.read_csv(pathlib.Path(__file__).parent / "kronos_4h_preds_full.csv")

    # Build bar->prediction map
    kronos_bar_map = {}
    for _, row in preds.iterrows():
        bar_idx = int(row["bar"])
        if 0 <= bar_idx < len(df):
            kronos_bar_map[bar_idx] = int(row["dir"])

    # Split: 70% in-sample, 30% out-of-sample
    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    # Build separate kronos maps (bar indices are positions in the ORIGINAL full df)
    km_is = {k: v for k, v in kronos_bar_map.items() if k < split_idx}
    km_oos = {k: v for k, v in kronos_bar_map.items() if k >= split_idx}
    # For OOS, remap global indices to local positions (0-based within df_oos)
    oos_offset = split_idx
    km_oos_local = {k - oos_offset: v for k, v in km_oos.items()}

    print(f"Data: {len(df)} total bars")
    print(
        f"  In-sample:      {len(df_is)} bars ({df_is.index[0].date()} to {df_is.index[-1].date()})"
    )
    print(
        f"  Out-of-sample:  {len(df_oos)} bars ({df_oos.index[0].date()} to {df_oos.index[-1].date()})"
    )
    print(f"Kronos predictions: {len(km_is)} in-sample, {len(km_oos)} out-of-sample")
    print()

    # Measure accuracy per split
    def measure_accuracy(df_sub, km):
        correct = 0
        total = 0
        for bar_idx, pred_dir in km.items():
            if bar_idx >= len(df_sub) - 1 or bar_idx < 0:
                continue
            actual_dir = (
                1
                if df_sub.iloc[bar_idx + 1]["close"] > df_sub.iloc[bar_idx]["close"]
                else -1
            )
            if pred_dir == actual_dir:
                correct += 1
            total += 1
        return correct, total

    c_is, t_is = measure_accuracy(df, km_is)
    c_oos, t_oos = measure_accuracy(df, km_oos)
    print(
        f"Kronos accuracy:  IS={c_is}/{t_is}={c_is / t_is * 100:.1f}%  OOS={c_oos}/{t_oos}={c_oos / t_oos * 100:.1f}%"
    )
    print()

    # ------------------------------------------------------------------
    # PHASE 1: In-sample exploration (lock parameters here)
    # ------------------------------------------------------------------
    print("=" * 110)
    print("PHASE 1: IN-SAMPLE EXPLORATION (lock parameters after this)")
    print("=" * 110)

    start_bal = 200_000.0

    configs_is = [
        ("No filter (baseline)", BTConfig(edge_filter_enabled=False)),
        (
            "RSI>55 & UPTREND",
            BTConfig(
                edge_filter_enabled=True,
                edge_filter_rsi_threshold=55.0,
                edge_filter_trend="UPTREND",
            ),
        ),
        ("RSI 55-70", BTConfig(edge_filter_enabled=True)),
        (
            "RSI>60 & UPTREND",
            BTConfig(
                edge_filter_enabled=True,
                edge_filter_rsi_threshold=60.0,
                edge_filter_trend="UPTREND",
            ),
        ),
    ]

    for name, bt_cfg in configs_is:
        bt = FullFidelityBT(bt_cfg, start_bal)
        if name == "RSI 55-70":
            # Custom: use edge filter with RSI 55-70 range
            bt.cfg.edge_filter_enabled = False
            # Run manually with RSI range filter
            for i in range(len(df_is)):
                bt.bar_idx = i
                row = df_is.iloc[i]
                bt._manage_exit(row["high"], row["low"], row["close"])
                if bt.pos is not None:
                    continue
                if i not in km_is:
                    continue
                pred_dir = km_is[i]
                atr = row["atr"]
                if atr <= 0 or np.isnan(atr):
                    continue
                rsi = row.get("rsi", 0)
                if not (55 <= rsi < 70):
                    continue
                sz = bt._calc_size(atr, row["close"])
                if sz <= 0:
                    continue
                side = "SHORT" if pred_dir == 1 else "LONG"
                bt._open(side, sz, row["close"], atr)
            if bt.pos:
                bt._close(df_is.iloc[-1]["close"], "END_OF_DATA")
        else:
            bt.run(df_is, km_is)
        stats = compute_stats(bt.trades, start_bal)
        print_stats(name, stats)

    # ------------------------------------------------------------------
    # PHASE 2: Out-of-sample validation with LOCKED parameters
    # ------------------------------------------------------------------
    print()
    print("=" * 110)
    print("PHASE 2: OUT-OF-SAMPLE VALIDATION (locked parameters from Phase 1)")
    print("=" * 110)

    # Based on in-sample results, lock the best filter
    # We test both "no filter" and "RSI>55 & UPTREND" on OOS data
    oos_configs = [
        ("No filter (baseline)", BTConfig(edge_filter_enabled=False)),
        (
            "RSI>55 & UPTREND (locked)",
            BTConfig(
                edge_filter_enabled=True,
                edge_filter_rsi_threshold=55.0,
                edge_filter_trend="UPTREND",
            ),
        ),
    ]

    for name, bt_cfg in oos_configs:
        bt = FullFidelityBT(bt_cfg, start_bal)
        bt.run(df_oos, km_oos_local)
        stats = compute_stats(bt.trades, start_bal)
        print_stats(name, stats)

    # ------------------------------------------------------------------
    # VERDICT
    # ------------------------------------------------------------------
    print()
    print("=" * 110)
    print("VERDICT")
    print("=" * 110)
    print("Compare Phase 1 (IS) vs Phase 2 (OOS) for each strategy.")
    print(
        "If OOS shows: (a) positive PnL, (b) WR > 50%, (c) PF > 1.0 => filter is validated"
    )
    print("If OOS shows degradation vs IS => likely overfit, do NOT deploy")
    print("If OOS shows negative PnL => filter is NOT reliable")


if __name__ == "__main__":
    main()
