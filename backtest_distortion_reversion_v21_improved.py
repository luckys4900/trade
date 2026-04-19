from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    total_return_pct: float
    win_rate_pct: float
    expectancy_pct: float
    max_dd_pct: float
    trades: int
    sharpe: float


def compute_atr(df: pd.DataFrame, length: int) -> pd.Series:
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / max(length, 1), adjust=False).mean()


def compute_adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr = compute_atr(df, length).replace(0, np.nan)
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / length, adjust=False).mean() / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100.0
    return dx.ewm(alpha=1.0 / length, adjust=False).mean()


def compute_vwap_proxy(df: pd.DataFrame, length: int = 3) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(length).sum()
    vv = df["volume"].rolling(length).sum().replace(0, np.nan)
    return pv / vv


class DistortionReversionV21Improved:
    def __init__(self) -> None:
        self.initial_capital: float = 10_000.0
        self.notional: float = 20_000.0
        self.maker_fee: float = 0.00015

    def load_data(self, csv_path: Path) -> pd.DataFrame:
        df = pd.read_csv(csv_path, parse_dates=["timestamp"]).set_index("timestamp")
        df = (
            df.resample("5min")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )
        return df.astype(float)

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr_5"] = compute_atr(out, 5)
        out["atr_1"] = compute_atr(out, 1)
        out["adx"] = compute_adx(out, 14)

        bb_mid = out["close"].rolling(20).mean()
        bb_std = out["close"].rolling(20).std()
        bb_up = bb_mid + 2.0 * bb_std
        bb_lo = bb_mid - 2.0 * bb_std
        out["bbw"] = (bb_up - bb_lo) / bb_mid.replace(0, np.nan)
        out["vwap_15"] = compute_vwap_proxy(out, 3)

        out["ret"] = out["close"].pct_change()
        out["vol_spike"] = out["volume"] / out["volume"].rolling(30).mean().replace(0, np.nan)
        out["proxy_obi"] = (out["close"] - out["open"]) / (out["high"] - out["low"] + 1e-8)
        out["proxy_af"] = out["ret"] * out["volume"].rolling(3).mean()
        out["cvd"] = (out["proxy_af"] * np.sign(out["ret"].fillna(0.0))).cumsum()
        out["cvd_norm"] = out["cvd"] / out["cvd"].rolling(12).std().replace(0, np.nan)

        out["cds"] = (
            0.25 * out["proxy_obi"].clip(-3, 3)
            + 0.30 * np.sign(out["proxy_af"].fillna(0.0))
            + 0.20 * ((out["close"] - out["vwap_15"]) / (out["atr_5"] + 1e-8))
            + 0.15 * out["cvd_norm"].fillna(0.0)
            + 0.10 * np.sign(out["proxy_af"].fillna(0.0)) * out["vol_spike"].clip(upper=3).fillna(0.0)
        )
        return out.dropna()

    @staticmethod
    def get_regime(row: pd.Series) -> str:
        if pd.isna(row["adx"]) or pd.isna(row["bbw"]):
            return "STRONG"
        if row["adx"] < 24 and row["bbw"] < 1.5:
            return "RANGE"
        if row["adx"] < 35:
            return "WEAK"
        return "STRONG"

    def backtest(
        self,
        feat: pd.DataFrame,
        cds_threshold: float = 0.58,
        start_hour: int = 6,
        end_hour: int = 18,
        tp_mult: float = 3.4,
        sl_mult: float = 2.3,
        max_forward_bars: int = 3,
        roundtrip_cost: float | None = None,
    ) -> BacktestResult:
        capital = self.initial_capital
        equity: List[float] = [capital]
        trade_rets: List[float] = []

        fee = (self.maker_fee * 2.0) if roundtrip_cost is None else roundtrip_cost

        i = 20
        while i < len(feat) - (max_forward_bars + 2):
            row = feat.iloc[i]
            ts = row.name
            if not (start_hour <= ts.hour <= end_hour):
                i += 1
                continue
            if self.get_regime(row) == "STRONG":
                i += 1
                continue

            atr = float(row["atr_5"])
            if atr <= 0 or not np.isfinite(atr):
                i += 1
                continue

            entry = float(feat.iloc[i + 1]["open"])
            direction = 0
            if row["cds"] > cds_threshold and entry < row["vwap_15"]:
                direction = 1
            elif row["cds"] < -cds_threshold and entry > row["vwap_15"]:
                direction = -1

            if direction == 0:
                i += 1
                continue

            tp_dist = atr * tp_mult
            sl_dist = atr * sl_mult
            exit_price = None

            for j in range(1, max_forward_bars + 1):
                fut = feat.iloc[i + 1 + j]
                if direction == 1:
                    tp_hit = fut["high"] >= entry + tp_dist
                    sl_hit = fut["low"] <= entry - sl_dist
                    if sl_hit:
                        exit_price = entry - sl_dist
                        break
                    if tp_hit:
                        exit_price = entry + tp_dist
                        break
                else:
                    tp_hit = fut["low"] <= entry - tp_dist
                    sl_hit = fut["high"] >= entry + sl_dist
                    if sl_hit:
                        exit_price = entry + sl_dist
                        break
                    if tp_hit:
                        exit_price = entry - tp_dist
                        break

            if exit_price is None:
                exit_price = float(feat.iloc[i + 1 + max_forward_bars]["close"])

            pnl_pct = direction * ((exit_price - entry) / entry)
            # Use fixed notional PnL to avoid unrealistic compounding artifacts.
            gross_pnl_cash = self.notional * pnl_pct
            cost_cash = self.notional * fee
            net_pnl_cash = gross_pnl_cash - cost_cash
            capital += net_pnl_cash
            if capital <= 0:
                break
            trade_rets.append(net_pnl_cash / max(self.initial_capital, 1e-9))
            equity.append(capital)
            i += max_forward_bars + 1

        if not trade_rets:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0, 0.0)

        ret_arr = np.array(trade_rets, dtype=float)
        eq = np.array(equity, dtype=float)
        dd = (eq / np.maximum.accumulate(eq)) - 1.0

        expectancy = float(ret_arr.mean() * 100.0)
        win_rate = float((ret_arr > 0).mean() * 100.0)
        total_return = float((capital / self.initial_capital - 1.0) * 100.0)
        max_dd = float(dd.min() * 100.0)
        sharpe = float((ret_arr.mean() / ret_arr.std()) * np.sqrt(len(ret_arr))) if ret_arr.std() > 0 else 0.0

        return BacktestResult(
            total_return_pct=total_return,
            win_rate_pct=win_rate,
            expectancy_pct=expectancy,
            max_dd_pct=max_dd,
            trades=len(trade_rets),
            sharpe=sharpe,
        )


