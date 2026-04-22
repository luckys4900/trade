# Changelog

## 2026-04-22

### P0 Critical Fixes
- Fixed alpha-score NaN handling via `compute_alpha_score()` to return neutral `50.0`.
- Fixed gap prediction missing-driver behavior:
  - Missing `N225_change` now returns `UNAVAILABLE` and `gap_pct=None`.
  - Added CME proxy fallback (`predict_gap_with_proxy`, `fetch_cme_nikkei_overnight_change`).
- Fixed G0 scenario contradiction:
  - Added `generate_g0_scenario()` with dynamic TP downgrade by gap-fill probability.
  - Prevents impossible `gap_fill_prob=0%` with full gap-fill TP.

### P1 Macro Integrity Improvements
- Added event calendar integration (`modules/event_calendar.py`) with:
  - 2026-04-22 Iran truce deadline CRITICAL event.
  - 2802 earnings pre-window handling.
- Added sector classifier (`modules/sector_classifier.py`) to keep 2802 as defensive food and suppress SOX when correlation is low.
- Added 9-box sentiment regime mapping (`modules/regime.py`) including `BULL_FADING`.
- Added real-time proxy fetch layer (`fetch_realtime_proxies`) for CME Nikkei/WTI/USDJPY in pre-open window.

### P2 Operational Quality
- Added hold-vs-cut section guard (`compute_hold_vs_cut_ev`) to skip when no position exists.
- Added backtest quality gate (`apply_backtest_quality_gate`) to enforce `PAPER_TRADE_ONLY` and `max_size_pct<=10` on invalid backtests.
- Added data freshness enforcement (`enforce_data_freshness`) with `LIMITED_REPORT` fallback path in runner.

### Integration
- Refactored `run_jpx_backtest.py` to consume modular integrity components.
- Updated `run.bat` launcher to pass regime inputs (`macro_sentiment`, `news_bias`) and optional freshness timestamp.
- Added regression test suite: `tests/test_2026_04_22_regression.py`.

## 2026-04-22 (v3.0 audit response)

### P0 Implemented
- Added `modules/data_provenance.py` and forced `Data Provenance` block at report head.
- Added synthetic watermark handling (`# SYNTHETIC`) for non-trustworthy source.
- Added executive summary as top H1 section right after provenance block.
- Added gap audit trail rendering (`GapPredictionBreakdown.render`) with mismatch marker (`⚠️矛盾`).
- Added strict missing primary driver behavior (`UNAVAILABLE / gap_pct=None`) and preserved NaN alpha neutralization.

### P1 Implemented
- Added environment score verification block near top with weighted formula visibility.
- Added fixed action discipline block tied to action bias and event timestamps.
- Added earnings proximity block with pre-drift warning and ATR expansion linkage.
- Added scenario eligibility matrix + gap class fill statistics.

### P2 Implemented
- Connected hold/cut EV section with CLI params (`--position-entry`, `--position-shares`, `--position-side`).
- Added macro cross dashboard (CME/WTI/BRENT/USDJPY/VIX/GOLD with timestamps and freshness).
- Added backtest scope disclaimer clarifying timeframe mismatch risks.

### Regression Coverage
- Added `tests/test_regression_20260422.py` for audit regressions.
- Kept compatibility with existing `tests/test_2026_04_22_regression.py` checks.
- Added CLI compatibility flags for path/debug verification: `--verbose`, `--no-cache`, `--dump-config`.

### Reflection of Prior Request
- Prior unresolved items reflected in this iteration: **10 / 10 core audit requirements**.

