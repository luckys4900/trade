import itertools
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from strategy.cointegration import CointegrationMonitor
from strategy.kalman_hedge import KalmanHedgeRatio
from strategy.spread import SpreadCalculator
from strategy.signals import SignalGenerator
from backtest.engine import BacktestEngine

logger = logging.getLogger(__name__)


class WalkForwardOptimizer:
    def __init__(self, config: Dict):
        self.config = config
        self.signal_cfg = config.get("SIGNAL", {})
        self.wf_cfg = config.get("WALK_FORWARD", {})
        self.risk_cfg = config.get("RISK", {})
        self.coint_cfg = config.get("COINTEGRATION", {})
        self.kalman_cfg = config.get("KALMAN", {})

        self.param_grid = list(
            itertools.product(
                self.signal_cfg.get("z_score_thresholds", [2.0]),
                self.signal_cfg.get("lookback_windows", [120]),
                self.signal_cfg.get("take_profit_z", [0.0]),
                self.signal_cfg.get("stop_loss_z", [4.0]),
            )
        )
        logger.info("Walk-Forward: %d param combos", len(self.param_grid))

    def run(
        self,
        btc_df: pd.DataFrame,
        eth_df: pd.DataFrame,
    ) -> Dict:
        common = btc_df.index.intersection(eth_df.index)
        btc_close = btc_df.loc[common, "close"]
        eth_close = eth_df.loc[common, "close"]

        n = len(common)
        n_splits = self.wf_cfg.get("n_splits", 6)
        is_ratio = self.wf_cfg.get("is_ratio", 0.7)
        min_trades_is = self.wf_cfg.get("min_trades_is", 30)
        min_trades_oos = self.wf_cfg.get("min_trades_oos", 15)

        split_size = n // n_splits
        all_oos_trades = []
        all_oos_equity = []
        split_results = []
        best_params_history = []

        for split_idx in range(2, n_splits):
            is_end = split_idx * split_size
            oos_end = min((split_idx + 1) * split_size, n)

            if oos_end <= is_end:
                continue

            is_btc = btc_close.iloc[:is_end]
            is_eth = eth_close.iloc[:is_end]
            oos_btc = btc_close.iloc[is_end:oos_end]
            oos_eth = eth_close.iloc[is_end:oos_end]

            logger.info(
                "Split %d: IS=%d-%d OOS=%d-%d",
                split_idx,
                0,
                is_end,
                is_end,
                oos_end,
            )

            is_precomp = self._precompute(is_btc, is_eth)
            oos_precomp = self._precompute(oos_btc, oos_eth)

            best_pf = -999
            best_params = None

            for z_entry, lb, z_exit, z_stop in self.param_grid:
                result = self._run_from_precomp(
                    is_precomp,
                    is_btc,
                    is_eth,
                    z_entry,
                    lb,
                    z_exit,
                    z_stop,
                    self.risk_cfg.get("capital", 100000),
                )
                m = result.get("metrics", {})
                if m.get("n_trades", 0) < min_trades_is:
                    continue
                pf = m.get("profit_factor", 0)
                if pf > best_pf:
                    best_pf = pf
                    best_params = (z_entry, lb, z_exit, z_stop)

            if best_params is None:
                logger.info("Split %d: no valid IS params", split_idx)
                continue

            best_params_history.append(
                {
                    "split": split_idx,
                    "z_entry": best_params[0],
                    "lookback": best_params[1],
                    "z_exit": best_params[2],
                    "z_stop": best_params[3],
                    "is_pf": round(best_pf, 3),
                }
            )

            oos_result = self._run_from_precomp(
                oos_precomp,
                oos_btc,
                oos_eth,
                best_params[0],
                best_params[1],
                best_params[2],
                best_params[3],
                self.risk_cfg.get("capital", 100000),
            )
            oos_metrics = oos_result.get("metrics", {})
            oos_trades = oos_result.get("trades", pd.DataFrame())
            oos_eq = oos_result.get("equity_curve", pd.Series())

            split_results.append(
                {
                    "split": split_idx,
                    "params": best_params,
                    "is_pf": round(best_pf, 3),
                    "oos_metrics": oos_metrics,
                    "oos_n": oos_metrics.get("n_trades", 0),
                }
            )

            if not oos_trades.empty:
                all_oos_trades.append(oos_trades)
            if not oos_eq.empty:
                all_oos_equity.append(oos_eq)

            logger.info(
                "Split %d: IS PF=%.3f → OOS PnL=%.2f N=%d WR=%.1f%% PF=%.3f",
                split_idx,
                best_pf,
                oos_metrics.get("total_pnl", 0),
                oos_metrics.get("n_trades", 0),
                oos_metrics.get("win_rate", 0),
                oos_metrics.get("profit_factor", 0),
            )

        combined_trades = (
            pd.concat(all_oos_trades) if all_oos_trades else pd.DataFrame()
        )
        combined_eq = (
            pd.concat(all_oos_equity) if all_oos_equity else pd.Series(dtype=float)
        )

        engine = BacktestEngine(self.config)
        if not combined_trades.empty:
            combined_metrics = engine._calculate_metrics(
                combined_trades, combined_eq, self.risk_cfg.get("capital", 100000)
            )
        else:
            combined_metrics = engine._empty_result()["metrics"]

        stability = self._analyze_param_stability(best_params_history)

        return {
            "oos_combined_metrics": combined_metrics,
            "oos_equity_curve": combined_eq,
            "oos_trades": combined_trades,
            "split_results": split_results,
            "best_params_history": best_params_history,
            "param_stability": stability,
        }

    def _precompute(
        self,
        btc_close: pd.Series,
        eth_close: pd.Series,
    ) -> Dict:
        kf = KalmanHedgeRatio(
            delta=self.kalman_cfg.get("delta", 1e-4),
            obs_noise=self.kalman_cfg.get("observation_noise", 1e-3),
        )
        kalman_df = kf.batch_update(btc_close, eth_close)

        cm = CointegrationMonitor(
            window=self.coint_cfg.get("rolling_window", 120),
            p_threshold_strong=self.coint_cfg.get("p_value_strong", 0.01),
            p_threshold_moderate=self.coint_cfg.get("p_value_moderate", 0.05),
        )
        coint_df = cm.rolling_coint_test(btc_close, eth_close, step=4)

        return {
            "kalman_df": kalman_df,
            "coint_df": coint_df,
            "cm": cm,
        }

    def _run_from_precomp(
        self,
        precomp: Dict,
        btc_close: pd.Series,
        eth_close: pd.Series,
        z_entry: float,
        lookback: int,
        z_exit: float,
        z_stop: float,
        capital: float,
    ) -> Dict:
        try:
            kalman_df = precomp["kalman_df"]
            coint_df = precomp["coint_df"]
            cm = precomp["cm"]

            spread_calc = SpreadCalculator(lookback_window=lookback)
            spread = kalman_df["spread"]
            z_scores = spread_calc.calculate_zscore(spread)

            common = z_scores.index.intersection(
                kalman_df["hedge_ratio"].index
            ).intersection(coint_df.index)

            sig_gen = SignalGenerator(
                z_entry=z_entry,
                z_exit=z_exit,
                z_stop=z_stop,
                lookback_window=lookback,
                max_hold_bars=int(lookback * 0.5),
                size_multiplier_func=cm.get_position_size_multiplier,
            )

            signals = sig_gen.generate_signals(
                spread_z=z_scores.loc[common],
                hedge_ratios=kalman_df["hedge_ratio"].loc[common],
                regimes=coint_df["regime"].loc[common],
                btc_close=btc_close.loc[common],
                eth_close=eth_close.loc[common],
                capital=capital,
                risk_pct=self.risk_cfg.get("risk_per_trade", 0.02),
                max_pos_pct=self.risk_cfg.get("max_position_pct", 0.20),
            )

            engine = BacktestEngine(self.config)
            return engine.run(
                signals,
                fee_rate=self.risk_cfg.get("fee_rate", 0.0005),
                slippage_pct=self.risk_cfg.get("slippage_pct", 0.0002),
                capital=capital,
            )
        except Exception as e:
            logger.warning("Run failed: %s", e)
            return {
                "trades": pd.DataFrame(),
                "equity_curve": pd.Series(dtype=float),
                "metrics": {},
            }

    def _run_single(
        self,
        btc_close: pd.Series,
        eth_close: pd.Series,
        z_entry: float,
        lookback: int,
        z_exit: float,
        z_stop: float,
        capital: float,
    ) -> Dict:
        try:
            kf = KalmanHedgeRatio(
                delta=self.kalman_cfg.get("delta", 1e-4),
                obs_noise=self.kalman_cfg.get("observation_noise", 1e-3),
            )
            kalman_df = kf.batch_update(btc_close, eth_close)

            cm = CointegrationMonitor(
                window=self.coint_cfg.get("rolling_window", 120),
                p_threshold_strong=self.coint_cfg.get("p_value_strong", 0.01),
                p_threshold_moderate=self.coint_cfg.get("p_value_moderate", 0.05),
            )
            coint_df = cm.rolling_coint_test(btc_close, eth_close, step=4)

            spread_calc = SpreadCalculator(lookback_window=lookback)
            spread = kalman_df["spread"]
            z_scores = spread_calc.calculate_zscore(spread)

            common = z_scores.index.intersection(
                kalman_df["hedge_ratio"].index
            ).intersection(coint_df.index)

            sig_gen = SignalGenerator(
                z_entry=z_entry,
                z_exit=z_exit,
                z_stop=z_stop,
                lookback_window=lookback,
                max_hold_bars=int(lookback * 0.5),
                size_multiplier_func=cm.get_position_size_multiplier,
            )

            signals = sig_gen.generate_signals(
                spread_z=z_scores.loc[common],
                hedge_ratios=kalman_df["hedge_ratio"].loc[common],
                regimes=coint_df["regime"].loc[common],
                btc_close=btc_close.loc[common],
                eth_close=eth_close.loc[common],
                capital=capital,
                risk_pct=self.risk_cfg.get("risk_per_trade", 0.02),
                max_pos_pct=self.risk_cfg.get("max_position_pct", 0.20),
            )

            engine = BacktestEngine(self.config)
            return engine.run(
                signals,
                fee_rate=self.risk_cfg.get("fee_rate", 0.0005),
                slippage_pct=self.risk_cfg.get("slippage_pct", 0.0002),
                capital=capital,
            )
        except Exception as e:
            logger.warning("Single run failed: %s", e)
            return {
                "trades": pd.DataFrame(),
                "equity_curve": pd.Series(dtype=float),
                "metrics": {},
            }

    @staticmethod
    def _analyze_param_stability(history: List[Dict]) -> Dict:
        if not history:
            return {"z_entry": {}, "lookback": {}, "stable": False}

        z_entries = [h["z_entry"] for h in history]
        lookbacks = [h["lookback"] for h in history]

        def count_freq(vals):
            freq = {}
            for v in vals:
                freq[v] = freq.get(v, 0) + 1
            return freq

        z_freq = count_freq(z_entries)
        lb_freq = count_freq(lookbacks)

        n_splits = len(history)
        z_mode = max(z_freq, key=z_freq.get)
        lb_mode = max(lb_freq, key=lb_freq.get)

        stable = (z_freq[z_mode] / n_splits >= 0.5) and (
            lb_freq[lb_mode] / n_splits >= 0.5
        )

        return {
            "z_entry_freq": {str(k): v for k, v in z_freq.items()},
            "z_entry_mode": z_mode,
            "lookback_freq": {str(k): v for k, v in lb_freq.items()},
            "lookback_mode": lb_mode,
            "n_splits": n_splits,
            "stable": stable,
        }
