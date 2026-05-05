---
title: Hyperliquid FR + Liquidation Reversal Strategy - Complete Backtest Specification
date: 2026-05-05
version: 1.0
status: PENDING_BACKTEST_VALIDATION
---

# Hyperliquid Funding Rate + Liquidation Reversal Strategy
## Complete System Logic & Backtest Specification

**Important**: This strategy is at **THEORY STAGE** - No backtest results yet. Requires validation before implementation.

---

## 📋 Context & Learning

### Background: Why This Strategy Exists

**Previous Failure (2026-04-20)**:
- Strategy: Whale Inflow Short
- Theory EV: +0.10% per trade (raw)
- Actual EV (after fees & SL/TP): **-0.09%** (NEGATIVE)
- **Lesson**: Raw EV must be validated with realistic fees, SL/TP, and out-of-sample testing

**Current Approach**:
- This document defines a NEW strategy before implementation
- Backtest spec is written for **external LLM validation**
- NO claims of "expected value" until backtest confirms it
- Must apply: Fees 0.10% (round-trip), realistic SL/TP, OOS testing

---

## 🎯 Strategy Overview

### Core Concept

Exploit two Hyperliquid-specific market inefficiencies:

1. **Funding Rate Arbitrage (FR-ARB)**: 
   - When funding rate is positive (longs are paying shorts), SELL/SHORT
   - Collect periodic funding payments every 8 hours
   - Thesis: FR is a mean-reverting signal

2. **Liquidation Level Reversal (LIQ-REV)**:
   - Identify zones where liquidations are clustered (from L2 data)
   - When price approaches liquidation level, take opposite position
   - Thesis: Liquidations cascade briefly, then reverse

---

## 📊 Market Data Requirements

### 1. OHLCV Data

```
Exchange: Hyperliquid (Perpetuals)
Pair: BTC/USDT:USDT
Timeframes Required:
  - 4h: For entry signals, RSI calculation
  - 1h: Optional, for liquidation timing
  - Daily: For trend context

Period: 2024-01-01 to 2026-04-30 (backtest period)
          2026-05-01 to 2026-05-31 (OOS validation)

API Source:
  - ccxt library (Hyperliquid supports via CCXT)
  - Or direct Hyperliquid API: /perpetual

Data Fields Required:
  - open, high, low, close, volume
  - timestamp (Unix ms)
```

### 2. Funding Rate Data

```
Frequency: Every 8 hours (when funding is paid)
Typical Payment Times: 
  - 08:00 UTC
  - 16:00 UTC
  - 00:00 UTC

Data Structure:
  {
    "timestamp": 1704067200000,  // Unix ms
    "funding_rate": 0.00015,      // 0.015% per 8h
    "next_payment": 1704096000000
  }

API Source: 
  - Hyperliquid: /funding_rates
  - CCXT: exchange.fetch_funding_history()
```

### 3. Liquidation Level Data (Optional but Recommended)

```
Structure: Order book L2 snapshot
  - Extract bids/asks at 1-minute intervals
  - Calculate liquidation price levels using mark price
  
Formula:
  Liquidation_Price = Mark_Price / (1 + Max_Leverage)
  
For Hyperliquid:
  - Max leverage: varies by coin (usually 10-50x)
  - BTC: typically 20x max
  - Liquidation_Price ≈ Current_Price / 20

Heat Map:
  - Cluster orders into $500 buckets
  - Identify 90th+ percentile clusters as "hot zones"
```

---

## 🔧 Strategy Specification

### Part 1: Funding Rate Arbitrage (FR-ARB)

#### Entry Conditions

```python
def should_enter_fr_arb(current_funding_rate, threshold=0.0005):
    """
    Enter SHORT when funding rate is positive (longs paying shorts)
    
    Args:
        current_funding_rate: float, e.g., 0.00015 (0.015%)
        threshold: minimum FR to consider (0.05% = 0.0005)
    
    Returns:
        'SHORT' if FR > threshold
        'LONG' if FR < -threshold
        None otherwise
    """
    if current_funding_rate > threshold:
        return 'SHORT'
    elif current_funding_rate < -threshold:
        return 'LONG'
    return None
```

#### Position Management

