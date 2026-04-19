import logging
import pathlib
from typing import Dict, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)

REPORT_DIR = pathlib.Path(__file__).parent


def _ensure_dir(path: str) -> None:
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)


def equity_curve_plot(
    equity_curve: pd.Series,
    wf_results: Dict,
    btc_close: pd.Series,
    eth_close: pd.Series,
    capital: float,
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    fig, ax = plt.subplots(figsize=(14, 6))

    if not equity_curve.empty:
        ax.plot(
            equity_curve.index,
            equity_curve.values,
            linewidth=1.0,
            label="Strategy",
            color="steelblue",
        )

        if not btc_close.empty:
            btc_norm = btc_close / btc_close.iloc[0] * capital
            ax.plot(
                btc_norm.index,
                btc_norm.values,
                linewidth=0.7,
                alpha=0.5,
                label="BTC Buy&Hold",
                color="orange",
            )

        if not eth_close.empty:
            eth_norm = eth_close / eth_close.iloc[0] * capital
            ax.plot(
                eth_norm.index,
                eth_norm.values,
                linewidth=0.7,
                alpha=0.5,
                label="ETH Buy&Hold",
                color="green",
            )

        peak = np.maximum.accumulate(equity_curve.values)
        dd = (peak - equity_curve.values) / peak * 100
        ax2 = ax.twinx()
        ax2.fill_between(equity_curve.index, dd, alpha=0.2, color="red")
        ax2.set_ylabel("Drawdown %", color="red")
        ax2.tick_params(axis="y", labelcolor="red")

    split_results = wf_results.get("split_results", [])
    for sr in split_results:
        if sr.get("oos_metrics", {}).get("n_trades", 0) > 0:
            pass

    ax.set_title("Walk-Forward Equity Curve")
    ax.set_ylabel("Equity (USDT)")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)


def spread_analysis_plot(
    spread: pd.Series,
    z_scores: pd.Series,
    trades_df: pd.DataFrame,
    z_entry: float,
    z_stop: float,
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    valid_spread = spread.dropna()
    if not valid_spread.empty:
        ax1.plot(
            valid_spread.index, valid_spread.values, linewidth=0.5, color="steelblue"
        )
        ax1.set_title("Spread (Kalman)")
        ax1.set_ylabel("Spread")

    valid_z = z_scores.dropna()
    if not valid_z.empty:
        ax2.plot(valid_z.index, valid_z.values, linewidth=0.5, color="steelblue")
        ax2.axhline(z_entry, color="red", linestyle="--", alpha=0.5)
        ax2.axhline(-z_entry, color="green", linestyle="--", alpha=0.5)
        ax2.axhline(z_stop, color="red", linestyle=":", alpha=0.3)
        ax2.axhline(-z_stop, color="green", linestyle=":", alpha=0.3)
        ax2.axhline(0, color="gray", linewidth=0.5)
        ax2.set_title("Z-Score")
        ax2.set_ylabel("Z-Score")

    if not trades_df.empty:
        opens = trades_df[trades_df.get("action") == "OPEN"]
        closes = trades_df[trades_df.get("action") == "CLOSE"]
        if not opens.empty and "z_score" in opens.columns:
            ax2.scatter(
                opens["timestamp"],
                opens["z_score"],
                marker="^",
                c="green",
                s=30,
                zorder=5,
            )

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)


def cointegration_regime_plot(
    coint_df: pd.DataFrame,
    p_strong: float,
    p_moderate: float,
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    if coint_df.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.semilogy(coint_df.index, coint_df["p_value"], linewidth=0.8, color="steelblue")
    ax.axhline(p_strong, color="green", linestyle="--", label=f"p={p_strong}")
    ax.axhline(p_moderate, color="orange", linestyle="--", label=f"p={p_moderate}")

    regimes = coint_df["regime"].values
    colors = {"STRONG": "green", "MODERATE": "yellow", "NONE": "red"}
    for i in range(len(coint_df) - 1):
        ax.axvspan(
            coint_df.index[i],
            coint_df.index[i + 1],
            alpha=0.15,
            color=colors.get(regimes[i], "gray"),
        )

    ax.set_title("Rolling Cointegration Regime")
    ax.set_ylabel("p-value (log)")
    ax.legend()
    ax.set_ylim(1e-4, 1)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)


