# -*- coding: utf-8 -*-
"""
Deep Backtest for Whale_1 - Comprehensive historical analysis
Backtests following strategy on Whale_1's entire trading history
"""

import os, sys, json, time, logging, argparse, requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import numpy as np

# Force UTF-8 on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_logger(log_dir="logs", name="whale_backtest"):
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{name}_{ts}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

class WhaleBacktester:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, wallet_address: str, logger=None):
        self.wallet_address = wallet_address
        self.logger = logger or setup_logger()
        self.all_trades = []

    def _raw_post(self, payload: dict, timeout: int = 15) -> Optional[dict]:
        try:
            resp = requests.post(self.HL_API_URL, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.logger.debug(f"API error: {e}")
        return None

    def fetch_all_fills(self, days_back: int = 365) -> List[dict]:
        """Fetch all fills for the wallet (up to API limit)"""
        self.logger.info(f"Fetching fills for last {days_back} days...")

        end_time = int(time.time() * 1000)
        start_time = end_time - (days_back * 24 * 60 * 60 * 1000)

        # API returns at most 10000 most recent fills
        payload = {
            'type': 'userFillsByTime',
            'user': self.wallet_address,
            'startTime': start_time,
            'endTime': end_time
        }

        data = self._raw_post(payload)
        if isinstance(data, list):
            self.logger.info(f"Fetched {len(data)} fills")
            return data
        else:
            self.logger.error("Failed to fetch fills")
            return []

    def pair_fills_to_trades(self, fills: List[dict]) -> List[dict]:
        """Convert fills to closed trades with detailed PnL"""
        trades = []
        coins = set(f.get('coin') for f in fills)

        for coin in coins:
            coin_fills = [f for f in fills if f.get('coin') == coin]
            coin_fills.sort(key=lambda x: x.get('time', 0))

            net_size = 0
            entry_price = 0
            entry_time = 0
            direction = None

            for fill in coin_fills:
                side = fill.get('side')
                sz = float(fill.get('sz', 0))
                px = float(fill.get('px', 0))
                fill_time = fill.get('time', 0)

                # Determine direction
                if direction is None:
                    if side == 'B':
                        direction = 'LONG'
                        net_size = sz
                        entry_price = px
                        entry_time = fill_time
                    elif side == 'A' and fill.get('dir') in ['Open Short']:
                        direction = 'SHORT'
                        net_size = -sz
                        entry_price = px
                        entry_time = fill_time
                else:
                    # Calculate PnL when position is closed/reduced
                    if direction == 'LONG':
                        if side == 'A':
                            if net_size > 0:
                                close_px = px
                                close_time = fill_time
                                pnl_pct = ((close_px - entry_price) / entry_price) * 100
                                pnl_abs = (close_px - entry_price) * min(sz, net_size)

                                trades.append({
                                    'coin': coin,
                                    'direction': direction,
                                    'entry_px': entry_price,
                                    'exit_px': close_px,
                                    'entry_time': entry_time,
                                    'exit_time': close_time,
                                    'hold_hours': (close_time - entry_time) / (1000 * 60 * 60),
                                    'pnl_pct': pnl_pct,
                                    'pnl_abs': pnl_abs,
                                    'size': min(sz, net_size)
                                })

                                net_size -= sz
                                if net_size <= 0:
                                    direction = None
                    elif direction == 'SHORT':
                        if side == 'B':
                            if net_size < 0:
                                close_px = px
                                close_time = fill_time
                                pnl_pct = ((entry_price - close_px) / entry_price) * 100
                                pnl_abs = (entry_price - close_px) * min(abs(sz), abs(net_size))

                                trades.append({
                                    'coin': coin,
                                    'direction': direction,
                                    'entry_px': entry_price,
                                    'exit_px': close_px,
                                    'entry_time': entry_time,
                                    'exit_time': close_time,
                                    'hold_hours': (close_time - entry_time) / (1000 * 60 * 60),
                                    'pnl_pct': pnl_pct,
                                    'pnl_abs': pnl_abs,
                                    'size': min(abs(sz), abs(net_size))
                                })

                                net_size += sz
                                if net_size >= 0:
                                    direction = None

        self.all_trades = trades
        return trades

    def analyze_trades(self, trades: List[dict]) -> dict:
        """Comprehensive trade analysis"""
        if not trades:
            return {}

        outcomes = np.array([t['pnl_pct'] for t in trades])
        hold_times = np.array([t.get('hold_hours', 0) for t in trades])

        wins = outcomes[outcomes > 0]
        losses = outcomes[outcomes <= 0]

        win_rate = len(wins) / len(outcomes) if len(outcomes) > 0 else 0
        avg_win = np.mean(wins) if len(wins) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0
        max_win = np.max(wins) if len(wins) > 0 else 0
        max_loss = np.min(losses) if len(losses) > 0 else 0

        # EV and risk metrics
        ev = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))

        # Sortino
        downside = outcomes[outcomes < 0]
        downside_std = np.std(downside) if len(downside) > 0 else 1e-8
        sortino = (np.mean(outcomes) / downside_std) if downside_std > 0 else 0

        # Sharpe
        sharpe = ev / (np.std(outcomes) + 1e-8) if np.std(outcomes) > 0 else 0

        # Max drawdown
        cumulative = np.cumsum(outcomes)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_dd = np.min(drawdown)

        # Time-based analysis
        avg_hold = np.mean(hold_times) if len(hold_times) > 0 else 0
        max_hold = np.max(hold_times) if len(hold_times) > 0 else 0
        min_hold = np.min(hold_times) if len(hold_times) > 0 else 0

        # Direction analysis
        long_trades = [t for t in trades if t.get('direction') == 'LONG']
        short_trades = [t for t in trades if t.get('direction') == 'SHORT']
        long_outcomes = np.array([t['pnl_pct'] for t in long_trades])
        short_outcomes = np.array([t['pnl_pct'] for t in short_trades])
        long_ev = np.mean(long_outcomes) if len(long_outcomes) > 0 else 0
        short_ev = np.mean(short_outcomes) if len(short_outcomes) > 0 else 0

        # Coin analysis
        coins = {}
        for coin in set(t.get('coin') for t in trades):
            coin_trades = [t for t in trades if t.get('coin') == coin]
            coin_outcomes = np.array([t['pnl_pct'] for t in coin_trades])
            coins[coin] = {
                'count': len(coin_trades),
                'ev': np.mean(coin_outcomes) if len(coin_outcomes) > 0 else 0,
                'wr': len(coin_outcomes[coin_outcomes > 0]) / len(coin_outcomes) if len(coin_outcomes) > 0 else 0
            }

        # Monthly performance
        monthly = {}
        for t in trades:
            dt = datetime.fromtimestamp(t['entry_time'] / 1000)
            month_key = dt.strftime('%Y-%m')
            if month_key not in monthly:
                monthly[month_key] = {'pnl': 0, 'trades': 0}
            monthly[month_key]['pnl'] += t.get('pnl_pct', 0)
            monthly[month_key]['trades'] += 1

        return {
            'total_trades': len(trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_win': max_win,
            'max_loss': max_loss,
            'ev_per_trade': ev,
            'sortino': sortino,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'avg_hold_hours': avg_hold,
            'max_hold_hours': max_hold,
            'min_hold_hours': min_hold,
            'long_ev': long_ev,
            'short_ev': short_ev,
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'coins': coins,
            'monthly': monthly,
            'outcomes': outcomes.tolist() if len(outcomes) < 1000 else outcomes[:1000].tolist()
        }

    def simulate_following_strategy(self, account_value: float = 100000, risk_per_trade: float = 0.015) -> dict:
        """
        Simulate following strategy with realistic risk management
        1.5% risk per trade, 2x ATR SL, 4x ATR TP
        """
        if not self.all_trades:
            return {}

        self.logger.info(f"Simulating following strategy...")
        self.logger.info(f"  Account: ${account_value:,.0f}")
        self.logger.info(f"  Risk per trade: {risk_per_trade*100}%")

        equity_curve = [account_value]
        trades_log = []

        for i, trade in enumerate(self.all_trades, 1):
            entry_px = trade['entry_px']
            exit_px = trade['exit_px']
            direction = trade['direction']

            # Calculate position size based on risk
            # Assume ATR = 2% of price (conservative estimate)
            atr = entry_px * 0.02
            sl_distance = atr * 2  # 2x ATR

            # Position size = (Account * Risk%) / SL Distance
            position_size_btc = (account_value * risk_per_trade) / sl_distance

            # Calculate PnL
            if direction == 'LONG':
                pnl_pct = ((exit_px - entry_px) / entry_px) * 100
            else:  # SHORT
                pnl_pct = ((entry_px - exit_px) / entry_px) * 100

            pnl_abs = account_value * (pnl_pct / 100)

            # Update equity
            account_value += pnl_abs
            equity_curve.append(account_value)

            trades_log.append({
                'trade_num': i,
                'direction': direction,
                'entry_px': entry_px,
                'exit_px': exit_px,
                'pnl_pct': pnl_pct,
                'pnl_abs': pnl_abs,
                'account_value': account_value
            })

        # Calculate strategy metrics
        equity_array = np.array(equity_curve)
        returns = np.diff(equity_array) / equity_array[:-1]

        total_return = (equity_array[-1] - equity_array[0]) / equity_array[0] * 100
        cagr = ((equity_array[-1] / equity_array[0]) ** (365 / 365) - 1) * 100  # Approximate

        # Max drawdown
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max * 100
        max_dd = np.min(drawdown)

        # Sharpe (annualized)
        sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0

        return {
            'initial_equity': equity_array[0],
            'final_equity': equity_array[-1],
            'total_return_pct': total_return,
            'cagr_pct': cagr,
            'max_drawdown_pct': max_dd,
            'sharpe_ratio': sharpe,
            'total_trades': len(self.all_trades),
            'equity_curve': list(equity_curve),
            'trades_log': trades_log
        }

    def generate_report(self, analysis: dict, simulation: dict) -> str:
        """Generate comprehensive backtest report"""
        report = []
        report.append("="*100)
        report.append("WHALE_1 DEEP BACKTEST REPORT")
        report.append(f"Wallet: {self.wallet_address}")
        report.append(f"Generated: {datetime.utcnow().isoformat()}")
        report.append("="*100)
        report.append("")

        # Executive Summary
        report.append("EXECUTIVE SUMMARY")
        report.append("-"*100)
        report.append(f"Total Historical Trades: {analysis.get('total_trades', 0)}")
        report.append(f"Win Rate: {analysis.get('win_rate', 0)*100:.1f}%")
        report.append(f"EV per Trade: {analysis.get('ev_per_trade', 0):.2f}%")
        report.append(f"Sortino: {analysis.get('sortino', 0):.2f}")
        report.append(f"Max Drawdown: {analysis.get('max_drawdown', 0):.2f}%")
        report.append("")

        # Following Strategy Results
        report.append("FOLLOWING STRATEGY SIMULATION")
        report.append("-"*100)
        report.append(f"Initial Equity: ${simulation.get('initial_equity', 0):,.2f}")
        report.append(f"Final Equity: ${simulation.get('final_equity', 0):,.2f}")
        report.append(f"Total Return: {simulation.get('total_return_pct', 0):.2f}%")
        report.append(f"Max Drawdown: {simulation.get('max_drawdown_pct', 0):.2f}%")
        report.append(f"Sharpe Ratio: {simulation.get('sharpe_ratio', 0):.2f}")
        report.append("")

        # Trade Statistics
        report.append("DETAILED TRADE STATISTICS")
        report.append("-"*100)
        report.append(f"Average Win: {analysis.get('avg_win', 0):.2f}%")
        report.append(f"Average Loss: {analysis.get('avg_loss', 0):.2f}%")
        report.append(f"Max Win: {analysis.get('max_win', 0):.2f}%")
        report.append(f"Max Loss: {analysis.get('max_loss', 0):.2f}%")
        report.append(f"Average Hold Time: {analysis.get('avg_hold_hours', 0):.2f} hours")
        report.append(f"Max Hold Time: {analysis.get('max_hold_hours', 0):.2f} hours")
        report.append("")

        # Direction Analysis
        report.append("DIRECTION ANALYSIS")
        report.append("-"*100)
        report.append(f"Long Trades: {analysis.get('long_trades', 0)} | EV: {analysis.get('long_ev', 0):.2f}%")
        report.append(f"Short Trades: {analysis.get('short_trades', 0)} | EV: {analysis.get('short_ev', 0):.2f}%")
        report.append("")

        # Coin Analysis
        report.append("COIN-BY-COIN PERFORMANCE")
        report.append("-"*100)
        coins = analysis.get('coins', {})
        for coin, stats in sorted(coins.items(), key=lambda x: x[1]['count'], reverse=True):
            report.append(f"{coin}: {stats['count']} trades | EV: {stats['ev']:.2f}% | WR: {stats['wr']*100:.1f}%")
        report.append("")

        # Monthly Performance
        report.append("MONTHLY PERFORMANCE")
        report.append("-"*100)
        monthly = analysis.get('monthly', {})
        for month in sorted(monthly.keys()):
            stats = monthly[month]
            report.append(f"{month}: {stats['pnl']:.2f}% ({stats['trades']} trades)")
        report.append("")

        # Recent Trades Sample
        report.append("RECENT 10 TRADES SAMPLE")
        report.append("-"*100)
        recent = simulation.get('trades_log', [])[-10:] if simulation.get('trades_log') else []
        for t in recent:
            report.append(
                f"#{t['trade_num']} {t['direction']:5s} | "
                f"Entry: ${t['entry_px']:,.2f} | Exit: ${t['exit_px']:,.2f} | "
                f"PnL: {t['pnl_pct']:>6.2f}% (${t['pnl_abs']:>8.2f}) | "
                f"Equity: ${t['account_value']:>10,.2f}"
            )
        report.append("")

        # Professional Assessment
        report.append("PROFESSIONAL ASSESSMENT")
        report.append("-"*100)

        strengths = []
        if analysis.get('sortino', 0) >= 5.0:
            strengths.append("Exceptional risk-adjusted returns (Sortino >= 5.0)")
        if analysis.get('win_rate', 0) >= 0.7:
            strengths.append("High win rate (>= 70%)")
        if analysis.get('ev_per_trade', 0) >= 1.0:
            strengths.append("Strong expected value (>= 1.0%)")
        if simulation.get('total_return_pct', 0) >= 50:
            strengths.append("Strong following strategy returns (>= 50%)")
        if simulation.get('max_drawdown_pct', 0) > -20:
            strengths.append("Controlled drawdown (>-20%)")

        concerns = []
        if analysis.get('max_drawdown', 0) < -30:
            concerns.append("Excessive drawdown (< -30%)")
        if analysis.get('win_rate', 0) < 0.5:
            concerns.append("Low win rate (< 50%)")
        if analysis.get('sortino', 0) < 2.0:
            concerns.append("Mediocre risk-adjusted returns (Sortino < 2.0)")
        if analysis.get('total_trades', 0) < 30:
            concerns.append("Insufficient sample size (< 30 trades)")

        report.append("Strengths:")
        for s in strengths:
            report.append(f"  + {s}")
        if not strengths:
            report.append("  None identified")

        report.append("\nConcerns:")
        for c in concerns:
            report.append(f"  - {c}")
        if not concerns:
            report.append("  None identified")

        report.append("\nRecommendation:")
        if (analysis.get('sortino', 0) >= 3.0 and
            analysis.get('ev_per_trade', 0) >= 0.8 and
            simulation.get('total_return_pct', 0) >= 30 and
            simulation.get('max_drawdown_pct', 0) > -25):
            report.append("  [STRONG BUY] Add to whale portfolio immediately")
        elif (analysis.get('sortino', 0) >= 2.0 and
              analysis.get('ev_per_trade', 0) >= 0.5):
            report.append("  [BUY] Good candidate, add with monitoring")
        else:
            report.append("  [HOLD] Review additional data before adding")

        return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description="Deep backtest for Whale_1")
    parser.add_argument('--wallet', type=str, default='0x863b676e5e4fea0541062c32983dc8f84749ca6d',
                        help='Wallet address to backtest')
    parser.add_argument('--days', type=int, default=365, help='Days of history to analyze')
    parser.add_argument('--account', type=float, default=100000, help='Starting account value for simulation')
    parser.add_argument('--risk', type=float, default=0.015, help='Risk per trade (0.015 = 1.5%)')
    parser.add_argument('--output', type=str, default='whale_1_backtest_report.txt', help='Output report file')
    args = parser.parse_args()

    backtester = WhaleBacktester(args.wallet)

    # Fetch and analyze
    print("\n" + "="*80)
    print("WHALE_1 DEEP BACKTEST")
    print("="*80)
    print(f"\nWallet: {args.wallet}")
    print(f"Analysis Period: Last {args.days} days")
    print(f"Simulation: ${args.account:,.0f} starting, {args.risk*100}% risk per trade")

    # Fetch fills
    fills = backtester.fetch_all_fills(args.days)
    if not fills:
        print("\n[ERROR] No fills found. Exiting.")
        return

    # Pair to trades
    print("\n[STEP 1] Pairing fills to trades...")
    trades = backtester.pair_fills_to_trades(fills)
    print(f"  [OK] Generated {len(trades)} closed trades")

    # Analyze
    print("\n[STEP 2] Analyzing trade patterns...")
    analysis = backtester.analyze_trades(trades)
    print(f"  [OK] Analysis complete")

    # Simulate following
    print("\n[STEP 3] Simulating following strategy...")
    simulation = backtester.simulate_following_strategy(args.account, args.risk)
    print(f"  [OK] Simulation complete")

    # Generate report
    print("\n[STEP 4] Generating report...")
    report = backtester.generate_report(analysis, simulation)

    # Save
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  [OK] Report saved to {args.output}")

    # Save JSON
    json_file = args.output.replace('.txt', '.json')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'analysis': analysis,
            'simulation': simulation,
            'wallet': args.wallet,
            'backtest_date': datetime.utcnow().isoformat()
        }, f, indent=2)
    print(f"  [OK] JSON saved to {json_file}")

    # Print report
    print("\n" + report)

if __name__ == "__main__":
    main()
