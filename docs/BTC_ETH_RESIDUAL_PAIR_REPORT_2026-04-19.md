# BTC/ETH Residual Pair Report

## Tested Strategy

Core hypothesis tested:

- `BTC/ETH perp`
- `1h` bars
- rolling beta residual mean reversion
- next-bar-open execution
- fees, slippage, and funding included
- walk-forward optimization with out-of-sample evaluation

Implementation:

- `scripts/btc_eth_residual_pair_backtest.py`

Artifacts:

- `backtest_results/btc_eth_residual_pair_results.json`
- `backtest_results/btc_eth_residual_pair_oos_trades.csv`

## Test Setup

- Period: `2023-01-01` to `2026-04-19`
- Venue: `Binance USDT-M perpetuals`
- Symbols: `BTC/USDT:USDT`, `ETH/USDT:USDT`
- Initial capital: `$100,000`
- Risk per trade: `0.8%`
- Max gross leverage: `2.0x`
- Fees: `0.04%`
- Slippage: `0.02%`
- Correlation filter: `corr(BTC, ETH) >= 0.60`

Parameter grid:

- beta window: `72, 168`
- z window: `48, 72, 96`
- z entry: `1.5, 2.0, 2.5`
- z exit: `0.0, 0.5`
- z stop: `3.0, 3.5, 4.0`
- max hold: `12, 24, 48h`

## OOS Results

Combined out-of-sample:

| Metric | Value |
|---|---:|
| Trades | 324 |
| Return | -5.04% |
| Final equity | 94,961.30 |
| Win rate | 41.98% |
| Profit factor | 0.621 |
| Sharpe | -0.31 |
| Max drawdown | -3.15% |
| t-stat | -1.453 |
| p-value | 0.1471 |

Walk-forward splits:

| Split | OOS PF | OOS Return | OOS Trades |
|---|---:|---:|---:|
| 2 | 0.580 | -2.30% | 90 |
| 3 | 0.742 | -1.01% | 42 |
| 4 | 0.698 | -0.61% | 81 |
| 5 | 0.405 | -1.12% | 111 |

## Adoption Decision

Adoption checks:

- FAIL: `OOS PF > 1.20`
- PASS: `OOS trades >= 80`
- FAIL: `OOS Sharpe > 1`
- PASS: `Max DD < 15%`
- FAIL: `t-test significant`
- FAIL: `Majority of OOS splits PF > 1`

Final decision:

**Do not adopt.**

## Interpretation

The core residual-mean-reversion alpha did not survive out-of-sample testing.

Important observations:

1. All OOS splits were negative.
2. The strategy generated enough trades, so this is not just a tiny-sample issue.
3. Drawdown stayed small, but that came from weak edge and modest sizing, not from a robust alpha.
4. The strategy appears to fit in-sample reasonably well, then degrades immediately OOS, which is a classic sign that the residual rule alone is not stable enough.

## Practical Conclusion

If this idea is pursued further, it should **not** be deployed as a core strategy in its current form.

The next valid research step would be:

1. keep this residual framework as the baseline,
2. add a separate event-study layer for `funding / OI / flow`,
3. prove that the gate improves OOS PF materially above `1.0`,
4. only then reconsider deployment.
