# Whale-Following Copy-Trading Bot Project

**Status**: ✓ Complete Implementation (as of 2026-04-10)

## Quick Start

```
Double-click these shortcuts in this folder:
  01_START.lnk     → Start all systems
  03_STATUS.lnk    → Check status anytime
  04_STOP.lnk      → Stop systems
```

## System Architecture

### Three Parallel Systems

1. **Whale Monitor** (15-min cycle)
   - File: `whale_monitor.py`
   - Output: `whale_signal.json`
   - Monitors 3 active Hyperliquid traders

2. **Macro Filter** (60-min cycle)
   - File: `macro_filter.py`
   - Output: `macro_state.json`
   - Tracks volatility & economic events

3. **Main Bot** (1-min cycle)
   - File: `qwen_unified_live.py`
   - Reads both signal files
   - Position size: 0.5x to 1.5x base

### Data Flow

```
whale_monitor → whale_signal.json
macro_filter → macro_state.json
                    ↓
            qwen_unified_live.py
                    ↓
        trade_alignment_log.json
            (30-day validation)
```

## Configuration

**File**: `whale_wallets.json`

Three monitored wallets:
- `0x863b676e5e4fea...` ($270k AUM)
- `0x932bdd2d5e2147...` ($648k AUM)
- `0x523852be2db1a7...` ($517k AUM)

Current settings optimized for initial discovery:
- `min_sortino`: -2.0 (will relax to 2.0 in production)
- `min_win_rate`: 0.0 (will raise to 0.50)
- `min_agreeing_wallets`: 1 (will raise to 3)

## Expected Behavior

### Signal Generation

- **Valid signal**: 1+ wallets holding BTC position
- **Direction**: LONG or SHORT (from whale consensus)
- **Strength**: (agreeing_count / total_wallets) × (avg_sortino / cap)
- **Update**: Every 15 minutes (whale_monitor), every 60 min (macro)

### Trade Multiplier

Position size = base_size × multiplier, where:

```
multiplier = 1.0 (default)

If whale_signal valid:
  + 0.5 × strength (max +0.5)
  Result: 1.0 to 1.5x

If macro_state = EXTREME:
  → Skip entry entirely (0.0)

If macro_state = NORMAL:
  - 0.5x penalty (0.5x min)
```

## 30-Day Validation Plan

Files: `trade_alignment_log.json` + `validate_whale_alpha.py`

After 30 days:
- Compare aligned (whale_signal match) vs unaligned returns
- If alpha > 0.3% → Continue with threshold tuning
- If alpha ≤ 0.3% → Disable whale system (bot continues)

## Key Implementation Details

### Sortino Calculation (FIXED)

Previously: sqrt(252/100) = 1.587 constant (WRONG)
Now: sqrt(actual_trades_per_year) using real fill history

### Outcome Backfill (FIXED)

_close_strat() now calls _backfill_alignment_outcome():
- Writes entry_px, exit_px, outcome to log
- Enables 30-day EV measurement

### Min Win Rate (FIXED)

score_wallets() now enforces min_win_rate parameter

### Consensus Voting (RELAXED)

For initial discovery: 1 wallet sufficient
Production: will require 3+ wallets, 60% agreement

## File Management

### Input Files
- `whale_wallets.json` - monitored wallet list
- `whale_signal.json` - latest whale signal (15-min)
- `macro_state.json` - latest macro state (60-min)

### Output Files
- `logs/whale_monitor_*.log` - whale system logs
- `logs/macro_filter_*.log` - volatility logs
- `logs/unified_live_*.log` - main bot logs
- `logs/startup_errors.log` - error tracking
- `whale_ranking_cache.json` - wallet performance cache (24h)
- `trade_alignment_log.json` - 30-day validation data

### Backup Files
- `whale_wallets_backups/` - weekly refreshes archived

## Production Readiness Checklist

- [x] All three systems operational
- [x] Signal generation working
- [x] Outcome backfill implemented
- [x] 30-day validation structure ready
- [x] Launcher shortcuts created (non-console closing)
- [ ] 30 days of live trading data
- [ ] Alpha validation passed (> 0.3%)
- [ ] Threshold parameters tuned

## Troubleshooting

### No signals generated
→ Check `whale_signal.json` timestamp (should be < 30 min old)
→ Run `03_STATUS.lnk` to verify whale_monitor running

### No whale_signal.json
→ whale_monitor may not have generated yet (first run takes 15 min)
→ Check `logs/whale_monitor_*.log` for errors

### Processes keep stopping
→ Check `logs/startup_errors.log`
→ Verify Python executable is installed and in PATH
→ Run `04_STOP.lnk` then `01_START.lnk` to restart

## Development Notes

**Language**: Japanese-compatible Python (UTF-8, chcp 65001)
**API**: Hyperliquid mainnet only
**Risk**: Paper trade first if unsure
**Account**: $211 balance (testnet equivalent)

## Next Session

When switching models:
1. Check `memory/MEMORY.md`
2. Check `memory/strategy_ev_analysis_2026-04-15.md`
3. Check `memory/implementation_whale_system.md`
4. This `CLAUDE.md` contains operational guide
5. Run `03_STATUS.lnk` to verify system state
6. Review `STRATEGY_ANALYSIS_HANDOFF_PROMPT.md` before new strategy research

---

## Tools Integration (2026-04-16)

### 1. LightRAG - Strategy Dependency Analysis
- **Status**: ✓ Installed and configured
- **File**: `tools_lightrag_setup.py`
- **Output**: `lightrag_dependency_graph.json`
- **Usage**: Analyze dependencies between trading strategies
- **Update Frequency**: Monthly when strategies change

### 2. Awesome Claude Code - Best Practices Guide
- **Status**: ✓ Guide created
- **File**: `memory/AWESOME_CLAUDE_CODE_GUIDE.md`
- **Key Skills**: brainstorming, writing-plans, systematic-debugging, test-driven-development
- **Usage**: Reference when starting new development

### 3. Everything Claude Code - Security Audit
- **Status**: ✓ Security scanning enabled
- **Files**: 
  - `tools_security_audit.py` (scanner)
  - `SECURITY_AUDIT_REPORT.md` (latest report)
  - `security_audit_issues.json` (structured data)
- **Last Scan**: 2026-04-16
- **Result**: 0 HIGH, 3 MEDIUM, 0 LOW risks
- **Frequency**: Run before each production deployment

## Tools Usage Checklist

Before any development:
- [ ] Review `memory/AWESOME_CLAUDE_CODE_GUIDE.md`
- [ ] Use superpowers:brainstorming for new features
- [ ] Use superpowers:writing-plans for multi-step tasks
- [ ] Use superpowers:systematic-debugging for bugs

Before production deployment:
- [ ] Run `python3 tools_security_audit.py`
- [ ] Review SECURITY_AUDIT_REPORT.md
- [ ] Fix all HIGH and MEDIUM risks
- [ ] Run `03_STATUS.lnk` verification