```
Entry:
  - Order Type: LIMIT (not market to avoid slippage)
  - Price: Current price (or better ask for SHORT)
  - Size: 0.5 BTC (for $190 account, use micros: 0.001 BTC)
  - Leverage: 1x (no leverage, pure arbitrage)
  - Margin: Isolated (no cross-margin)

Hold Period:
  - Until next 8h funding payment arrives
  - Typical hold: 4 to 24 hours
  - Max hold: 48 hours (must close if FR reverses)

Exit Trigger 1: Take Profit (Primary)
  - TP: +0.40% (collect funding + small price move)
  - When price moves +0.40% in our direction, close immediately
  - Profit = Funding (0.015%) + Price Move (0.40%) - Fees (0.10%) = +0.255%

Exit Trigger 2: Stop Loss (Risk Control)
  - SL: -1.0% (max acceptable loss per trade)
  - If price goes against us by 1.0%, close to limit losses
  - Loss = -1.0% - Fees (0.10%) = -1.10%

Exit Trigger 3: Funding Reversal (Signal Change)
  - If funding rate turns negative before TP/SL, exit immediately
  - Avoids holding against the new funding direction
  - Expected close-out time: 6-8 hours after entry
```

#### Expected Parameters (Theory)

```
Entry Frequency:
  - 3-5 entries per day (funding changes multiple times)
  - 90-150 entries per month
  
Win Rate:
  - Theory: ~65% (funded trades)
  - Based on: Consistent + 0.015% funding payment
  - Risk: Funding can turn negative 1-2x/week

Average Win: +0.255% per winning trade
Average Loss: -1.10% per losing trade
P&L = (65% × 0.255%) + (35% × -1.10%) = +0.166% - 0.385% = **-0.219%** (RAW)

⚠️ CRITICAL: Raw calculation shows negative! Must backtest to verify actual outcomes.
```

---

### Part 2: Liquidation Level Reversal (LIQ-REV)

#### Entry Conditions

```python
def should_enter_liq_reversal(
    current_price, 
    liquidation_levels,  # list of price levels where liquidations cluster
    rsi_4h,
    max_distance_pct=0.5
):
    """
    Enter reverse position when price approaches liquidation level
    
    Logic:
      - Liquidations at level X means SHORT orders will be forced to cover
      - When price drops TO liquidation level, shorts get liquidated
      - This causes SHORT-covering (buying), driving price up temporarily
      - We catch this bounce by going LONG before the liquidation
    
    Args:
        current_price: float, e.g., 42100
        liquidation_levels: list, e.g., [42000, 41500, 41000]
        rsi_4h: float, 0-100
        max_distance_pct: max distance from liq level to consider (0.5 = 0.5%)
    
    Returns:
        ('LONG', price) if price nears liquidation level + RSI < 30
        ('SHORT', price) if price nears liquidation level + RSI > 70
        None otherwise
    """
    for liq_level in liquidation_levels:
        distance = abs(current_price - liq_level) / liq_level * 100
        
        # If price is within 0.5% of liquidation level
        if distance < max_distance_pct:
            # If price is BELOW liq level and RSI is oversold
            if current_price < liq_level and rsi_4h < 30:
                return ('LONG', liq_level)
            # If price is ABOVE liq level and RSI is overbought
            elif current_price > liq_level and rsi_4h > 70:
                return ('SHORT', liq_level)
    
    return None
```

#### Position Management

```
Entry:
  - Order Type: LIMIT
  - Price: At liquidation level (wait for price to reach it)
  - Size: 0.5 BTC (same as FR-ARB for consistency)
  - Leverage: 1x (no leverage)
  - Margin: Isolated

Hold Period:
  - Duration: 4-12 hours
  - Purpose: Capture reversal bounce after liquidation cascade
  
Exit Trigger 1: Take Profit (Primary)
  - TP: +0.95% (larger move expected from liquidation cascade)
  - Example: Enter at $42,000 (liq level), exit at $42,400 (+0.95%)
  - Profit = Price Move (0.95%) - Fees (0.10%) = +0.85%

Exit Trigger 2: Stop Loss (Risk Control)
  - SL: -0.24% (tight SL, protects if liquidation fails)
  - Example: Enter at $42,000, SL at $41,900
  - Loss = -0.24% - Fees (0.10%) = -0.34%

Exit Trigger 3: Time-Based (Max Hold)
  - If no move after 12 hours, exit at market
  - Avoids holding unrelated positions
```

#### Expected Parameters (Theory)

```
Entry Frequency:
  - 1-3 entries per day (liquidation levels stable but price approaches slowly)
  - 20-40 entries per month

Win Rate:
  - Theory: ~58% (liquidations don't always cascade)
  - Based on: Price action near liquidation zones is volatile

Average Win: +0.85% per winning trade
Average Loss: -0.34% per losing trade
P&L = (58% × 0.85%) + (42% × -0.34%) = +0.493% - 0.143% = **+0.350%** (RAW)

⚠️ This appears positive, but must be validated via backtest.
```

---

## 📈 Combined Strategy Expected Value (THEORY ONLY)

### Monthly P&L Calculation (UNVALIDATED)

