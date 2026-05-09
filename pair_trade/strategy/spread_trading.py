import logging
from typing import Dict, Callable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SpreadTrader:
    """
    Spread-based pairs trading that does NOT rely on cointegration.

    Strategy:
    - Track spread = BTC_price - (hedge_ratio * ETH_price)
    - When spread is high (BTC overpriced): SHORT BTC, LONG ETH
    - When spread is low (BTC underpriced): LONG BTC, SHORT ETH
    - Uses z-score of spread relative to historical mean/std
    - Hedge ratio is adaptive (monthly updated or Kalman)
    """

    def __init__(
        self,
        z_entry_high: float = 2.0,
        z_entry_low: float = -2.0,
        z_exit: float = 0.0,
        z_stop: float = 4.0,
        lookback_window: int = 120,
        max_hold_bars: int = 60,
    ):
        """
        Args:
            z_entry_high: Entry threshold for SHORT (spread too high)
            z_entry_low: Entry threshold for LONG (spread too low)
            z_exit: Exit threshold when spread returns to mean
            z_stop: Stop-loss threshold
            lookback_window: bars for mean/std calculation
            max_hold_bars: max holding period
        """
        self.z_entry_high = z_entry_high
        self.z_entry_low = z_entry_low
        self.z_exit = z_exit
        self.z_stop = z_stop
        self.lookback = lookback_window
        self.max_hold = max_hold_bars

    def compute_spread_zscore(
        self,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
        hedge_ratios: pd.Series,
    ) -> pd.Series:
        """
        Compute spread and its z-score.

        Spread = BTC_price - (hedge_ratio * ETH_price)

        Args:
            btc_prices: BTC price series
            eth_prices: ETH price series
            hedge_ratios: Dynamic hedge ratio series

        Returns:
            Z-score of spread
        """
        common_idx = btc_prices.index.intersection(eth_prices.index).intersection(hedge_ratios.index)

        btc = btc_prices.loc[common_idx]
        eth = eth_prices.loc[common_idx]
        hr = hedge_ratios.loc[common_idx]

        # Compute spread
        spread = btc - (hr * eth)

        # Rolling mean/std
        rolling_mean = spread.rolling(self.lookback, min_periods=self.lookback).mean()
        rolling_std = spread.rolling(self.lookback, min_periods=self.lookback).std()

        # Z-score
        zscore = (spread - rolling_mean) / rolling_std.replace(0, np.nan)
        zscore = zscore.shift(1)  # Avoid look-ahead bias

        return zscore.loc[common_idx]

    def generate_spread_signals(
        self,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
        hedge_ratios: pd.Series,
        capital: float = 100000.0,
        risk_pct: float = 0.02,
        max_pos_pct: float = 0.20,
        size_multiplier_func: Optional[Callable[[float], float]] = None,
    ) -> pd.DataFrame:
        """
        Generate trading signals based on spread z-score.

        Signal logic:
        - z > z_entry_high: SHORT (spread overextended, BTC too expensive)
        - z < z_entry_low: LONG (spread underextended, BTC too cheap)
        - Exit at z_exit (mean reversion)
        - Stop loss at z_stop

        Args:
            btc_prices: BTC price series
            eth_prices: ETH price series
            hedge_ratios: Hedge ratio series
            capital: Trading capital
            risk_pct: Risk per trade as % of capital
            max_pos_pct: Max position as % of capital
            size_multiplier_func: Optional function to adjust position size by regime

        Returns:
            DataFrame of trade signals
        """
        if size_multiplier_func is None:
            size_multiplier_func = lambda x: 1.0

        zscore = self.compute_spread_zscore(btc_prices, eth_prices, hedge_ratios)

        common_idx = zscore.index.intersection(btc_prices.index).intersection(eth_prices.index).intersection(hedge_ratios.index)

        z = zscore.loc[common_idx].values
        btc = btc_prices.loc[common_idx].values
        eth = eth_prices.loc[common_idx].values
        hr = hedge_ratios.loc[common_idx].values
        idx = common_idx

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

            # Position management
            if in_pos:
                held = i - entry_bar

                # Time stop
                if held >= self.max_hold:
                    trades.append(
                        self._close_spread_trade(
                            i, idx, btc, eth, hr, "TIME_STOP",
                            pos_side, entry_btc, entry_eth, entry_hr,
                            eth_size, btc_size
                        )
                    )
                    in_pos = False
                    continue

                # Loss stop
                if pos_side == "LONG" and z[i] < -self.z_stop:
                    trades.append(
                        self._close_spread_trade(
                            i, idx, btc, eth, hr, "STOP_LOSS",
                            pos_side, entry_btc, entry_eth, entry_hr,
                            eth_size, btc_size
                        )
                    )
                    in_pos = False
                    continue

                if pos_side == "SHORT" and z[i] > self.z_stop:
                    trades.append(
                        self._close_spread_trade(
                            i, idx, btc, eth, hr, "STOP_LOSS",
                            pos_side, entry_btc, entry_eth, entry_hr,
                            eth_size, btc_size
                        )
                    )
                    in_pos = False
                    continue

                # Exit on mean reversion
                if pos_side == "LONG" and z[i] >= self.z_exit:
                    trades.append(
                        self._close_spread_trade(
                            i, idx, btc, eth, hr, "TAKE_PROFIT",
                            pos_side, entry_btc, entry_eth, entry_hr,
                            eth_size, btc_size
                        )
                    )
                    in_pos = False
                    continue

                if pos_side == "SHORT" and z[i] <= -self.z_exit:
                    trades.append(
                        self._close_spread_trade(
                            i, idx, btc, eth, hr, "TAKE_PROFIT",
                            pos_side, entry_btc, entry_eth, entry_hr,
                            eth_size, btc_size
                        )
                    )
                    in_pos = False
                    continue

                continue

            # Entry logic
            mult = size_multiplier_func(z[i])
            if mult <= 0:
                continue

            # Spread too high (BTC expensive): SHORT
            if z[i] > self.z_entry_high:
                pos_side = "SHORT"
            # Spread too low (BTC cheap): LONG
            elif z[i] < self.z_entry_low:
                pos_side = "LONG"
            else:
                continue

            # Compute position size based on risk
            risk_budget = capital * risk_pct * mult
            spread_value = abs(btc[i] - hr[i] * eth[i])

            if spread_value <= 0:
                continue

            eth_size = risk_budget / spread_value
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

            trades.append({
                'timestamp': idx[i],
                'action': 'OPEN',
                'side': pos_side,
                'z_score': round(float(z[i]), 4),
                'hedge_ratio': round(float(hr[i]), 6),
                'eth_size': round(eth_size, 6),
                'btc_size': round(btc_size, 6),
                'entry_price_eth': round(float(eth[i]), 2),
                'entry_price_btc': round(float(btc[i]), 2),
                'size_mult': mult,
            })

        df = pd.DataFrame(trades)
        if len(df) > 0:
            logger.info(
                "Spread trading: generated %d signals",
                len(df),
            )
        return df

    @staticmethod
    def _close_spread_trade(
        i, idx, btc, eth, hr, reason, side,
        entry_btc, entry_eth, entry_hr,
        eth_size, btc_size
    ) -> Dict:
        """Close a spread trade."""
        exit_btc = float(btc[i])
        exit_eth = float(eth[i])

        if side == "LONG":
            # LONG: buy ETH, short BTC
            eth_pnl = (exit_eth - entry_eth) * eth_size
            btc_pnl = -(exit_btc - entry_btc) * abs(btc_size)
        else:
            # SHORT: short ETH, buy BTC
            eth_pnl = -(exit_eth - entry_eth) * eth_size
            btc_pnl = (exit_btc - entry_btc) * abs(btc_size)

        gross_pnl = eth_pnl + btc_pnl

        return {
            'timestamp': idx[i],
            'action': 'CLOSE',
            'side': side,
            'reason': reason,
            'exit_price_eth': round(exit_eth, 2),
            'exit_price_btc': round(exit_btc, 2),
            'eth_pnl': round(eth_pnl, 4),
            'btc_pnl': round(btc_pnl, 4),
            'gross_pnl': round(gross_pnl, 4),
            'eth_size': round(eth_size, 6),
            'btc_size': round(btc_size, 6),
        }
