import logging
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SignalGenerator:
    def __init__(
        self,
        z_entry: float = 2.0,
        z_exit: float = 0.0,
        z_stop: float = 4.0,
        lookback_window: int = 120,
        max_hold_bars: int = 60,
        size_multiplier_func: Optional[Callable[[str], float]] = None,
    ):
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.z_stop = z_stop
        self.lookback = lookback_window
        self.max_hold = max_hold_bars
        self.size_mult = size_multiplier_func or (lambda r: 1.0)

    def generate_signals(
        self,
        spread_z: pd.Series,
        hedge_ratios: pd.Series,
        regimes: pd.Series,
        btc_close: pd.Series,
        eth_close: pd.Series,
        capital: float = 100000.0,
        risk_pct: float = 0.02,
        max_pos_pct: float = 0.20,
    ) -> pd.DataFrame:
        common = (
            spread_z.index.intersection(hedge_ratios.index)
            .intersection(regimes.index)
            .intersection(btc_close.index)
            .intersection(eth_close.index)
        )

        z = spread_z.loc[common].values
        hr = hedge_ratios.loc[common].values
        reg = regimes.loc[common].values
        btc = btc_close.loc[common].values
        eth = eth_close.loc[common].values
        idx = common

        trades = []
        in_pos = False
        pos_side = ""
        entry_bar = 0
        entry_z = 0.0
        entry_hr = 0.0
        entry_btc = 0.0
        entry_eth = 0.0
        eth_size = 0.0
        btc_size = 0.0

        for i in range(len(idx)):
            if np.isnan(z[i]) or np.isnan(hr[i]):
                continue

            if in_pos:
                held = i - entry_bar
                if held >= self.max_hold:
                    trades.append(
                        self._close_trade(
                            i,
                            idx,
                            btc,
                            eth,
                            hr,
                            "TIME_STOP",
                            reg[i],
                            pos_side,
                            entry_btc,
                            entry_eth,
                            entry_hr,
                            eth_size,
                            btc_size,
                        )
                    )
                    in_pos = False
                    continue

                if pos_side == "LONG":
                    if z[i] > self.z_stop:
                        trades.append(
                            self._close_trade(
                                i,
                                idx,
                                btc,
                                eth,
                                hr,
                                "STOP_LOSS",
                                reg[i],
                                pos_side,
                                entry_btc,
                                entry_eth,
                                entry_hr,
                                eth_size,
                                btc_size,
                            )
                        )
                        in_pos = False
                        continue
                    if z[i] >= self.z_exit:
                        trades.append(
                            self._close_trade(
                                i,
                                idx,
                                btc,
                                eth,
                                hr,
                                "TAKE_PROFIT",
                                reg[i],
                                pos_side,
                                entry_btc,
                                entry_eth,
                                entry_hr,
                                eth_size,
                                btc_size,
                            )
                        )
                        in_pos = False
                        continue
                elif pos_side == "SHORT":
                    if z[i] < -self.z_stop:
                        trades.append(
                            self._close_trade(
                                i,
                                idx,
                                btc,
                                eth,
                                hr,
                                "STOP_LOSS",
                                reg[i],
                                pos_side,
                                entry_btc,
                                entry_eth,
                                entry_hr,
                                eth_size,
                                btc_size,
                            )
                        )
                        in_pos = False
                        continue
                    if z[i] <= -self.z_exit:
                        trades.append(
                            self._close_trade(
                                i,
                                idx,
                                btc,
                                eth,
                                hr,
                                "TAKE_PROFIT",
                                reg[i],
                                pos_side,
                                entry_btc,
                                entry_eth,
                                entry_hr,
                                eth_size,
                                btc_size,
                            )
                        )
                        in_pos = False
                        continue

            if in_pos:
                continue

            mult = self.size_mult(reg[i])
            if mult <= 0:
                continue

            if z[i] < -self.z_entry:
                pos_side = "LONG"
            elif z[i] > self.z_entry:
                pos_side = "SHORT"
            else:
                continue

            sl_dist = abs(z[i]) - self.z_stop
            if sl_dist <= 0:
                continue

            risk_budget = capital * risk_pct * mult
            price_spread = abs(eth[i] - hr[i] * btc[i])
            if price_spread <= 0:
                continue

            eth_size = risk_budget / price_spread
            max_notional = capital * max_pos_pct
            notional = eth_size * eth[i] + eth_size * abs(hr[i]) * btc[i]
            if notional > max_notional:
                eth_size *= max_notional / notional
            eth_size = max(0.001, eth_size)
            btc_size = eth_size * hr[i]

            in_pos = True
            entry_bar = i
            entry_z = z[i]
            entry_hr = hr[i]
            entry_btc = btc[i]
            entry_eth = eth[i]

            trades.append(
                {
                    "timestamp": idx[i],
                    "action": "OPEN",
                    "side": pos_side,
                    "z_score": round(float(z[i]), 4),
                    "hedge_ratio": round(float(hr[i]), 6),
                    "regime": reg[i],
                    "eth_size": round(eth_size, 6),
                    "btc_size": round(btc_size, 6),
                    "entry_price_eth": round(float(eth[i]), 2),
                    "entry_price_btc": round(float(btc[i]), 2),
                    "size_mult": mult,
                }
            )

        df = pd.DataFrame(trades)
        if len(df) > 0:
            logger.info(
                "Generated %d signals (actions: %s)",
                len(df),
                df["action"].value_counts().to_dict(),
            )
        return df

    @staticmethod
    def _close_trade(
        i,
        idx,
        btc,
        eth,
        hr,
        reason,
        regime,
        side,
        entry_btc,
        entry_eth,
        entry_hr,
        eth_size,
        btc_size,
    ) -> Dict:
        exit_btc = float(btc[i])
        exit_eth = float(eth[i])
        exit_hr = float(hr[i])

        if side == "LONG":
            eth_pnl = (exit_eth - entry_eth) * eth_size
            btc_pnl = -(exit_btc - entry_btc) * abs(btc_size)
        else:
            eth_pnl = -(exit_eth - entry_eth) * eth_size
            btc_pnl = (exit_btc - entry_btc) * abs(btc_size)

        gross_pnl = eth_pnl + btc_pnl

        return {
            "timestamp": idx[i],
            "action": "CLOSE",
            "side": side,
            "reason": reason,
            "regime": regime,
            "exit_price_eth": round(exit_eth, 2),
            "exit_price_btc": round(exit_btc, 2),
            "eth_pnl": round(eth_pnl, 4),
            "btc_pnl": round(btc_pnl, 4),
            "gross_pnl": round(gross_pnl, 4),
            "eth_size": round(eth_size, 6),
            "btc_size": round(btc_size, 6),
        }

    @staticmethod
    def validate_signals(signals_df: pd.DataFrame) -> Dict:
        if signals_df.empty:
            return {"valid": False, "error": "No signals"}

        opens = signals_df[signals_df["action"] == "OPEN"]
        closes = signals_df[signals_df["action"] == "CLOSE"]

        n_trades = min(len(opens), len(closes))
        longs = opens[opens["side"] == "LONG"]
        shorts = opens[opens["side"] == "SHORT"]

        return {
            "valid": True,
            "n_trades": n_trades,
            "n_long": len(longs),
            "n_short": len(shorts),
            "long_short_ratio": round(len(longs) / max(len(shorts), 1), 2),
        }
