# -*- coding: utf-8 -*-
# Fixed main function
import os, sys, json, time, logging, argparse
import datetime as dt
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Trading config
@dataclass
class TradingConfig:
    exchange_id: str = "hyperliquid"
    symbol: str = "BTC"
    timeframe: str = "4h"
    use_testnet: bool = False
    wallet_address: str = field(default_factory=lambda: os.getenv("HL_WALLET_ADDRESS", ""))
    private_key: str = field(default_factory=lambda: os.getenv("HL_PRIVATE_KEY", ""))
    lookback_days: int = 180
    data_csv: str = "btc_usdt_4h.csv"
    ema_fast: int = 50
    ema_slow: int = 200
    ema_slope_period: int = 10
    ema_range_pct: float = 0.01
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    rsi_exit_long: float = 65.0
    rsi_exit_short: float = 35.0
    atr_period: int = 14
    atr_sl_mult: float = 2.0
    risk_pct: float = 0.015
    max_hold_bars: int = 30
    initial_cash: float = 100.0
    commission_pct: float = 0.0005
    max_position_pct: float = 0.50
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_halt_pct: float = 0.10
    order_type: Literal["limit", "market"] = "limit"
    slippage_pct: float = 0.001
    min_notional: float = 10.0
    log_dir: str = "logs"
    state_file: str = "trade_state.json"

def setup_logging(c, debug=False):
    Path(c.log_dir).mkdir(exist_ok=True)
    lg = logging.getLogger("AdaptiveV5_HL")
    lg.setLevel(logging.DEBUG); lg.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(f"{c.log_dir}/v5_hl_{dt.datetime.now():%Y%m%d_%H%M%S}.log")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(); ch.setLevel(logging.DEBUG if debug else logging.INFO); ch.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(ch)
    return lg

def create_env_file():
    """Create .env file with default configuration"""
    env_content = """# Hyperliquid API Credentials
# =========================================================
# IMPORTANT: Never commit this file to git or share publicly!
# Your private key gives full access to your wallet.
# =========================================================

# Hyperliquid Wallet Configuration
# Get your wallet address from MetaMask (Arbitrum network)
HL_WALLET_ADDRESS=0x8455b70a5a0d942eb9a1598a0e9e1214a3b31b55

# Hyperliquid Private Key
# Export from MetaMask: Account Details -> Export Private Key
HL_PRIVATE_KEY=0x42cbf5670eead7cfda780b9d09d4ac09dcbf9d0b8ca1b0d169f49f1ae4d358c6

# =========================================================
# Network Configuration (Optional - defaults to mainnet)
# Set HL_USE_TESTNET=true for testnet trading
# HL_USE_TESTNET=false for mainnet (real money)
HL_USE_TESTNET=false
"""
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("✅ .env file created with your Hyperliquid API credentials")
        print("")
        print("Configuration:")
        print("  Wallet Address: 0x8455...31b55")
        print("  Private Key: 0x42cb...358c6")
        print("  Network: Mainnet (real money)")
        print("")
        print("⚠️  SECURITY REMINDERS:")
        print("  1. Never share your .env file or private key")
        print("  2. Use testnet first: set HL_USE_TESTNET=true")
        print("  3. Start with small amounts")
        print("")
        print("To use testnet, edit .env and change HL_USE_TESTNET=true")
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        raise

def main():
    print("="*70)
    print("Starting BTC/USDT 4H Adaptive RSI v5 - Hyperliquid Edition")
    print("="*70)

    pa=argparse.ArgumentParser()
    pa.add_argument("--mode",choices=["backtest","paper","live"],default="backtest")
    pa.add_argument("--days",type=int,default=180)
    pa.add_argument("--exchange",choices=["binance","hyperliquid"],default="hyperliquid")
    pa.add_argument("--testnet",action="store_true",help="Use Hyperliquid Testnet")
    pa.add_argument("--debug",action="store_true",help="Enable debug logging")
    pa.add_argument("--interval",type=int,default=60,help="Loop interval in seconds (default: 60)")
    args=pa.parse_args()

    print(f"DEBUG: Mode={args.mode}, Interval={args.interval}s, Testnet={args.testnet}")

    try:
        # Import checks
        print("Checking dependencies...")
        import ccxt
        print("  - ccxt: OK")
        try:
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            print("  - hyperliquid-python-sdk: OK")
        except ImportError:
            print("  - hyperliquid-python-sdk: NOT FOUND - Install with: pip install hyperliquid-python-sdk")
            raise
        from eth_account import Account
        print("  - eth-account: OK")
        print("\nAll dependencies OK!\n")

        # Create .env file if it doesn't exist
        if not os.path.exists(".env"):
            print("Creating .env file...")
            create_env_file()

        c=TradingConfig()
        c.lookback_days = args.days
        c.use_testnet = args.testnet
        c.exchange_id = args.exchange

        print(f"Configuration: Days={c.lookback_days}, Testnet={c.use_testnet}")

        try:
            lg=setup_logging(c, debug=args.debug)
            print("Log setup complete")

            lg.info(f"Mode: {args.mode} | v5 Adaptive RSI (Hyperliquid Edition) | Days: {c.lookback_days}")
            lg.info(f"Exchange: {args.exchange} ({'Testnet' if c.use_testnet else 'Mainnet'})")

            if args.mode=="backtest":
                print("Entering BACKTEST mode...")
                lg.info("Entering BACKTEST mode")
                print("WARNING: Backtest not implemented in this simplified version")
                lg.info("Backtest not implemented")
            elif args.mode=="paper":
                print("Entering PAPER mode...")
                lg.info("Entering PAPER mode")
                lg.info("PAPER MODE (Read-only Hyperliquid)")
                print("WARNING: LiveEngine not implemented in this simplified version")
            elif args.mode=="live":
                print("Entering LIVE mode...")
                print("WARNING: This will execute real trades!")
                print("="*70)
                lg.info("Entering LIVE mode")
                lg.info("WARNING: LIVE mode - REAL MONEY TRADING")
                print("WARNING: LiveEngine not implemented in this simplified version")
            else:
                lg.error(f"UNKNOWN MODE: {args.mode}")

        except KeyboardInterrupt:
            print("\n\nUser interrupted execution.")
            sys.exit(0)
        except Exception as e:
            import traceback
            print(f"\n{'='*70}", file=sys.stderr)
            print(f"CRITICAL ERROR: {e}", file=sys.stderr)
            print(f"{'='*70}\n", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            print(f"\nCheck the log file for details.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nUser interrupted execution.")
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        print(f"{'='*70}\n", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        print(f"\nCheck the log file for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()