# Strategy EV Analysis Memory (2026-04-15)

## Purpose
This memo captures the recent BTC strategy research flow, verified backtest results, and the implementation decisions already applied to the live bot. Any future LLM analysis should read this file before proposing new strategy changes.

## Scope Covered
- Review of current `OCPM`, `RangeMR`, `RSISwing`, and `Contrarian`
- Re-evaluation of `Contrarian` expectancy with fresh runs
- Comparison of regime filters, timeframe changes, entry timing, and EV optimization ideas
- Live implementation decisions chosen from the highest-value evidence

## Files To Read First
1. `memory/strategy_ev_analysis_2026-04-15.md`
2. `PROJECT_STATUS.md`
3. `SYSTEM/qwen_unified_live.py`
4. `test_contrarian_integration.py`
5. `START/MASTER_LAUNCHER.bat`

## Ground Truth Principles
- Prefer fresh backtests over old terminal summaries or hand-written estimates.
- BTC strategy quality improved when trades were filtered, not when trade count was expanded.
- For this project, raising expectancy by removing low-quality entries is preferred over adding many similar strategies.
- Backtest claims should be supported by explicit metrics: expectancy, PF, MDD, trade count, and rough monthly trade frequency.

## Key Research Findings

### 1. Contrarian Was Not Strong Enough As-Is
- Older saved reports showed weak or mixed edge.
- Fresh recalculation showed the strategy can be positive, but results vary because Kronos prediction uses sampling.
- Conclusion: `Contrarian` should not run in all BTC regimes. It needs gating.

### 2. Contrarian Mid-Volatility Gate Improved Quality
Fresh BTC 4h full-period comparison:
- `base_contrarian`: Return `+19.49%`, PF `1.138`, WR `49.385%`, MDD `12.738%`, Expectancy `+0.1143`, Trades `569`
- `contrarian_mid_vol`: Return `+25.894%`, PF `1.198`, WR `50.82%`, MDD `11.968%`, Expectancy `+0.1681`, Trades `427`
- `contrarian_trend`: Return `-11.246%`, PF `0.991`, WR `45.248%`, MDD `28.794%`, Expectancy `-0.0071`, Trades `484`

Interpretation:
- Mid-volatility filtering helped.
- Trend-filtering `Contrarian` made it worse.
- Live implementation chosen: allow `Contrarian` only when `35 <= vol_pct <= 80`.

### 3. Legacy EV Improved More By Filtering And Exit Quality Than By More Entries
`ev_optimization_backtest.py` fresh results:
- Baseline: EV `+0.239`, PF `1.19`, Trades `63`
- Tighter trailing stops: EV `+0.539`, PF `1.57`, Trades `63`
- Trend + Confluence + Dynamic: EV `+0.892`, PF `1.69`, Trades `45`
- Enhanced EV: EV `+0.742`, PF `1.61`, Trades `43`

Interpretation:
- Exit quality matters a lot.
- Better filtering improved per-trade quality even with fewer trades.

### 4. Timeframe Expansion Did Not Beat 4h Core
`timeframe_comparison.py` fresh results:
- `4h only`: PF `1.31`, PnL `$6.89`, DD `8.5%`, Sharpe `0.32`
- `1h only`: PF `1.11`, PnL `$2.29`, DD `14.6%`, Sharpe `0.09`
- `4h trend + 1h entry`: PF `1.28`, PnL `$4.98`, DD `10.1%`, Sharpe `0.22`
- `1h tight SL/TP`: PF `0.59`, PnL `-$8.44`, DD `13.9%`, Sharpe `-0.72`

Interpretation:
- The system should remain 4h-first for BTC.
- Lower-timeframe expansion increased noise more than edge.

### 5. Entry Timing Favored Immediate 4h Confirmation
`entry_timing_comparison.py` fresh results:
- `Wait (Open Entry)`: PF `1.19`, PnL `$4.13`, Sharpe `0.20`
- `Don't Wait (Close Entry)`: PF `1.31`, PnL `$6.89`, Sharpe `0.32`

