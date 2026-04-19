# Whale Wallet Discovery Guide

## Overview

`discover_whale_wallets.py` は Hyperliquid leaderboard からトップパフォーマーのウォレットを自動発見し、`whale_wallets.json` に設定するツールです。

機関投資家基準でフィルタリングされたウォレットのみを選定：
- **ROI**: >= 20% (past 90 days)
- **Trades**: >= 200 closed trades (statistical significance)
- **Win Rate**: >= 50%
- **AUM**: $1M - $100M (institutional scale, not market-moving)
- **Sortino**: >= 2.0 (risk-adjusted returns)

---

## Usage Options

### Option 1: Auto-Discovery (Recommended if API works)

```bash
python discover_whale_wallets.py --auto
```

**What it does:**
1. Queries Hyperliquid leaderboard APIs
2. Filters for qualified wallets
3. Detects correlated clusters (synchronized entry patterns)
4. Validates via Hyperliquid clearinghouseState API
5. Scores by actual Sortino ratio from 90-day fills
6. Displays top candidates for user confirmation

**Output:**
```
======================================================================
WHALE WALLET DISCOVERY - Multi-Source Investigation
======================================================================

Whale_1
  Address: 0x1234567890abcdef1234567890abcdef12345678
  Sortino: 3.42 | WR: 61.2% | Trades: 312 | AUM: $8.2M

Whale_2
  Address: 0x9876543210fedcba9876543210fedcba98765432
  Sortino: 2.98 | WR: 58.4% | Trades: 287 | AUM: $15.1M

...

Proceed with update? (y/n): y
✓ Updated whale_wallets.json
```

---

### Option 2: Manual Entry (No API Required)

```bash
python discover_whale_wallets.py --manual
```

**What it does:**
1. Opens interactive prompt
2. User enters wallet addresses from leaderboard (copy-paste)
3. Validates each address on Hyperliquid
4. Scores by actual performance
5. Updates config

