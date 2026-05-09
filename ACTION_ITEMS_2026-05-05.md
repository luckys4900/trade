# Action Items - Remote Sync Follow-Up
**Generated**: 2026-05-05  
**Status**: 5 strategy implementations found and documented

---

## 🔴 CRITICAL ITEMS (Do Today)

### 1. **Fix Path Issues** (Blocks backtest execution)
```bash
# Current problem: Scripts have Windows paths
# C:\Users\user\Desktop\cursor\trade\data  (Windows path in 4 files)

Files to fix:
  ✗ data/fr_carry_rigorous_backtest.py (line 19)
  ✗ data/fr_rigorous_backtest.py (line 44, 49)
  ✗ data/inside_bar_btc_rigorous_bt.py (line 9)
  ✗ data/pairs_trading_rigorous_backtest.py (line 21, 22)

Solution: Change to relative path or use os.path expansion
```

### 2. **Verify Dependencies**
```bash
python3 -c "import statsmodels; import scipy; print('OK')"
# If fails: pip install statsmodels scipy
```

### 3. **Run Backtests** (Collect actual results)
```bash
# Test each in sequence to see output:
python3 data/fr_carry_rigorous_backtest.py
python3 data/fr_rigorous_backtest.py
python3 data/inside_bar_btc_rigorous_bt.py
python3 data/pairs_trading_rigorous_backtest.py
```

---

## 🟡 MEDIUM PRIORITY (This Week)

### 4. **Reconcile Expected Value Claims**
| Strategy | Your Spec Claim | Actual Implementation | Status |
|----------|---|---|---|
| FR-ARB | +0.40% entry, -1.0% SL | Rigorous 2yr backtest | PENDING RESULTS |
| LIQ-REV | +0.95% TP, +0.35% EV | No matching impl | MISSING |
| FR MR | None proposed | Full implementation | PENDING RESULTS |
| Pairs | None proposed | Full implementation | PENDING RESULTS |
| Inside Bar | None proposed | Full implementation | PENDING RESULTS |

**Action**: After running backtests, determine which matches your goals

### 5. **Understand Daily SMA Bot Status**
- **File**: SYSTEM/daily_sma_trader.py
- **Status**: Ready to trade (independent from whale system)
- **Check**: Has it been started? Where's the state file?
- **Action**: `ls -la daily_sma_state.json logs/daily_sma_*.log`

### 6. **Update Repository Documentation**
```bash
□ Update HYPERLIQUID_FR_LIQ_STRATEGY_BACKTEST_SPEC.md with:
  - Actual backtest results
  - Statistical significance findings
  - Which strategies passed validation
  - Expected monthly P&L (not theoretical)
□ Add results section to CLAUDE.md
□ Archive this analysis report
```

---

## 🟢 LOWER PRIORITY (Next Sprint)

### 7. **Integrate Strategy Selection**
After validation results, decide:
- [ ] Which strategies to run live?
- [ ] Should daily_sma_trader.py stay independent?
- [ ] Should it coordinate with qwen_unified_live.py?
- [ ] What's the capital allocation per strategy?

### 8. **Monitor Live Trading**
- Daily SMA bot: Track state daily
- Pairs trading: Requires cointegration stability
- FR strategies: Monitor funding rate regime

---

## 📊 QUICK REFERENCE: What Each Strategy Does

| Name | Entry Signal | Exit Signal | Time Horizon | Risk |
|------|---|---|---|---|
| **FR Carry** | FR extreme (>0.3%) | Time-based (8-16h) | Hours | 0.17% cost |
| **FR Z-Score** | Z-score deviation | Mean reversion or time | Hours | 0.17% cost |
| **Inside Bar** | Breakout from inside bar | ATR SL/TP | Minutes-Hours | Variable |
| **Pairs** | Spread Z-score | Mean reversion or time | Hours-Days | 0.34% cost (4 sides) |
| **Daily SMA** | EMA crossover | Opposite cross/trail | Days | 2% risk per trade |

---

## ⚠️ IMPORTANT CONSTRAINTS

1. **All are Hyperliquid-exclusive** (as per your requirement)
2. **$190 account size** assumed in backtests
3. **Cost models**: Assume 0.035% taker + 0.05% slippage
4. **IS/OOS validation**: All use proper train/test split
5. **Statistical rigor**: All require p<0.05 or clear robustness for "IMPLEMENT"

---

## 🎯 SUCCESS CRITERIA

Strategy can be **live-traded** when:
- ✓ OOS EV > 0 (positive out-of-sample)
- ✓ p-value < 0.05 (statistically significant) OR robust across parameters
- ✓ Kelly criterion suggests positive sizing
- ✓ Max drawdown is acceptable
- ✓ Monthly P&L estimate > 0.5% of account

---

## 📝 NEXT REPORT

After running backtests, provide:
1. **Results Table**: All strategies with OOS metrics
2. **Verdict Summary**: Which pass validation?
3. **Expected Monthly P&L**: For $190 account
4. **Implementation Roadmap**: Which to trade first?

---

**Prepared by**: Claude Code  
**For**: Strategy Validation & Live Trading Decision

