import argparse
import logging
import sys
from datetime import datetime

import numpy as np

from config import (
    BASE_DIR,
    CACHE_DIR,
    COINTEGRATION,
    DATA,
    KALMAN,
    REPORT_DIR,
    RISK,
    SIGNAL,
    WALK_FORWARD,
)
from data.fetcher import DataFetcher
from strategy.cointegration import CointegrationMonitor
from strategy.kalman_hedge import KalmanHedgeRatio
from strategy.spread import SpreadCalculator
from backtest.walk_forward import WalkForwardOptimizer
from backtest.metrics import PerformanceMetrics
from report import visualizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(REPORT_DIR / "run.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Pair Trade Backtest")
    parser.add_argument("--mode", default="backtest", choices=["backtest"])
    args = parser.parse_args()

    config = {
        "DATA": DATA,
        "COINTEGRATION": COINTEGRATION,
        "KALMAN": KALMAN,
        "SIGNAL": SIGNAL,
        "RISK": RISK,
        "WALK_FORWARD": WALK_FORWARD,
    }

    print("=" * 60)
    print("Pair Trade Improved Backtest")
    print("=" * 60)
    print("Data: {} to {}".format(DATA["start_date"], DATA["end_date"]))
    print("Symbols: {}".format(DATA["symbols"]))
    print("Walk-Forward splits: {}".format(WALK_FORWARD["n_splits"]))
    print(
        "Param combos: {}".format(
            len(SIGNAL["z_score_thresholds"])
            * len(SIGNAL["lookback_windows"])
            * len(SIGNAL["take_profit_z"])
            * len(SIGNAL["stop_loss_z"])
        )
    )
    print()

    print("[1/5] Fetching data...")
    fetcher = DataFetcher(DATA["exchange"])
    btc_df = fetcher.fetch_ohlcv(
        DATA["symbols"][0],
        DATA["timeframe"],
        DATA["start_date"],
        DATA["end_date"],
    )
    eth_df = fetcher.fetch_ohlcv(
        DATA["symbols"][1],
        DATA["timeframe"],
        DATA["start_date"],
        DATA["end_date"],
    )
    fetcher.validate_data(btc_df, "BTC")
    fetcher.validate_data(eth_df, "ETH")
    print("  BTC: {} rows | ETH: {} rows".format(len(btc_df), len(eth_df)))

    common = btc_df.index.intersection(eth_df.index)
    btc_close = btc_df.loc[common, "close"]
    eth_close = eth_df.loc[common, "close"]
    print(
        "  Common: {} rows ({:.1f} months)".format(
            len(common),
            (common[-1] - common[0]).days / 30,
        )
    )

    print("\n[2/5] Computing Kalman hedge ratios...")
    kf = KalmanHedgeRatio(
        delta=KALMAN["delta"],
        obs_noise=KALMAN["observation_noise"],
    )
    kalman_df = kf.batch_update(btc_close, eth_close)
    print(
        "  Hedge ratio range: {:.4f} - {:.4f}".format(
            kalman_df["hedge_ratio"].min(),
            kalman_df["hedge_ratio"].max(),
        )
    )

    print("\n[3/5] Running Walk-Forward optimization...")
    wf = WalkForwardOptimizer(config)
    wf_results = wf.run(btc_df.loc[common], eth_df.loc[common])

    print("\n[4/5] Computing Monte Carlo simulation...")
    mc_result = {
        "pf_distribution": [],
        "actual_pf": 0,
        "percentile_rank": 0,
        "is_significant": False,
    }
    if not wf_results["oos_trades"].empty:
        mc_result = PerformanceMetrics.monte_carlo_simulation(
            wf_results["oos_trades"], n_sim=1000
        )

    print("\n[5/5] Generating reports...")
    visualizer.equity_curve_plot(
        wf_results["oos_equity_curve"],
        wf_results,
        btc_close,
        eth_close,
        RISK["capital"],
        str(REPORT_DIR / "01_equity_curve.png"),
    )

    visualizer.trade_analysis_plot(
        wf_results["oos_trades"],
        str(REPORT_DIR / "02_trade_analysis.png"),
    )

    visualizer.walk_forward_summary_plot(
        wf_results,
        mc_result,
        str(REPORT_DIR / "03_walk_forward_summary.png"),
    )

    print_report(config, wf_results, mc_result)