**Steps:**
1. Visit [Hyperliquid Leaderboard](https://app.hyperliquid.xyz/leaderboard)
2. Sort by **ROI** (descending) or **Profit** (descending)
3. Filter for wallets with:
   - ROI > 20%
   - Trades > 50-100 (visible on leaderboard)
   - Account Value > $1M
4. Copy wallet address (click on row)
5. Paste into prompt: `Wallet 1 address (or 'done'):`
6. Repeat for 6-10 wallets
7. Script validates and updates config

**Example Leaderboard Criteria:**

| Column | Filter |
|--------|--------|
| ROI % | > 20 |
| Trades | > 200 (check via HyperStats if needed) |
| Account Value | $1M - $100M |
| Recent Activity | Past 7 days |

---

## Finding Top Traders: Public Tools

### Official Tools
- **[Hyperliquid Leaderboard](https://app.hyperliquid.xyz/leaderboard)** - Official, real-time
- **[HyperStats](https://hyperstats.org)** - Whale tracker, performance grades (S+, S, A)
- **[CoinGlass Hyperliquid](https://www.coinglass.com/hyperliquid)** - Wallet analytics
- **[HyperTracker](https://hypertracker.io)** - Live position monitoring

### Process: Finding High-Quality Wallets

1. **Open HyperStats or Hyperliquid Leaderboard**
2. **Sort by ROI (past 90 days)** descending
3. **Identify candidates:**
   ```
   Top 1:  ROI +45%, Account: $450k, Trades: 85
   Top 2:  ROI +38%, Account: $380k, Trades: 72
   Top 3:  ROI +32%, Account: $320k, Trades: 64
   ...
   ```
4. **Click on wallet → Copy address**
5. **Paste into discovery script**

---

## Output: whale_wallets.json

After successful discovery, you'll have:

```json
{
  "wallets": [
    {
      "address": "0x1234567890abcdef1234567890abcdef12345678",
      "label": "Whale_1",
      "active": true,
      "notes": "Sortino: 3.42, WR: 61.2%, Trades: 312, AUM: $8.2M"
    },
    {
      "address": "0x9876543210fedcba9876543210fedcba98765432",
      "label": "Whale_2",
      "active": true,
      "notes": "Sortino: 2.98, WR: 58.4%, Trades: 287, AUM: $15.1M"
    }
  ],
  "scoring_config": {
    "lookback_days": 90,
    "min_trades": 200,
    "min_sortino": 2.0,
    "min_win_rate": 0.50,
    "min_account_value": 1000000,
    "max_account_value": 100000000
  },
  "consensus_config": {
    "min_agreeing_wallets": 3,
    "min_agreement_pct": 0.60
  }
}
```

---

## Validation Checklist

After discovery, verify:

- [ ] **Wallet count**: 6-10 wallets configured
- [ ] **Min AUM met**: Each wallet > $1M account value
- [ ] **Win rate > 50%**: Confirm in notes
- [ ] **Sortino > 2.0**: Institutional-grade threshold
- [ ] **Independent signals**: No more than 2-3 wallets from same cluster

Test with:
```bash
python whale_monitor.py --once
```

Expected output:
```
Whale_1: sortino=3.42, wr=61.2%, trades=312, ev=0.0189
Whale_2: sortino=2.98, wr=58.4%, trades=287, ev=0.0156
...
Signal written: direction=LONG, strength=0.62, valid=True
```

---

## Troubleshooting

### Q: "No qualifying wallets found"
**Causes:**
- Leaderboard API unreachable
- Invalid test addresses
- Wallets don't meet Sortino >= 2.0 threshold

**Solutions:**
1. Try manual mode: `python discover_whale_wallets.py --manual`
2. Visit leaderboard directly: https://app.hyperliquid.xyz/leaderboard
3. Copy real wallet addresses (ROI > 20%, Trades > 200)

### Q: "Address not found on Hyperliquid"
- Check that address is valid (0x... 42 chars)
- Verify wallet is active on Hyperliquid (has positions)
- Try a different wallet from leaderboard

### Q: "Sortino < 2.0, skipped"
- Wallet doesn't have strong enough historical performance
- Choose wallets with higher ROI from leaderboard
- Look for S+ or S grade on HyperStats

---

## Next Steps

1. **Run discovery:**
   ```bash
   python discover_whale_wallets.py --manual  # or --auto
   ```

2. **Test signal generation:**
   ```bash
   python whale_monitor.py --once
   ```

3. **Verify outcome logging:**
   ```bash
   python qwen_unified_live.py --once
   # Check trade_alignment_log.json has records
   ```

4. **Start full system:**
   ```bash
   Qwen_本番自動売買_起動.bat
   ```

5. **Monitor for 30 days:**
   ```bash
   python validate_whale_alpha.py
   # After 30+ trades, check if aligned trades outperform
   ```

---

## Parameter Explanation

### Scoring Config

| Parameter | Value | Reason |
|-----------|-------|--------|
| `min_trades` | 200 | p < 0.01 statistical significance |
| `min_sortino` | 2.0 | Institutional minimum standard |
| `min_win_rate` | 0.50 | Enforced in scoring (was 0.45 before) |
| `min_account_value` | $1M | Institutional-grade threshold |
| `max_account_value` | $100M | Avoid market-moving wallets |
| `lookback_days` | 90 | Standard 3-month evaluation window |
| `rescore_interval` | 24h | Daily refresh (was weekly before) |

### Consensus Config

| Parameter | Value | Reason |
|-----------|-------|--------|
| `min_agreeing_wallets` | 3 | Minimum independent signals |
| `min_agreement_pct` | 0.60 | 60% consensus threshold |
| `signal_ttl_minutes` | 30 | 30min freshness window |

---

## Security Notes

- ✅ All wallet data is **public** (on-chain leaderboard)
- ✅ Script only **reads** from Hyperliquid API (no write access)
- ✅ No API keys or secrets required
- ✅ Addresses are deduplicated (clustering detection removes correlated wallets)

