# BTC/USDT 4H ADAPTIVE RSI v5 - Hyperliquid Edition

**Regime-Aware Trading System on Hyperliquid Perpetual DEX**

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Hyperliquid Setup](#hyperliquid-setup)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Strategy Details](#strategy-details)
- [Risk Management](#risk-management)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

v5 Adaptive RSI is a production-ready trading bot that:
- Detects market regimes (BULL/BEAR/RANGE)
- Executes mean reversion trades using RSI
- Adapts automatically to market conditions
- Runs on Hyperliquid Perpetual DEX for low fees and no KYC

**Key Innovation**: v1-v4 failed because they were LONG-ONLY during a bear market. v5 detects regime and trades accordingly:
- **BULL** → Long RSI dips (buy RSI<35, sell RSI>65)
- **BEAR** → Short RSI pops (short RSI>65, cover RSI<35)
- **RANGE** → Skip (cash preservation)

---

## ✨ Features

### Trading Engine
- **Regime Detection**: EMA-based trend and slope analysis
- **RSI Mean Reversion**: Wilder's RSI for momentum entries/exits
- **Adaptive Risk**: ATR-based position sizing (1.5% per trade)
- **Split Exit**: Primary at RSI recovery, backup at stop loss

### Exchange Integration
- **Hyperliquid Perpetual DEX**: Low 0.05% fees, no KYC
- **Limit Orders (GTC)**: Best execution, no slippage
- **Market Order Fallback**: With slippage protection
- **Testnet Support**: Test before real money

### Safety Mechanisms
- **Max 50% Position Size**: Prevents over-leverage
- **Stop Loss**: 2.0 ATR below entry
- **Consecutive Loss Cooldown**: 3 losses → 6 bar pause
- **Drawdown Halt**: 10% DD stops new entries
- **Time Exit**: Max 30 bars (5 days on 4H timeframe)

---

## 🔐 Hyperliquid Setup

### Prerequisites

1. **MetaMask Wallet**: Download from [metamask.io](https://metamask.io)
2. **ETH on Arbitrum**: Required for gas fees
3. **USDC for Trading**: Deposit to Hyperliquid

### Step 1: Get Wallet Address

1. Open MetaMask
2. Copy your Arbitrum wallet address
3. Save as `HL_WALLET_ADDRESS`

### Step 2: Get Private Key (⚠️ SECURITY WARNING)

**⚠️ CRITICAL: Never share your private key! Only use with testnet first!**

**For Testnet (Recommended)**:
1. Create a new MetaMask wallet (separate from mainnet)
2. Fund with test ETH from [Arbitrum Sepolia Faucet](https://faucet.quicknode.com/arbitrum/sepolia)
3. Export private key:
   - MetaMask → Account Details → Export Private Key
   - Enter password to reveal
   - Save as `HL_PRIVATE_KEY`

**For Mainnet**:
1. Ensure you trust the software
2. Only use wallets with small amounts initially
3. Follow same export process above

### Step 3: Fund Hyperliquid

**Testnet**:
1. Visit [testnet.hyperliquid.xyz](https://testnet.hyperliquid.xyz)
2. Connect MetaMask
3. Deposit test USDC/ETH from testnet faucet

**Mainnet**:
1. Visit [app.hyperliquid.xyz](https://app.hyperliquid.xyz)
2. Connect MetaMask
3. Deposit USDC from Arbitrum

### Step 4: Get API Keys

Hyperliquid doesn't require API keys - uses wallet signing directly!

However, you need:
- **Wallet Address**: `HL_WALLET_ADDRESS`
- **Private Key**: `HL_PRIVATE_KEY` (for signing orders)

---

## 📦 Installation

### 1. Clone/Download

```bash
cd C:\Users\user\Desktop\cursor\trade
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `hyperliquid-python-sdk`: Hyperliquid API
- `eth-account`: Ethereum wallet signing
- `python-dotenv`: Environment variables
- `ccxt`: Historical data for backtest
- `pandas`, `numpy`: Data analysis

### 3. Configure Environment Variables

Create `.env` file in project root:

```env
# Hyperliquid Credentials
HL_WALLET_ADDRESS=your_wallet_address_here
HL_PRIVATE_KEY=your_private_key_here

# Note: Never commit .env to git!
```

**⚠️ SECURITY**: Add `.env` to `.gitignore`:

```bash
echo ".env" >> .gitignore
echo "*.log" >> .gitignore
echo "logs/" >> .gitignore
echo "trade_state.json" >> .gitignore
```

---

## ⚙️ Configuration

Edit parameters in `force_run_hl.py`:

```python
@dataclass
class TradingConfig:
    # Exchange
    exchange_id: str = "hyperliquid"
    symbol: str = "BTC"  # Hyperliquid uses coin name, not pair
    timeframe: str = "4h"
    use_testnet: bool = False  # Set True for testnet
    
    # Regime Detection
    ema_fast: int = 50
    ema_slow: int = 200
    ema_slope_period: int = 10
    ema_range_pct: float = 0.01  # EMAs within 1% = range
    
    # RSI
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    rsi_exit_long: float = 65.0
    rsi_exit_short: float = 35.0
    
    # Risk
    atr_period: int = 14
    atr_sl_mult: float = 2.0  # Stop loss distance
    risk_pct: float = 0.015  # 1.5% of equity per trade
    max_hold_bars: int = 30
    
    # Safety
    initial_cash: float = 100_000.0
    commission_pct: float = 0.0005  # Hyperliquid: 0.05%
    max_position_pct: float = 0.50  # Max 50% position
    max_consecutive_losses: int = 3
    cooldown_bars: int = 6
    drawdown_halt_pct: float = 0.10
    
    # Order Settings
    order_type: Literal["limit", "market"] = "limit"
    slippage_pct: float = 0.001  # 0.1% for limit orders
```

---

## 🚀 Usage

### Backtest (Historical Data)

```bash
# 180 days (default)
python force_run_hl.py --mode backtest

# Custom period
python force_run_hl.py --mode backtest --days 90
```

**Output**: Performance report with metrics, trade history, regime analysis

---

### Paper Trading (Testnet - Read-Only)

```bash
# Testnet (dry run, no real orders)
python force_run_hl.py --mode live --testnet
```

**What it does**:
- Connects to Hyperliquid Testnet
- Monitors market conditions
- Logs signals without executing orders
- Perfect for strategy validation

---

### Live Trading (Mainnet - Real Money)

⚠️ **WARNING: Start with testnet! Only use mainnet after thorough testing!**

```bash
# Mainnet with real orders
python force_run_hl.py --mode live

# Or explicitly specify exchange
python force_run_hl.py --mode live --exchange hyperliquid
```

**What it does**:
- Connects to Hyperliquid Mainnet
- Executes real orders
- Manages positions automatically
- Logs all trades to `logs/` directory

---

## 📊 Strategy Details

### Regime Detection

| Condition | Regime | Action |
|-----------|---------|--------|
| EMA50 > EMA200 & Slope > 0 | **BULL** | Look for long entries |
| EMA50 < EMA200 & Slope < 0 | **BEAR** | Look for short entries |
| |EMAs within 1%| **RANGE** | No new entries |

### Entry Logic

**Long Entry (BULL)**:
- Regime = BULL
- RSI < 35 (oversold)
- Volume OK (ATR-based risk)

**Short Entry (BEAR)**:
- Regime = BEAR
- RSI > 65 (overbought)
- Volume OK (ATR-based risk)

**No Entry (RANGE)**:
- Regime = RANGE
- Skip for cash preservation

### Exit Logic

**Long Exit**:
- **Primary**: RSI > 65 (momentum recovery)
- **Backup**: Price < Stop Loss (Entry - 2.0 ATR)
- **Time**: Max 30 bars

**Short Exit**:
- **Primary**: RSI < 35 (momentum recovery)
- **Backup**: Price > Stop Loss (Entry + 2.0 ATR)
- **Time**: Max 30 bars

### Order Execution

**Default: Limit Order (GTC)**
```python
order_type = {"limit": {"tif": "Gtc"}}  # Good till Cancelled
```

Advantages:
- Best price at entry
- No slippage
- Cancel if not filled

**Fallback: Market Order** (if urgent)
```python
order_type = "market"  # Market order with slippage protection
```

---

## 🛡️ Risk Management

### Position Sizing

```python
risk_amount = equity * 0.015  # 1.5% of equity
sl_distance = atr * 2.0  # 2.0 ATR stop loss
position_size = min(risk_amount / sl_distance, equity * 0.50 / price)
```

**Conservative Approach**:
- Max 50% of equity in single position
- 1.5% risk per trade
- 2.0 ATR stop loss

### Safety Mechanisms

| Mechanism | Trigger | Action |
|-----------|---------|--------|
| Stop Loss | Price hits SL level | Close position |
| RSI Exit | RSI crosses threshold | Close position |
| Time Exit | 30 bars held | Close position |
| Consecutive Losses | 3 losses in a row | 6 bar cooldown |
| Drawdown Halt | Equity DD > 10% | Stop new entries |

---

## 📈 Performance (Backtest Results)

### 6-Month Test (Sep 2025 - Mar 2026)

| Metric | Value |
|--------|-------|
| Total Return | +7.40% |
| Max Drawdown | 2.86% |
| Sharpe Ratio | 1.50 |
| Win Rate | 60.0% |
| Profit Factor | 9.38 |
| Expectancy | +$1,527.56/trade |

### Regime Analysis

| Regime | % of Time | Trades |
|--------|-----------|--------|
| BEAR | 47% | 7 |
| RANGE | 40% | 2 |
| BULL | 13% | 1 |

**Key Insight**: BEAR regime is most profitable (75% win rate on shorts)

---

## 🔧 Troubleshooting

### Import Error: hyperliquid packages not found

```bash
pip install --upgrade hyperliquid-python-sdk eth-account
```

### Error: No wallet credentials

**Solution**: Check `.env` file:
```bash
# Verify .env exists and contains:
cat .env
```

### Error: Insufficient funds

**Solution**: Deposit USDC to Hyperliquid:
- Testnet: Use testnet faucet
- Mainnet: Bridge USDC to Arbitrum

### Error: Order rejected

**Common causes**:
1. Insufficient margin
2. Price too far from market
3. Slippage protection too tight

**Solution**: Check logs for specific error message

### Connection Error to Hyperliquid

**Testnet down?** Check: https://testnet.hyperliquid.xyz
**Mainnet down?** Check: https://app.hyperliquid.xyz

---

## 📝 Logs & State

### Log Files

Location: `logs/v5_hl_YYYYMMDD_HHMMSS.log`

Contains:
- All trade executions
- Error messages
- Market data updates
- Performance metrics

### State File

Location: `trade_state.json`

Stores:
- Current position (LONG/SHORT/none)
- Entry price & time
- Stop loss level
- Cooldown status
- Peak equity

**Important**: Never delete this file while bot is running!

---

## 🔐 Security Best Practices

1. **Separate Wallets**:
   - Use dedicated wallet for trading
   - Keep majority of funds in cold storage

2. **Testnet First**:
   - Always test on testnet first
   - Verify strategy behavior
   - Check for bugs

3. **Start Small**:
   - Begin with small amounts
   - Monitor for 1-2 weeks
   - Gradually increase position size

4. **Never Share Keys**:
   - Private key is your master key
   - Never post on forums/social media
   - Use hardware wallet for large amounts

5. **Regular Backups**:
   - Backup `trade_state.json`
   - Save logs periodically
   - Keep copy of `.env` (offline)

---

## 📞 Support

### Documentation
- Hyperliquid API: https://hyperliquid.gitbook.io/hyperliquid-docs/
- eth-account: https://eth-account.readthedocs.io/

### Issues
- Check logs in `logs/` directory
- Verify `.env` configuration
- Test on testnet first

---

## 📄 License

This software is provided as-is for educational purposes. Use at your own risk.

**DISCLAIMER**: Cryptocurrency trading involves substantial risk of loss. Past performance is not indicative of future results. The authors are not responsible for any financial losses incurred.

---

**Happy Trading! 🚀**
