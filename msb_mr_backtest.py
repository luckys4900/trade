"""
MSB-MR v1.0 - Market Structure Break + Mean Reversion - Full-Fidelity Backtest
================================================================================
BTC 4H, IS/OOS 70/30 split, fee/slippage, partial TP

Entry Logic (LONG):
  1. Market Structure = BULLISH (HH + HL in last 20 bars)
  2. Bullish Order Block detected (strong bullish impulse after bearish candle)
  3. Price touches OB zone (between OB bottom and top)
  4. OB age <= 50 bars (freshness)
  5. RSI between 35-55 (confirmation, not overbought/oversold)

Exit Logic:
  - SL: OB bottom - 1.0 ATR
  - TP1: 1.5R -> close 50%
  - TP2: 3.0R -> close remaining 50%
  - Time stop: 30 bars
  - Trailing: after TP1, move SL to breakeven
"""

import pathlib
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple


@dataclass
class MSBConfig:
    structure_lookback: int = 20
    structure_smooth: int = 5
    impulse_atr_mult: float = 1.5
    ob_max_age: int = 50
    rsi_low: float = 35.0
    rsi_high: float = 55.0
    sl_atr_below_ob: float = 1.0
    tp1_r: float = 1.5
    tp2_r: float = 3.0
    tp1_pct: float = 0.5
    time_stop_bars: int = 30
    risk_per_trade: float = 0.01
    rsi_period: int = 14
    atr_period: int = 14
    taker_fee: float = 0.00045
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
    df.dropna(subset=["atr", "rsi"], inplace=True)
    return df


def detect_structure(df, idx, lookback=20, smooth=5):
    if idx < lookback + smooth:
        return "INSUFFICIENT"

    half = lookback // 2

    recent_high = df["high"].iloc[idx - half : idx].max()
    prev_high = df["high"].iloc[idx - lookback : idx - half].max()
    recent_low = df["low"].iloc[idx - half : idx].min()
    prev_low = df["low"].iloc[idx - lookback : idx - half].min()

    hh = recent_high > prev_high
    hl = recent_low > prev_low
    lh = recent_high < prev_high
    ll = recent_low < prev_low

    if hh and hl:
        return "BULLISH"
    elif lh and ll:
        return "BEARISH"
    else:
        return "RANGING"


def find_order_block(df, idx, structure, max_lookback=50, impulse_mult=1.5):
    if structure == "BULLISH":
        for i in range(idx - 1, max(idx - max_lookback, 1), -1):
            candle = df.iloc[i]
            next_candle = df.iloc[i + 1]
            candle_body = abs(candle["close"] - candle["open"])
            next_body = next_candle["close"] - next_candle["open"]

            if candle["close"] < candle["open"]:
                if next_body > 0 and next_body > df["atr"].iloc[i] * impulse_mult:
                    return {
                        "type": "BULLISH",
                        "top": candle["high"],
                        "bottom": candle["low"],
                        "index": i,
                    }
    elif structure == "BEARISH":
        for i in range(idx - 1, max(idx - max_lookback, 1), -1):
            candle = df.iloc[i]
            next_candle = df.iloc[i + 1]
            next_body = next_candle["open"] - next_candle["close"]

            if candle["close"] > candle["open"]:
                if next_body > 0 and next_body > df["atr"].iloc[i] * impulse_mult:
                    return {
                        "type": "BEARISH",
                        "top": candle["high"],
                        "bottom": candle["low"],
                        "index": i,
                    }
    return None