def kalman_hedge_ratio_plot(
    kalman_df: pd.DataFrame,
    ols_ratio: float,
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    valid = kalman_df.dropna(subset=["hedge_ratio"])
    if valid.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(valid.index, valid["hedge_ratio"], linewidth=0.8, label="Kalman")
    ax.axhline(ols_ratio, color="red", linestyle="--", label=f"OLS={ols_ratio:.4f}")
    ax.fill_between(
        valid.index,
        valid["hedge_ratio"] - 2 * valid["uncertainty"],
        valid["hedge_ratio"] + 2 * valid["uncertainty"],
        alpha=0.2,
        color="steelblue",
    )
    ax.set_title("Kalman Hedge Ratio vs Static OLS")
    ax.set_ylabel("Hedge Ratio")
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)


def trade_analysis_plot(
    trades_df: pd.DataFrame,
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    if trades_df.empty:
        return

    close_trades = trades_df[trades_df.get("action") != "OPEN"]
    if close_trades.empty and "net_pnl" in trades_df.columns:
        close_trades = trades_df

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    if "net_pnl" in close_trades.columns:
        wins = close_trades[close_trades["net_pnl"] > 0]["net_pnl"]
        losses = close_trades[close_trades["net_pnl"] <= 0]["net_pnl"]
        axes[0].hist(wins, bins=20, alpha=0.7, color="green", label="Wins")
        axes[0].hist(losses, bins=20, alpha=0.7, color="red", label="Losses")
        axes[0].set_title("PnL Distribution")
        axes[0].legend()

    if "held_bars" in close_trades.columns:
        axes[1].hist(close_trades["held_bars"], bins=20, color="steelblue", alpha=0.7)
        axes[1].set_title("Holding Period Distribution (bars)")
        axes[1].set_xlabel("Bars")

    if "entry_time" in close_trades.columns and "net_pnl" in close_trades.columns:
        close_trades_copy = close_trades.copy()
        close_trades_copy["month"] = pd.to_datetime(
            close_trades_copy["entry_time"]
        ).dt.to_period("M")
        monthly = close_trades_copy.groupby("month")["net_pnl"].sum()
        colors = ["green" if v > 0 else "red" for v in monthly.values]
        monthly.plot(kind="bar", ax=axes[2], color=colors)
        axes[2].set_title("Monthly PnL")
        axes[2].tick_params(axis="x", rotation=45)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)


def walk_forward_summary_plot(
    wf_results: Dict,
    mc_result: Optional[Dict],
    save_path: str,
) -> None:
    _ensure_dir(save_path)
    splits = wf_results.get("split_results", [])

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    if splits:
        split_labels = [f"Split {s['split']}" for s in splits]
        is_pfs = [s.get("is_pf", 0) for s in splits]
        oos_pfs = [s.get("oos_metrics", {}).get("profit_factor", 0) for s in splits]

        x = np.arange(len(splits))
        width = 0.35
        axes[0].bar(x - width / 2, is_pfs, width, label="IS PF", color="steelblue")
        axes[0].bar(x + width / 2, oos_pfs, width, label="OOS PF", color="orange")
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(split_labels, rotation=45)
        axes[0].set_title("IS vs OOS Profit Factor")
        axes[0].legend()

    if mc_result and mc_result.get("pf_distribution"):
        axes[1].hist(
            mc_result["pf_distribution"], bins=50, alpha=0.7, color="steelblue"
        )
        axes[1].axvline(
            mc_result["actual_pf"],
            color="red",
            linewidth=2,
            label=f"Actual PF={mc_result['actual_pf']:.3f}",
        )
        axes[1].axvline(
            np.percentile(mc_result["pf_distribution"], 95),
            color="orange",
            linestyle="--",
            label="95th pct",
        )
        axes[1].set_title(f"Monte Carlo ({len(mc_result['pf_distribution'])} sims)")
        axes[1].legend()

    param_hist = wf_results.get("best_params_history", [])
    if param_hist:
        from collections import Counter

        z_counts = Counter(h["z_entry"] for h in param_hist)
        axes[2].bar(
            [str(k) for k in z_counts.keys()],
            list(z_counts.values()),
            color="steelblue",
        )
        axes[2].set_title("Z-Entry Selection Frequency")
        axes[2].set_xlabel("Z-Entry")

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    logger.info("Saved: %s", save_path)
