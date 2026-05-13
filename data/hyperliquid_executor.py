"""
Hyperliquid Live Trading Executor - Clarity Act v3.0
Executes trading orders on Hyperliquid via CCXT
Author: Claude Code
Date: 2026-05-14
"""

import ccxt
import logging
import time
from datetime import datetime
from typing import Dict, Tuple, Optional, List
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HyperliquidExecutor:
    """
    Executes market orders on Hyperliquid via CCXT
    Handles position sizing using Kelly Criterion
    """

    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        paper_trade: bool = False,
        kelly_fraction: float = 0.55
    ):
        """
        Initialize Hyperliquid executor

        Args:
            api_key: Hyperliquid API key
            api_secret: Hyperliquid API secret
            paper_trade: If True, simulate orders without executing
            kelly_fraction: Kelly Criterion fraction for position sizing (0-1)
        """
        self.paper_trade = paper_trade
        self.kelly_fraction = kelly_fraction
        self.exchange = None
        self.account_balance = 0
        self.open_positions = {}
        self.trade_history = []
        self.last_order_id = 0

        if not paper_trade:
            self._initialize_exchange(api_key, api_secret)
        else:
            logger.info("Paper trading mode enabled - no real orders will be executed")

    def _initialize_exchange(self, api_key: str, api_secret: str):
        """Initialize CCXT Hyperliquid connection"""
        try:
            self.exchange = ccxt.hyperliquid({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'margin': True
                }
            })

            # Test connection
            self.exchange.load_markets()
            logger.info("Hyperliquid exchange initialized successfully")

            # Load account balance
            self._update_account_balance()

        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid exchange: {e}")
            raise

    def _update_account_balance(self):
        """Fetch current account balance from exchange"""
        try:
            if self.exchange:
                balance = self.exchange.fetch_balance()
                self.account_balance = balance.get('USDC', {}).get('free', 0)
                logger.info(f"Account balance updated: ${self.account_balance:,.2f}")
        except Exception as e:
            logger.error(f"Failed to update account balance: {e}")

    def calculate_position_size(
        self,
        account_balance: float,
        expected_return: float,
        win_rate: float,
        stop_loss_percent: float = -2.5
    ) -> float:
        """
        Calculate optimal position size using Kelly Criterion

        Kelly = (bp + p - q) / b
        Where:
        - p = win probability
        - q = loss probability (1-p)
        - b = loss/win ratio

        Apply Kelly fraction for risk management

        Args:
            account_balance: Total account balance
            expected_return: Expected return per trade (%)
            win_rate: Historical win rate (0-1)
            stop_loss_percent: Stop loss level (%)

        Returns:
            Position size in USD
        """
        try:
            if win_rate <= 0 or win_rate >= 1:
                # Invalid win rate, use conservative sizing
                return account_balance * 0.05 * self.kelly_fraction

            p = win_rate
            q = 1 - p

            # Calculate b (loss/win ratio)
            if expected_return == 0:
                return account_balance * 0.05 * self.kelly_fraction

            win_amount = abs(expected_return)
            loss_amount = abs(stop_loss_percent)
            b = loss_amount / win_amount if win_amount > 0 else 1

            # Kelly calculation
            kelly_pct = (b * p + p - q) / b

            # Apply Kelly fraction
            fractional_kelly = kelly_pct * self.kelly_fraction

            # Ensure positive and bounded
            fractional_kelly = max(0.01, min(fractional_kelly, 0.25))  # 1-25% max

            position_size = account_balance * fractional_kelly

            logger.info(
                f"Position size calculated: ${position_size:,.2f} "
                f"(Kelly: {kelly_pct:.2%}, Fractional: {fractional_kelly:.2%})"
            )

            return position_size

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return account_balance * 0.05 * self.kelly_fraction

    def execute_market_order(
        self,
        symbol: str,
        side: str,
        position_size_usd: float,
        current_price: float = None
    ) -> Dict:
        """
        Execute market order (buy or sell)

        Args:
            symbol: Trading pair (e.g., 'BTC/USDC')
            side: 'buy' or 'sell'
            position_size_usd: Position size in USD
            current_price: Current market price (for paper trading)

        Returns:
            Order result dictionary
        """
        try:
            if side not in ['buy', 'sell']:
                raise ValueError(f"Invalid side: {side}")

            # Calculate quantity based on position size
            if current_price is None and not self.paper_trade:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
            elif current_price is None:
                raise ValueError("current_price required for paper trading")

            quantity = position_size_usd / current_price

            # Round to exchange precision
            if not self.paper_trade:
                market = self.exchange.market(symbol)
                quantity = self.exchange.amount_to_precision(symbol, quantity)

            if self.paper_trade:
                # Paper trading: simulate order
                order_id = self._generate_paper_order_id()
                order = {
                    'id': order_id,
                    'symbol': symbol,
                    'type': 'market',
                    'side': side,
                    'amount': quantity,
                    'price': current_price,
                    'cost': quantity * current_price,
                    'status': 'closed',
                    'timestamp': datetime.now().isoformat(),
                    'paper_trade': True
                }
                logger.info(f"Paper order executed: {side.upper()} {quantity:.4f} {symbol} @ ${current_price:.2f}")
            else:
                # Live trading: execute on exchange
                order = self.exchange.create_market_order(
                    symbol, side, quantity
                )
                logger.info(f"Live order executed: {order}")

            self.trade_history.append(order)
            self.open_positions[symbol] = {
                'side': side,
                'quantity': quantity,
                'entry_price': current_price,
                'entry_time': datetime.now().isoformat(),
                'position_size_usd': position_size_usd
            }

            return {
                'success': True,
                'order': order,
                'quantity': quantity,
                'price': current_price,
                'cost': quantity * current_price
            }

        except Exception as e:
            logger.error(f"Failed to execute market order: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def close_position(
        self,
        symbol: str,
        current_price: float = None
    ) -> Dict:
        """
        Close an open position

        Args:
            symbol: Trading pair
            current_price: Current market price

        Returns:
            Exit result dictionary
        """
        try:
            if symbol not in self.open_positions:
                return {
                    'success': False,
                    'error': f"No open position for {symbol}"
                }

            position = self.open_positions[symbol]
            side = 'sell' if position['side'] == 'buy' else 'buy'

            # Execute closing order
            result = self.execute_market_order(
                symbol, side, position['position_size_usd'], current_price
            )

            if result['success']:
                # Calculate P&L
                quantity = position['quantity']
                entry_price = position['entry_price']
                exit_price = current_price

                if position['side'] == 'buy':
                    pnl = (exit_price - entry_price) * quantity
                else:
                    pnl = (entry_price - exit_price) * quantity

                pnl_percent = (pnl / position['position_size_usd']) * 100

                result['pnl'] = pnl
                result['pnl_percent'] = pnl_percent
                result['duration'] = (datetime.now() -
                                     datetime.fromisoformat(position['entry_time'])).total_seconds() / 3600

                # Remove from open positions
                del self.open_positions[symbol]

                logger.info(
                    f"Position closed for {symbol}: P&L ${pnl:,.2f} ({pnl_percent:.2f}%)"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def apply_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        trailing_stop_percent: float = 0.75
    ) -> Optional[Dict]:
        """
        Apply trailing stop to open position

        Args:
            symbol: Trading pair
            current_price: Current market price
            trailing_stop_percent: Trailing stop percentage (%)

        Returns:
            Close result if stop hit, None otherwise
        """
        try:
            if symbol not in self.open_positions:
                return None

            position = self.open_positions[symbol]
            entry_price = position['entry_price']

            if position['side'] == 'buy':
                stop_price = entry_price * (1 - trailing_stop_percent / 100)

                if current_price <= stop_price:
                    logger.info(
                        f"Trailing stop triggered for {symbol}: "
                        f"{current_price:.2f} <= {stop_price:.2f}"
                    )
                    return self.close_position(symbol, current_price)
            else:
                stop_price = entry_price * (1 + trailing_stop_percent / 100)

                if current_price >= stop_price:
                    logger.info(
                        f"Trailing stop triggered for {symbol}: "
                        f"{current_price:.2f} >= {stop_price:.2f}"
                    )
                    return self.close_position(symbol, current_price)

            return None

        except Exception as e:
            logger.error(f"Error applying trailing stop: {e}")
            return None

    def get_position_status(self, symbol: str) -> Dict:
        """Get status of open position"""
        if symbol in self.open_positions:
            return self.open_positions[symbol]
        return None

    def get_all_positions(self) -> Dict:
        """Get all open positions"""
        return self.open_positions.copy()

    def get_trade_history(self, limit: int = None) -> List[Dict]:
        """Get trade history"""
        if limit:
            return self.trade_history[-limit:]
        return self.trade_history.copy()

    def fetch_current_balance(self) -> float:
        """Fetch current account balance"""
        if self.paper_trade:
            return self.account_balance
        else:
            self._update_account_balance()
            return self.account_balance

    def validate_trading_pair(self, symbol: str) -> bool:
        """Validate if trading pair exists on exchange"""
        try:
            if self.paper_trade:
                return True  # Assume valid in paper trade mode

            markets = self.exchange.symbols
            return symbol in markets
        except Exception as e:
            logger.error(f"Error validating trading pair: {e}")
            return False

    def _generate_paper_order_id(self) -> int:
        """Generate unique paper order ID"""
        self.last_order_id += 1
        return self.last_order_id

    def save_trade_history(self, filepath: str):
        """Save trade history to JSON file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.trade_history, f, indent=2, default=str)
            logger.info(f"Trade history saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save trade history: {e}")

    def load_trade_history(self, filepath: str):
        """Load trade history from JSON file"""
        try:
            with open(filepath, 'r') as f:
                self.trade_history = json.load(f)
            logger.info(f"Trade history loaded from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load trade history: {e}")

    def run_live_trading_session(
        self,
        signal_generator,
        price_feed,
        duration_minutes: int = 60,
        check_interval_seconds: int = 60
    ) -> Dict:
        """
        Main trading loop for live execution

        Args:
            signal_generator: SignalGenerator instance
            price_feed: Function that returns (btc_price, eth_price, btc_ma)
            duration_minutes: Session duration
            check_interval_seconds: Check interval

        Returns:
            Session summary
        """
        logger.info("Starting live trading session...")
        start_time = datetime.now()
        session_trades = []
        session_pnl = 0

        try:
            while True:
                elapsed = (datetime.now() - start_time).total_seconds() / 60

                if elapsed >= duration_minutes:
                    logger.info("Trading session duration reached")
                    break

                # Get current prices
                btc_price, eth_price, btc_ma = price_feed()

                # Check for entry signal
                entry_signal, entry_reason = signal_generator.entry_signal(
                    btc_price, eth_price, btc_ma
                )

                if entry_signal:
                    logger.info(f"Entry signal: {entry_reason}")

                    # Calculate position size
                    position_size = self.calculate_position_size(
                        account_balance=self.fetch_current_balance(),
                        expected_return=1.0,
                        win_rate=0.60,
                        stop_loss_percent=-2.5
                    )

                    # Execute entry
                    result = self.execute_market_order(
                        symbol='BTC/USDC',
                        side='buy',
                        position_size_usd=position_size,
                        current_price=btc_price
                    )

                    if result['success']:
                        session_trades.append(result)

                # Check for exit signal
                exit_signal, exit_reason = signal_generator.exit_signal(btc_price, eth_price)

                if exit_signal:
                    logger.info(f"Exit signal: {exit_reason}")
                    close_result = self.close_position('BTC/USDC', btc_price)

                    if close_result['success']:
                        session_pnl += close_result.get('pnl', 0)
                        session_trades.append(close_result)

                # Apply trailing stops
                for symbol in list(self.open_positions.keys()):
                    self.apply_trailing_stop(symbol, btc_price)

                time.sleep(check_interval_seconds)

        except KeyboardInterrupt:
            logger.info("Trading session interrupted by user")
        except Exception as e:
            logger.error(f"Error during trading session: {e}")

        # Close any remaining positions
        for symbol in list(self.open_positions.keys()):
            self.close_position(symbol)

        summary = {
            'duration_minutes': elapsed,
            'trades_executed': len(session_trades),
            'session_pnl': session_pnl,
            'session_pnl_percent': (session_pnl / self.account_balance) * 100,
            'final_balance': self.fetch_current_balance(),
            'trades': session_trades
        }

        logger.info(f"Trading session summary: {summary}")
        return summary