```
Strategy 1: FR Arbitrage (90-150 entries/month)
  - Win Rate: 65% | Avg Win: +0.255% | Avg Loss: -1.10%
  - Monthly P&L (theory): -0.22% → **NEGATIVE**

Strategy 2: Liquidation Reversal (20-40 entries/month)
  - Win Rate: 58% | Avg Win: +0.85% | Avg Loss: -0.34%
  - Monthly P&L (theory): +0.35% → **POSITIVE**

Combined (150 total entries):
  - Expected Monthly: -0.22% + 0.35% = **+0.13%** (THEORY)
  - For $190 account: +$0.25/month
  - Hand-fee after 0.10% round-trip: **-0.07%** (NET NEGATIVE?)

⚠️ CRITICAL: Theory shows possible NEGATIVE return after fees.
   Backtest MUST confirm whether this strategy is viable.
```

---

## 🧪 Backtest Implementation Guide

### Required Inputs for LLM Backtest

```
1. Data Collection:
   - OHLCV 4h: BTC/USDT:USDT from Hyperliquid, 2024-01-01 to 2026-05-31
   - Funding rates: 8h frequency, full history
   - Liquidation levels: L2 data snapshots hourly
   
2. Backtester Setup:
   - Framework: Freqtrade, Backtrader, or custom Python
   - Starting Capital: $190 USDT
   - Fees: 0.05% per side (0.10% round-trip)
   - Slippage: 0.05% (conservative for limit orders)
   - Leverage: 1x (no leverage)
   - Max Positions: 2 open (FR + LIQ can overlap)
   
3. Test Periods:
   - In-Sample (IS): 2024-01-01 to 2025-06-30
   - Out-of-Sample (OOS): 2025-07-01 to 2026-05-31
   - Purpose: Detect overfitting
   
4. Validation Metrics Required:
   - Total Return (%)
   - Sharpe Ratio
   - Win Rate (%)
   - Profit Factor (Total Wins / Total Losses)
   - Max Drawdown (%)
   - Average Trade Duration
   - Monthly breakdown (Jan-May 2026)
```

### Backtest Code Template (Freqtrade)

```python
# File: strategies/HyperliquidFRLiqStrategy.py

from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
import talib
import pandas as pd

class HyperliquidFRLiqStrategy(IStrategy):
    """
    Funding Rate Arbitrage + Liquidation Reversal
    For Hyperliquid BTC/USDT:USDT perpetuals
    """
    
    STOPLOSS = -0.01
    TRAILING_STOPLOSS_POSITIVE = 0.004
    TRAILING_STOPLOSS_POSITIVE_OFFSET = 0.01
    TRAILING_ONLY_OFFSET_IS_REACHED = True
    
    TIMEFRAME = '4h'
    
    def __init__(self, config):
        super().__init__(config)
        self.funding_rate = None
        self.liquidation_levels = None
    
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Calculate RSI and other indicators"""
        dataframe['rsi'] = talib.RSI(dataframe['close'], timeperiod=14)
        return dataframe
    
    def populate_entry_signals(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Part 1: FR Arbitrage Entry
        """
        # Get current funding rate (assume API fetch before strategy runs)
        fr = self.get_funding_rate()
        
        # FR-ARB: SHORT when FR > 0.05%
        dataframe.loc[
            (fr > 0.0005) & (dataframe['volume'] > 0),
            'enter_short'
        ] = 1
        
        # FR-ARB: LONG when FR < -0.05%
        dataframe.loc[
            (fr < -0.0005) & (dataframe['volume'] > 0),
            'enter_long'
        ] = 1
        
        """
        Part 2: Liquidation Reversal Entry
        """
        liq_levels = self.get_liquidation_levels()
        
        for liq_level in liq_levels:
            distance_pct = abs(dataframe['close'] - liq_level) / liq_level * 100
            
            # LIQ-REV: LONG when price near liq level + RSI < 30
            dataframe.loc[
                (distance_pct < 0.5) & (dataframe['close'] < liq_level) & 
                (dataframe['rsi'] < 30),
                'enter_long'
            ] = 1
            
            # LIQ-REV: SHORT when price near liq level + RSI > 70
            dataframe.loc[
                (distance_pct < 0.5) & (dataframe['close'] > liq_level) & 
                (dataframe['rsi'] > 70),
                'enter_short'
            ] = 1
        
        return dataframe
    
    def populate_exit_signals(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Exit signals (TP/SL handled by stoploss config)"""
        return dataframe
    
    def get_funding_rate(self) -> float:
        """Fetch current funding rate from Hyperliquid"""
        # TODO: Implement API call to Hyperliquid /funding_rates
        pass
    
    def get_liquidation_levels(self) -> list:
        """Extract liquidation level clusters from L2 data"""
        # TODO: Implement Hyperliquid L2 snapshot parsing
        pass
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate, **kwargs):
        """Custom SL logic for both strategies"""
        # FR-ARB: SL -1.0%
        # LIQ-REV: SL -0.24%
        # Trailing: +0.40% for FR, +0.95% for LIQ
        pass
```

