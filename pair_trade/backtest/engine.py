import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, config: Dict):
        self.config = config
        self.risk_cfg = config.get("RISK", {})

    def run(
        self,
        signals_df: pd.DataFrame,
        fee_rate: float = 0.0005,
        slippage_pct: float = 0.0002,
        capital: float = 100000.0,
    ) -> Dict:
        if signals_df.empty:
            return self._empty_result()

        trades = []
        equity = capital
        equity_curve = []

        open_sig = None
        for _, row in signals_df.iterrows():
            if row["action"] == "OPEN":
                open_sig = row
            elif row["action"] == "CLOSE" and open_sig is not None:
                trade = self._calc_trade_pnl(open_sig, row, fee_rate, slippage_pct)
                equity += trade["net_pnl"]
                trade["equity_after"] = round(equity, 2)
                trades.append(trade)
                equity_curve.append({"timestamp": row["timestamp"], "equity": equity})
                open_sig = None

        if not trades:
            return self._empty_result()

        trades_df = pd.DataFrame(trades)
        eq_series = pd.Series(
            [e["equity"] for e in equity_curve],
            index=[e["timestamp"] for e in equity_curve],
        )
        eq_series.name = "equity"

        metrics = self._calculate_metrics(trades_df, eq_series, capital)

        return {
            "trades": trades_df,
            "equity_curve": eq_series,
            "metrics": metrics,
        }

    def _calc_trade_pnl(
        self,
        open_row: pd.Series,
        close_row: pd.Series,
        fee_rate: float,
        slippage_pct: float,
    ) -> Dict:
        gross_pnl = float(close_row.get("gross_pnl", 0))

        eth_size = float(open_row["eth_size"])
        btc_size = float(open_row["btc_size"])
        entry_eth = float(open_row["entry_price_eth"])
        entry_btc = float(open_row["entry_price_btc"])
        exit_eth = float(close_row["exit_price_eth"])
        exit_btc = float(close_row["exit_price_btc"])

        notional_open = eth_size * entry_eth + abs(btc_size) * entry_btc
        notional_close = eth_size * exit_eth + abs(btc_size) * exit_btc
        total_notional = notional_open + notional_close

        total_fee = total_notional * fee_rate
        total_slip = total_notional * slippage_pct
        net_pnl = gross_pnl - total_fee - total_slip

        held_bars = 0
        try:
            ts_open = open_row["timestamp"]
            ts_close = close_row["timestamp"]
            if isinstance(ts_open, pd.Timestamp) and isinstance(ts_close, pd.Timestamp):
                held_bars = int((ts_close - ts_open).total_seconds() / (4 * 3600))
        except Exception:
            pass

        return {
            "entry_time": open_row["timestamp"],
            "exit_time": close_row["timestamp"],
            "side": open_row["side"],
            "reason": close_row["reason"],
            "regime": open_row.get("regime", "UNKNOWN"),
            "hedge_ratio": open_row.get("hedge_ratio", 0),
            "eth_size": eth_size,
            "btc_size": btc_size,
            "entry_price_eth": entry_eth,
            "entry_price_btc": entry_btc,
            "exit_price_eth": exit_eth,
            "exit_price_btc": exit_btc,
            "gross_pnl": round(gross_pnl, 4),
            "total_fee": round(total_fee, 4),
            "total_slip": round(total_slip, 4),
            "net_pnl": round(net_pnl, 4),
            "held_bars": max(held_bars, 0),
        }

    @staticmethod
    def _calculate_metrics(
        trades_df: pd.DataFrame,
        equity_curve: pd.Series,
        capital: float,
    ) -> Dict:
        pnls = trades_df["net_pnl"].values
        n = len(pnls)
        total_pnl = float(np.sum(pnls))
        wins = pnls[pnls > 0]
        losses = np.abs(pnls[pnls < 0])
        n_wins = len(wins)
        n_losses = len(losses)
        wr = n_wins / n * 100 if n > 0 else 0
        pf = (
            float(np.sum(wins) / np.sum(losses))
            if len(losses) > 0 and np.sum(losses) > 0
            else 0.0
        )

        avg_win = float(np.mean(wins)) if n_wins > 0 else 0
        avg_loss = float(np.mean(losses)) if n_losses > 0 else 0
        avg_wl = avg_win / avg_loss if avg_loss > 0 else 0

        eq = equity_curve.values
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / peak * 100
        max_dd_pct = float(np.max(dd)) if len(dd) > 0 else 0

        eq_diff = np.diff(eq)
        if len(eq_diff) > 1 and np.std(eq_diff) > 0:
            periods_per_year = 2190
            sharpe = float(
                np.mean(eq_diff) / np.std(eq_diff) * np.sqrt(periods_per_year)
            )
        else:
            sharpe = 0.0

        neg = eq_diff[eq_diff < 0]
        if len(neg) > 0 and np.std(neg) > 0:
            sortino = float(np.mean(eq_diff) / np.std(neg) * np.sqrt(periods_per_year))
        else:
            sortino = 0.0

        if len(pnls) > 1 and np.std(pnls) > 0:
            t_stat = float(np.mean(pnls) / (np.std(pnls) / np.sqrt(n)))
        else:
            t_stat = 0.0

        from scipy import stats as sp_stats

        p_value = float(sp_stats.ttest_1samp(pnls, 0)[1]) if n > 1 else 1.0

        avg_hold = (
            float(np.mean(trades_df["held_bars"].values))
            if "held_bars" in trades_df.columns
            else 0
        )

        return {
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / capital * 100, 2),
            "n_trades": n,
            "n_long": int((trades_df["side"] == "LONG").sum()),
            "n_short": int((trades_df["side"] == "SHORT").sum()),
            "win_rate": round(wr, 1),
            "profit_factor": round(pf, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_win_loss_ratio": round(avg_wl, 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "avg_holding_bars": round(avg_hold, 1),
            "avg_holding_hours": round(avg_hold * 4, 1),
            "t_statistic": round(t_stat, 3),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
            "final_equity": round(float(eq[-1]), 2) if len(eq) > 0 else capital,
        }

    @staticmethod
    def _empty_result() -> Dict:
        return {
            "trades": pd.DataFrame(),
            "equity_curve": pd.Series(dtype=float),
            "metrics": {
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "n_trades": 0,
                "n_long": 0,
                "n_short": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "avg_win_loss_ratio": 0,
                "max_dd_pct": 0,
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "avg_holding_bars": 0,
                "avg_holding_hours": 0,
                "t_statistic": 0,
                "p_value": 1.0,
                "significant": False,
                "final_equity": 0,
            },
        }