def run_deep_study(data_path: Path) -> Tuple[BacktestResult, pd.DataFrame]:
    strat = DistortionReversionV21Improved()
    df = strat.load_data(data_path)
    feat = strat.add_indicators(df)

    base = strat.backtest(feat)
    logger.info("Base total_return=%.2f%% win_rate=%.2f%% expectancy=%.4f%% trades=%d max_dd=%.2f%% sharpe=%.3f",
                base.total_return_pct, base.win_rate_pct, base.expectancy_pct, base.trades, base.max_dd_pct, base.sharpe)

    rows: List[Dict[str, float]] = []
    for th in [0.50, 0.54, 0.58, 0.62, 0.66]:
        for hours in [(4, 20), (6, 18), (8, 16)]:
            for cost in [0.00030, 0.00042, 0.00060]:
                result = strat.backtest(
                    feat,
                    cds_threshold=th,
                    start_hour=hours[0],
                    end_hour=hours[1],
                    roundtrip_cost=cost,
                )
                rows.append(
                    {
                        "threshold": th,
                        "hours": f"{hours[0]}-{hours[1]}",
                        "cost_rt": cost,
                        "return_pct": result.total_return_pct,
                        "win_rate_pct": result.win_rate_pct,
                        "expectancy_pct": result.expectancy_pct,
                        "trades": result.trades,
                        "max_dd_pct": result.max_dd_pct,
                        "sharpe": result.sharpe,
                    }
                )

    study = pd.DataFrame(rows).sort_values(["return_pct", "sharpe"], ascending=False)
    return base, study


def main() -> None:
    path = Path("data/raw/BTC_5m_hyperliquid.csv")
    base, study = run_deep_study(path)
    pd.DataFrame([base.__dict__]).to_csv("v21_improved_base_result.csv", index=False)
    study.to_csv("v21_improved_sensitivity.csv", index=False)
    logger.info("saved: v21_improved_base_result.csv, v21_improved_sensitivity.csv")
    logger.info("best row:\n%s", study.head(1).to_string(index=False))


if __name__ == "__main__":
    main()
