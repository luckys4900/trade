from typing import List, Optional
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    side: str = 'long'

@dataclass
class BacktestResult:
    pair_name: str
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    sharpe_ratio: float
    max_drawdown: float
    equity_curve: List[float] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)

class BacktestEngine:
    def __init__(self, z_score_threshold=2.0, position_size=0.02,
                 entry_threshold=2.0, exit_threshold=0.5):
        self.z_score_threshold = z_score_threshold
        self.position_size = position_size
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def _calculate_z_score(self, price1, price2, window=20):
        p1_norm = (price1 - price1.mean()) / price1.std()
        p2_norm = (price2 - price2.mean()) / price2.std()
        spread = p1_norm - p2_norm
        z_score = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()
        return z_score

    def run(self, df1, df2, pair_name, initial_capital=100000, lookback_window=20):
        price1 = df1['close']
        price2 = df2['close']
        z_score = self._calculate_z_score(price1, price2, lookback_window)

        trades = []
        equity_values = [initial_capital]
        capital = initial_capital
        position_open = False
        entry_price = 0
        entry_time = None

        for i in range(lookback_window + 1, len(z_score)):
            current_z = z_score.iloc[i]
            current_time = z_score.index[i]

            if not position_open and abs(current_z) > self.entry_threshold:
                position_open = True
                entry_price = current_z
                entry_time = current_time
                capital *= (1 - self.position_size)

            elif position_open:
                if abs(current_z) < self.exit_threshold or i == len(z_score) - 1:
                    exit_price = current_z
                    exit_time = current_time
                    pnl_pct = -(exit_price - entry_price) / max(abs(entry_price), 0.001)
                    pnl = capital * self.position_size * pnl_pct

                    trade = Trade(entry_time=entry_time, entry_price=entry_price,
                                  exit_time=exit_time, exit_price=exit_price,
                                  pnl=pnl, pnl_pct=pnl_pct)
                    trades.append(trade)
                    capital += pnl
                    equity_values.append(capital)
                    position_open = False
            else:
                equity_values.append(capital)

        while len(equity_values) < len(z_score):
            equity_values.append(equity_values[-1])

        total_pnl = capital - initial_capital
        total_return_pct = (capital - initial_capital) / initial_capital * 100

        if len(trades) == 0:
            return BacktestResult(
                pair_name=pair_name, initial_capital=initial_capital,
                final_capital=capital, total_pnl=total_pnl,
                total_return_pct=total_return_pct, total_trades=0,
                winning_trades=0, losing_trades=0, win_rate=0.0,
                avg_win=0.0, avg_loss=0.0, sharpe_ratio=0.0,
                max_drawdown=0.0, equity_curve=equity_values, trades=trades)

        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        win_rate = len(winning) / len(trades)
        avg_win = np.mean([t.pnl for t in winning]) if winning else 0
        avg_loss = np.mean([t.pnl for t in losing]) if losing else 0

        returns = np.diff(equity_values) / np.array(equity_values[:-1])
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0

        equity_array = np.array(equity_values)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max
        max_drawdown = np.min(drawdown)

        return BacktestResult(
            pair_name=pair_name, initial_capital=initial_capital,
            final_capital=capital, total_pnl=total_pnl,
            total_return_pct=total_return_pct, total_trades=len(trades),
            winning_trades=len(winning), losing_trades=len(losing),
            win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
            sharpe_ratio=float(sharpe), max_drawdown=float(max_drawdown),
            equity_curve=equity_values, trades=trades)

    def walk_forward(self, df1, df2, pair_name, train_window=200,
                     test_window=100, step=50, initial_capital=100000):
        all_trades = []
        equity_curve = [initial_capital]
        capital = initial_capital

        for start_idx in range(0, len(df1) - train_window - test_window, step):
            train_end = start_idx + train_window
            test_end = train_end + test_window
            test_df1 = df1.iloc[train_end:test_end]
            test_df2 = df2.iloc[train_end:test_end]
            result = self.run(test_df1, test_df2, pair_name, capital)
            all_trades.extend(result.trades)
            capital = result.final_capital
            equity_curve.append(capital)

        total_pnl = capital - initial_capital
        total_return_pct = total_pnl / initial_capital * 100

        if len(all_trades) == 0:
            return BacktestResult(
                pair_name=pair_name, initial_capital=initial_capital,
                final_capital=capital, total_pnl=total_pnl,
                total_return_pct=total_return_pct, total_trades=0,
                winning_trades=0, losing_trades=0, win_rate=0.0,
                avg_win=0.0, avg_loss=0.0, sharpe_ratio=0.0,
                max_drawdown=0.0, equity_curve=equity_curve, trades=all_trades)

        winning = [t for t in all_trades if t.pnl > 0]
        losing = [t for t in all_trades if t.pnl <= 0]
        win_rate = len(winning) / len(all_trades)
        avg_win = np.mean([t.pnl for t in winning]) if winning else 0
        avg_loss = np.mean([t.pnl for t in losing]) if losing else 0

        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0

        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

        return BacktestResult(
            pair_name=pair_name, initial_capital=initial_capital,
            final_capital=capital, total_pnl=total_pnl,
            total_return_pct=total_return_pct, total_trades=len(all_trades),
            winning_trades=len(winning), losing_trades=len(losing),
            win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
            sharpe_ratio=float(sharpe), max_drawdown=float(max_drawdown),
            equity_curve=equity_curve, trades=all_trades)