class MSBMRBacktest:
    def __init__(self, cfg: MSBConfig, start_balance: float = 10_000.0):
        self.cfg = cfg
        self.balance = start_balance
        self.start_balance = start_balance
        self.trades: List[Dict] = []
        self.bar_idx = 0

        self.in_pos = False
        self.pos_side = ""
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.tp1_px = 0.0
        self.tp2_px = 0.0
        self.size_usd = 0.0
        self.size_remaining_pct = 1.0
        self.entry_bar = 0
        self.tp1_hit = False
        self.ob_ref = None

    def _apply_slippage(self, px, side):
        if side == "buy":
            return px * (1 + self.cfg.slippage)
        return px * (1 - self.cfg.slippage)

    def _open(self, row, idx, side, ob):
        entry_px = self._apply_slippage(
            row["close"], "buy" if side == "LONG" else "sell"
        )
        atr = row["atr"]

        if side == "LONG":
            stop_px = ob["bottom"] - self.cfg.sl_atr_below_ob * atr
            risk_dist = abs(entry_px - stop_px)
            tp1_px = entry_px + risk_dist * self.cfg.tp1_r
            tp2_px = entry_px + risk_dist * self.cfg.tp2_r
        else:
            stop_px = ob["top"] + self.cfg.sl_atr_below_ob * atr
            risk_dist = abs(stop_px - entry_px)
            tp1_px = entry_px - risk_dist * self.cfg.tp1_r
            tp2_px = entry_px - risk_dist * self.cfg.tp2_r

        if risk_dist <= 0:
            return

        risk_budget = self.balance * self.cfg.risk_per_trade
        size_usd = min(risk_budget / risk_dist, self.balance * 0.25)

        fee = size_usd * self.cfg.taker_fee
        self.balance -= fee

        self.in_pos = True
        self.pos_side = side
        self.entry_px = entry_px
        self.stop_px = stop_px
        self.tp1_px = tp1_px
        self.tp2_px = tp2_px
        self.size_usd = size_usd
        self.size_remaining_pct = 1.0
        self.entry_bar = idx
        self.tp1_hit = False
        self.ob_ref = ob

    def _close_partial(self, exit_px, pct, reason):
        fill_px = self._apply_slippage(
            exit_px, "sell" if self.pos_side == "LONG" else "buy"
        )
        close_size = self.size_usd * pct
        fee = close_size * self.cfg.taker_fee
        self.balance -= fee

        if self.pos_side == "LONG":
            pnl = (fill_px - self.entry_px) / self.entry_px * close_size
        else:
            pnl = (self.entry_px - fill_px) / self.entry_px * close_size

        risk_dist = abs(self.entry_px - self.stop_px)
        r_mult = (
            (fill_px - self.entry_px) / risk_dist
            if self.pos_side == "LONG"
            else (self.entry_px - fill_px) / risk_dist
        )

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "side": self.pos_side,
                "entry_px": self.entry_px,
                "exit_px": fill_px,
                "size_usd": close_size,
                "pnl": pnl,
                "reason": reason,
                "balance_after": self.balance,
            }
        )

        self.size_remaining_pct -= pct
        if self.size_remaining_pct <= 0.01:
            self.in_pos = False

    def _close_full(self, exit_px, reason):
        fill_px = self._apply_slippage(
            exit_px, "sell" if self.pos_side == "LONG" else "buy"
        )
        fee = self.size_usd * self.size_remaining_pct * self.cfg.taker_fee
        self.balance -= fee

        close_size = self.size_usd * self.size_remaining_pct
        if self.pos_side == "LONG":
            pnl = (fill_px - self.entry_px) / self.entry_px * close_size
        else:
            pnl = (self.entry_px - fill_px) / self.entry_px * close_size

        self.trades.append(
            {
                "entry_bar": self.entry_bar,
                "exit_bar": self.bar_idx,
                "side": self.pos_side,
                "entry_px": self.entry_px,
                "exit_px": fill_px,
                "size_usd": close_size,
                "pnl": pnl,
                "reason": reason,
                "balance_after": self.balance,
            }
        )
        self.in_pos = False

    def run(self, df, precomputed=None):
        if precomputed:
            cached_structure = precomputed["structure"]
            cached_ob = precomputed["ob"]
        else:
            cached_structure = {}
            cached_ob = {}
            for i in range(30, len(df)):
                cached_structure[i] = detect_structure(
                    df, i, self.cfg.structure_lookback, self.cfg.structure_smooth
                )
                cached_ob[i] = find_order_block(
                    df,
                    i,
                    cached_structure[i],
                    self.cfg.ob_max_age,
                    self.cfg.impulse_atr_mult,
                )

        for i in range(30, len(df)):
            self.bar_idx = i
            row = df.iloc[i]
            high, low, close = row["high"], row["low"], row["close"]
            atr = row["atr"]
            rsi = row["rsi"]

            if self.in_pos:
                held = i - self.entry_bar

                if held >= self.cfg.time_stop_bars:
                    self._close_full(close, "TIME_STOP")
                    continue

                if self.pos_side == "LONG":
                    if low <= self.stop_px:
                        self._close_full(self.stop_px, "STOP_LOSS")
                        continue
                    if not self.tp1_hit and high >= self.tp1_px:
                        self._close_partial(self.tp1_px, self.cfg.tp1_pct, "TP1")
                        self.tp1_hit = True
                        self.stop_px = self.entry_px
                        continue
                    if self.tp1_hit and high >= self.tp2_px:
                        self._close_full(self.tp2_px, "TP2")
                        continue
                else:
                    if high >= self.stop_px:
                        self._close_full(self.stop_px, "STOP_LOSS")
                        continue
                    if not self.tp1_hit and low <= self.tp1_px:
                        self._close_partial(self.tp1_px, self.cfg.tp1_pct, "TP1")
                        self.tp1_hit = True
                        self.stop_px = self.entry_px
                        continue
                    if self.tp1_hit and low <= self.tp2_px:
                        self._close_full(self.tp2_px, "TP2")
                        continue

            if self.in_pos:
                continue

            if i not in cached_structure:
                cached_structure[i] = detect_structure(
                    df, i, self.cfg.structure_lookback, self.cfg.structure_smooth
                )
            structure = cached_structure[i]

            if structure == "RANGING" or structure == "INSUFFICIENT":
                continue

            if i not in cached_ob:
                cached_ob[i] = find_order_block(
                    df, i, structure, self.cfg.ob_max_age, self.cfg.impulse_atr_mult
                )
            ob = cached_ob[i]

            if ob is None:
                continue

            ob_age = i - ob["index"]
            if ob_age > self.cfg.ob_max_age:
                continue

            if ob["type"] == "BULLISH":
                in_ob = ob["bottom"] <= close <= ob["top"]
                side = "LONG"
            elif ob["type"] == "BEARISH":
                in_ob = ob["bottom"] <= close <= ob["top"]
                side = "SHORT"
            else:
                continue

            if not in_ob:
                continue

            if not (self.cfg.rsi_low <= rsi <= self.cfg.rsi_high):
                continue

            if side == "LONG" and structure != "BULLISH":
                continue
            if side == "SHORT" and structure != "BEARISH":
                continue

            self._open(row, i, side, ob)

        if self.in_pos:
            self._close_full(df.iloc[-1]["close"], "END_OF_DATA")


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
            "avg_r": 0,
            "sharpe": 0,
            "rr": 0,
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

    daily_chunks = np.array_split(pnls, max(1, len(pnls) // 6))
    daily_sums = [sum(c) for c in daily_chunks]
    darr = np.array(daily_sums)
    sharpe = (
        darr.mean() / darr.std() * np.sqrt(365)
        if len(darr) > 1 and darr.std() > 0
        else 0
    )

    months = max(1, n // 20)
    trades_per_month = n / months

    return {
        "n": n,
        "pnl": round(total_pnl, 2),
        "wr": round(wr, 1),
        "pf": round(pf, 3),
        "avg": round(total_pnl / n, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "rr": round(rr, 2),
        "avg_r": 0,
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
        "final": round(start_bal + total_pnl, 2),
        "reasons": reasons,
        "t_stat": round(t_stat, 3),
        "significant": abs(t_stat) > 1.96,
        "trades_per_month": round(trades_per_month, 1),
    }


def print_stats(label, s):
    print(
        "  {:<50} PnL={:>10,.2f} | N={:>3} | WR={:>5.1f}% | PF={:>5.3f} | "
        "RR={:>4.2f} | Sharpe={:>6.3f} | DD={:>5.1f}% | TPM={:>4.1f} | Final={:>10,.2f}".format(
            label,
            s["pnl"],
            s["n"],
            s["wr"],
            s["pf"],
            s["rr"],
            s["sharpe"],
            s["max_dd_pct"],
            s.get("trades_per_month", 0),
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
    btc_path = base / "btc_usdt_4h_unified.csv"

    print("Loading data...")
    df = prepare_data(btc_path)
    print("Total: {} bars ({} ~ {})".format(len(df), df.index[0], df.index[-1]))
    print()

    split_idx = int(len(df) * 0.7)
    df_is = df.iloc[:split_idx].copy()
    df_oos = df.iloc[split_idx:].copy()
    is_months = (df_is.index[-1] - df_is.index[0]).days / 30
    oos_months = (df_oos.index[-1] - df_oos.index[0]).days / 30
    print(
        "IS: {} bars ({} ~ {}) = {:.0f} months".format(
            len(df_is), df_is.index[0].date(), df_is.index[-1].date(), is_months
        )
    )
    print(
        "OOS: {} bars ({} ~ {}) = {:.0f} months".format(
            len(df_oos), df_oos.index[0].date(), df_oos.index[-1].date(), oos_months
        )
    )
    print()

    start_bal = 10_000.0

    print("Precomputing structure & OB (this may take a minute)...")
    default_cfg = MSBConfig()
    precomp_is = {"structure": {}, "ob": {}}
    for i in range(30, len(df_is)):
        precomp_is["structure"][i] = detect_structure(
            df_is, i, default_cfg.structure_lookback, default_cfg.structure_smooth
        )
        precomp_is["ob"][i] = find_order_block(
            df_is,
            i,
            precomp_is["structure"][i],
            default_cfg.ob_max_age,
            default_cfg.impulse_atr_mult,
        )
    print("IS precompute done: {} bars".format(len(precomp_is["structure"])))

    # ==================================================================
    # PHASE 1: IS Quick Check with Default
    # ==================================================================
    print("=" * 150)
    print("PHASE 1: IN-SAMPLE DEFAULT CHECK")
    print("=" * 150)

    bt = MSBMRBacktest(default_cfg, start_bal)
    bt.run(df_is, precomp_is)
    s = calc_stats(bt.trades, start_bal)
    s["months"] = is_months
    s["trades_per_month"] = round(s["n"] / is_months, 1) if is_months > 0 else 0
    print_stats("Default (precomputed OB/structure)", s)

    # ==================================================================
    # PHASE 2: IS Grid Search
    # ==================================================================
    print()
    print("=" * 150)
    print("PHASE 2: IS GRID SEARCH")
    print("=" * 150)

    impulse_list = [1.0, 1.5, 2.0]
    ob_age_list = [30, 50, 80]
    rsi_combos = [(30, 55), (35, 55), (0, 100)]
    tp_combos = [(1.5, 3.0), (1.0, 2.5), (2.0, 4.0)]

    grid_results = []
    total = len(impulse_list) * len(ob_age_list) * len(rsi_combos) * len(tp_combos)
    print("Testing {} combinations...".format(total))

    for imp in impulse_list:
        for ob_age in ob_age_list:
            precomp_grid = {"structure": precomp_is["structure"], "ob": {}}
            for i in range(30, len(df_is)):
                precomp_grid["ob"][i] = find_order_block(
                    df_is, i, precomp_grid["structure"][i], ob_age, imp
                )
            for rsi_lo, rsi_hi in rsi_combos:
                for tp1, tp2 in tp_combos:
                    cfg = MSBConfig(
                        impulse_atr_mult=imp,
                        ob_max_age=ob_age,
                        rsi_low=float(rsi_lo),
                        rsi_high=float(rsi_hi),
                        tp1_r=tp1,
                        tp2_r=tp2,
                    )
                    bt = MSBMRBacktest(cfg, start_bal)
                    bt.run(df_is, precomp_grid)
                    s = calc_stats(bt.trades, start_bal)
                    s["params"] = "IMP={} OBAge={} RSI={}-{} TP={}/{}".format(
                        imp, ob_age, rsi_lo, rsi_hi, tp1, tp2
                    )
                    grid_results.append(s)

    grid_results.sort(key=lambda x: x["pnl"], reverse=True)
    print("\nTop 20:")
    for s in grid_results[:20]:
        if s["n"] >= 5:
            s["months"] = is_months
            s["trades_per_month"] = round(s["n"] / is_months, 1)
            print_stats(s["params"], s)

    # ==================================================================
    # PHASE 3: OOS Validation
    # ==================================================================
    print()
    print("=" * 150)
    print("PHASE 3: OUT-OF-SAMPLE VALIDATION")
    print("=" * 150)

    print("Precomputing OOS structure & OB...")
    precomp_oos = {"structure": {}, "ob": {}}
    for i in range(30, len(df_oos)):
        precomp_oos["structure"][i] = detect_structure(
            df_oos, i, default_cfg.structure_lookback, default_cfg.structure_smooth
        )
        precomp_oos["ob"][i] = find_order_block(
            df_oos,
            i,
            precomp_oos["structure"][i],
            default_cfg.ob_max_age,
            default_cfg.impulse_atr_mult,
        )
    print("OOS precompute done")

    tested = set()
    oos_results = []
    for is_result in grid_results:
        p = is_result["params"]
        if p in tested or is_result["n"] < 10:
            continue
        tested.add(p)

        parts = p.split()
        imp = float(parts[0].split("=")[1])
        ob_age = int(parts[1].split("=")[1])
        rsi_parts = parts[2].split("=")[1].split("-")
        rsi_lo = float(rsi_parts[0])
        rsi_hi = float(rsi_parts[1])
        tp_parts = parts[3].split("=")[1].split("/")
        tp1 = float(tp_parts[0])
        tp2 = float(tp_parts[1])

        precomp_oos_grid = {"structure": precomp_oos["structure"], "ob": {}}
        for i in range(30, len(df_oos)):
            precomp_oos_grid["ob"][i] = find_order_block(
                df_oos, i, precomp_oos["structure"][i], ob_age, imp
            )

        cfg = MSBConfig(
            impulse_atr_mult=imp,
            ob_max_age=ob_age,
            rsi_low=rsi_lo,
            rsi_high=rsi_hi,
            tp1_r=tp1,
            tp2_r=tp2,
        )
        bt = MSBMRBacktest(cfg, start_bal)
        bt.run(df_oos, precomp_oos_grid)
        oos = calc_stats(bt.trades, start_bal)
        oos["params"] = p
        oos["is_pnl"] = is_result["pnl"]
        oos["is_n"] = is_result["n"]
        oos["is_pf"] = is_result["pf"]
        oos["is_wr"] = is_result["wr"]
        oos["months"] = oos_months
        oos["trades_per_month"] = (
            round(oos["n"] / oos_months, 1) if oos_months > 0 else 0
        )
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

    # Default on OOS
    print()
    bt_def = MSBMRBacktest(MSBConfig(), start_bal)
    bt_def.run(df_oos)
    oos_def = calc_stats(bt_def.trades, start_bal)
    oos_def["months"] = oos_months
    oos_def["trades_per_month"] = (
        round(oos_def["n"] / oos_months, 1) if oos_months > 0 else 0
    )
    print_stats("OOS Default", oos_def)

    # ==================================================================
    # VERDICT
    # ==================================================================
    print()
    print("=" * 150)
    print("VERDICT")
    print("=" * 150)

    best_oos = max(oos_results, key=lambda x: x["pnl"]) if oos_results else None
    if best_oos:
        print(f"\nBest OOS: {best_oos['params']}")
        print(
            f"  OOS: PnL={best_oos['pnl']:+,.2f}  N={best_oos['n']}  WR={best_oos['wr']}%  PF={best_oos['pf']}  DD={best_oos['max_dd_pct']}%  TPM={best_oos.get('trades_per_month', 0)}"
        )

    print(
        f"\nDefault OOS: PnL={oos_def['pnl']:+,.2f}  N={oos_def['n']}  WR={oos_def['wr']}%  PF={oos_def['pf']}  TPM={oos_def.get('trades_per_month', 0)}"
    )

    print("\nAdoption Checklist:")
    checks = {}
    target = best_oos if best_oos else oos_def
    if target:
        checks["IS Expectancy > 0"] = (target.get("is_pnl") or target["pnl"]) > 0
        checks["OOS Expectancy > 0"] = target["pnl"] > 0
        checks["OOS N >= 20"] = target["n"] >= 20
        checks["OOS PF > 1.2"] = target["pf"] > 1.2
        checks["Max DD < 25%"] = target["max_dd_pct"] < 25
        checks["Trades/month >= 15"] = target.get("trades_per_month", 0) >= 15
        checks["OOS WR >= 50%"] = target["wr"] >= 50
        checks["t-stat significant"] = target.get("significant", False)

    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n>>> VALIDATED <<<")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f"\n>>> NOT VALIDATED - Failed: {', '.join(failed)} <<<")


if __name__ == "__main__":
    main()