Interpretation:
- Current direct 4h close-based behavior is better than waiting one more bar.

### 6. Hard Regime Filtering Helped Legacy Quality
Fresh hard-regime backtest on `OCPM + RangeMR`:
- Baseline: Return `+1.596%`, Expectancy `+$0.0435`, PF `1.0973`, MDD `8.794%`, Trades `63`
- Strict hard regime: Return `+3.125%`, Expectancy `+$0.1906`, PF `1.6528`, MDD `4.475%`, Trades `18`

Interpretation:
- Strong regime filtering improved quality but reduced frequency too much.

### 7. Best Balance Was Hard OCPM Only
Relaxed variants:
- `strict_hard_regime`: Expectancy `+$0.1906`, PF `1.6528`, Trades/month `0.74`
- `relax_ema200_for_ocpm`: Expectancy `+$0.0914`, PF `1.2707`, Trades/month `0.823`
- `relax_mr_only`: Expectancy `+$0.2489`, PF `2.08`, Trades/month `0.946`
- `hard_ocpm_only`: Expectancy `+$0.1048`, PF `1.3233`, MDD `4.228%`, Trades `32`, Trades/month `1.316`

Interpretation:
- `relax_mr_only` had the best raw expectancy, but still fewer than 1 trade/month.
- `hard_ocpm_only` was selected as the best balance between trade frequency and quality.

## Live Implementation Decisions Already Applied

### Decision A: Contrarian Mid-Volatility Gate
Implemented in `SYSTEM/qwen_unified_live.py`
- Added `vol_pct`
- Added config:
  - `contrarian_vol_filter_enabled = True`
  - `contrarian_min_vol_pct = 35.0`
  - `contrarian_max_vol_pct = 80.0`

### Decision B: OCPM Hard Regime Only
Implemented in `SYSTEM/qwen_unified_live.py`
- Added config:
  - `ocpm_hard_regime_enabled = True`
  - `ocpm_ema_regime_period = 200`
- OCPM only allowed when:
  - LONG: `close > EMA55 > EMA200`, `EMA21 > EMA55`, `EMA21 slope > 0`
  - SHORT: inverse
- `RangeMR` left unchanged for live operation

### Decision C: Launcher Path Is Ready
`START/MASTER_LAUNCHER.bat` launches `SYSTEM/qwen_unified_live.py`, so restarting from the launcher uses the new logic.

## Tests Already Added
`test_contrarian_integration.py`
- verifies `vol_pct` exists
- verifies `Contrarian` is blocked outside the volatility gate
- verifies `Contrarian` can still open inside the gate
- verifies OCPM hard-regime columns exist
- verifies OCPM is blocked when hard regime fails
- verifies OCPM proceeds when hard regime passes

Fresh verification already completed:
- `pytest test_contrarian_integration.py`
- `python -m py_compile SYSTEM/qwen_unified_live.py test_contrarian_integration.py`
- `cmd /c "echo 0| .\\START\\MASTER_LAUNCHER.bat"`

## What Future Analysis Should Focus On
Priority order:
1. Improve exit quality for `Legacy` strategies
2. Add derivatives-aware filters to `Contrarian`:
   - funding
   - open interest
   - basis
3. Test session and weekday filters for BTC
4. Run walk-forward validation by sub-period
5. Revisit capital allocation after more live data

## What Future Analysis Should Avoid
- Do not assume more strategies automatically improve monthly return.
- Do not prefer lower-timeframe expansion without strong evidence.
- Do not trust old terminal summaries over fresh reruns.
- Do not add RSI/EMA variants that duplicate existing price logic without accessing a different BTC market structure.

## Recommended Starting Prompt For Another LLM
Before doing any new strategy analysis, read:
- `memory/strategy_ev_analysis_2026-04-15.md`
- `PROJECT_STATUS.md`
- `SYSTEM/qwen_unified_live.py`

Then answer:
- What has already been tested?
- What is already live?
- Which unimplemented idea has the highest expected value per engineering effort?
- What should be tested next without duplicating prior work?