def print_report(config, wf_results, mc_result):
    metrics = wf_results.get("oos_combined_metrics", {})
    splits = wf_results.get("split_results", [])
    stability = wf_results.get("param_stability", {})

    print()
    print("=" * 60)
    print("Pair Trade Improved Backtest Results")
    print("=" * 60)
    print("Period: {} to {}".format(DATA["start_date"], DATA["end_date"]))
    print("Walk-Forward splits: {}".format(WALK_FORWARD["n_splits"]))

    print()
    print("[OOS Combined Performance]")
    print(
        "  Total PnL:      {:>+10,.2f} USDT ({:>+.1f}%)".format(
            metrics.get("total_pnl", 0),
            metrics.get("total_pnl_pct", 0),
        )
    )
    print("  Trades:          {:>10d}".format(metrics.get("n_trades", 0)))
    print("  Win Rate:        {:>10.1f}%".format(metrics.get("win_rate", 0)))
    print("  Profit Factor:   {:>10.3f}".format(metrics.get("profit_factor", 0)))
    print(
        "  Sharpe Ratio:    {:>10.2f} (annualized)".format(
            metrics.get("sharpe_ratio", 0)
        )
    )
    print("  Max Drawdown:    {:>10.2f}%".format(metrics.get("max_dd_pct", 0)))
    print(
        "  Avg Hold:        {:>10.1f} bars ({:.0f}h)".format(
            metrics.get("avg_holding_bars", 0),
            metrics.get("avg_holding_hours", 0),
        )
    )
    print(
        "  t-statistic:     {:>10.3f} (p={:.4f}) {}".format(
            metrics.get("t_statistic", 0),
            metrics.get("p_value", 1),
            "*** SIGNIFICANT" if metrics.get("significant") else "(not significant)",
        )
    )

    print()
    print("[Walk-Forward OOS Results]")
    for sr in splits:
        m = sr.get("oos_metrics", {})
        print(
            "  Split {}: PF={:.3f} N={:>3d} WR={:.1f}% PnL={:+,.2f} Params=z={}/{}/{}/lb={}".format(
                sr["split"],
                m.get("profit_factor", 0),
                m.get("n_trades", 0),
                m.get("win_rate", 0),
                m.get("total_pnl", 0),
                sr["params"][0],
                sr["params"][2],
                sr["params"][3],
                sr["params"][1],
            )
        )

    print()
    print("[Parameter Stability]")
    n_sp = stability.get("n_splits", 0)
    print(
        "  Z-entry mode: {} ({}/{})".format(
            stability.get("z_entry_mode", "N/A"),
            max(stability.get("z_entry_freq", {}).values(), default=0),
            n_sp,
        )
    )
    print(
        "  Lookback mode: {} ({}/{})".format(
            stability.get("lookback_mode", "N/A"),
            max(stability.get("lookback_freq", {}).values(), default=0),
            n_sp,
        )
    )
    print("  Stability: {}".format("STABLE" if stability.get("stable") else "UNSTABLE"))

    print()
    print("[Monte Carlo Test]")
    print("  Actual PF:     {:.3f}".format(mc_result.get("actual_pf", 0)))
    if mc_result.get("pf_distribution"):
        print("  MC median PF:  {:.3f}".format(np.median(mc_result["pf_distribution"])))
    print("  Percentile:    {:.1f}%".format(mc_result.get("percentile_rank", 0)))
    print(
        "  Significant:   {}".format(
            "YES (top 5%)" if mc_result.get("is_significant") else "NO"
        )
    )

    print()
    print("[Adoption Criteria]")
    checks = {
        "OOS PF > 1.30": metrics.get("profit_factor", 0) > 1.30,
        "OOS N > 100": metrics.get("n_trades", 0) > 100,
        "t-test p < 0.05": metrics.get("significant", False),
        "Max DD < 15%": metrics.get("max_dd_pct", 100) < 15,
        "Monte Carlo top 5%": mc_result.get("is_significant", False),
        "Param stability": stability.get("stable", False),
    }
    all_pass = True
    for criterion, passed in checks.items():
        mark = "PASS" if passed else "FAIL"
        print("  [{}] {}".format(mark, criterion))
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print(">>> ADOPTION RECOMMENDED <<<")
    else:
        n_fail = sum(1 for v in checks.values() if not v)
        print(">>> NOT RECOMMENDED ({} criteria failed) <<<".format(n_fail))
    print("=" * 60)


if __name__ == "__main__":
    main()