### Configuration File (Freqtrade config.json)

```json
{
  "max_open_trades": 2,
  "stake_currency": "USDT",
  "dry_run": true,
  "dry_run_wallet": 190,
  
  "exchange": {
    "name": "hyperliquid",
    "pair_whitelist": ["BTC/USDT:USDT"],
    "timeframe": "4h"
  },
  
  "stake_amount": "10",
  
  "stoploss": -0.01,
  "trailing_stoploss": {
    "trailing_stop": true,
    "trailing_stop_positive": 0.004,
    "trailing_stop_positive_offset": 0.01,
    "trailing_only_offset_is_reached": true
  },
  
  "order_types": {
    "entry": "limit",
    "exit": "limit",
    "stoploss": "market",
    "stoploss_on_exchange": false
  },
  
  "fee": 0.001,  # 0.10% round-trip
  
  "timeframe": "4h"
}
```

---

## ✅ Backtest Validation Checklist

### Must-Have Results Before Implementation

- [ ] **IS Period (2024-2025.6)**:
  - Total Return: Positive or Negative?
  - Sharpe Ratio: > 0.5 (acceptable)
  - Win Rate: FR > 50%, LIQ > 50%
  - Max Drawdown: < 15%

- [ ] **OOS Period (2025.7-2026.5)**:
  - Total Return: Same sign as IS (positive EV persists)?
  - Sharpe Ratio: > 0.5
  - Win Rate: Maintained or degraded?
  - **Critical**: OOS EV must be > 0 to proceed

- [ ] **Monthly Breakdown**:
  - Which months profitable? Which not?
  - Pattern: FR works in high-FR months, LIQ works in consolidation?

- [ ] **Fee Impact**:
  - Raw EV vs Net EV (after 0.10% fees)
  - If Raw > 0 but Net < 0: Not viable

- [ ] **Profit Factor**:
  - Total Wins / Total Losses > 1.1 (acceptable)
  - If < 1.0: Strategy is losing money

---

## 🚫 Rejection Criteria

**If ANY of these occur, REJECT the strategy**:

```
1. OOS EV < 0 (negative expected value)
2. Win Rate < 50% for either component
3. Max Drawdown > 20%
4. Profit Factor < 1.0
5. Net EV (after fees) becomes negative
6. Monthly loss in > 3 months during OOS period
```

---

## 📌 For Next LLM Session

**To run this backtest, provide to the next LLM:**

```
Files:
- This document (HYPERLIQUID_FR_LIQ_STRATEGY_BACKTEST_SPEC.md)
- Freqtrade strategy code (above)
- Historical data CSV: 
  - BTC/USDT 4h OHLCV (2024-2026)
  - Funding rates (2024-2026)

Instructions:
"Execute backtest using Freqtrade or Backtrader.
Output: Monthly P&L, Sharpe, Win Rate, Profit Factor, Max DD.
Decision: APPROVE (EV > 0 after fees) or REJECT (EV < 0)"

Expected Output Format:
{
  "is_period": {
    "total_return": "+2.3%",
    "sharpe": 1.2,
    "win_rate": "56%",
    "profit_factor": 1.15,
    "max_drawdown": "-8.4%"
  },
  "oos_period": {
    "total_return": "+1.8%",
    "sharpe": 0.9,
    "win_rate": "54%",
    "profit_factor": 1.08,
    "max_drawdown": "-6.2%"
  },
  "decision": "APPROVE / REJECT",
  "reason": "..."
}
```

---

## 📝 Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| **Strategy Logic** | ✅ Defined | FR + Liquidation reversal |
| **Backtest Spec** | ✅ Complete | Ready for external validation |
| **Theoretical EV** | ⚠️ Uncertain | Theory shows +0.13% but very thin |
| **Actual EV** | ❌ Unknown | **Backtest required** |
| **Implementation Ready?** | ❌ NO | Wait for backtest results |
| **Risk Assessment** | ⚠️ Medium | Small account ($190), thin margins |

---

**Status: AWAITING BACKTEST VALIDATION**

This document is input for external LLM backtest. Do not implement until OOS validation confirms EV > 0 after fees.

---

**Created**: 2026-05-05  
**Version**: 1.0  
**Purpose**: Rigorous backtest specification to avoid repeating Whale Inflow Short failure
