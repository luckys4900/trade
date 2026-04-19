# RSM-D Proxy Validation Report

## Summary

This report validates the proposed `RSM-D` strategy using the data already present in this repository, plus locally reproducible derived signals.

Bottom line:

- The original claim is **not confirmed** in this workspace.
- A reproducible proxy backtest on the available altcoin universe produced **negative expectancy**.
- Therefore, the statement "`RSM-D` has clearly positive EV" is **not supported** by the evidence available here.

## Data Inventory

Backtest script:

- `scripts/rsm_d_proxy_backtest.py`

Generated outputs:

- `backtest_results/rsm_d_proxy_results.json`
- `backtest_results/rsm_d_proxy_trades.csv`
- `backtest_results/rsm_d_data_inventory.csv`
- `backtest_results/rsm_d_regime_daily.csv`

Usable local universe:

- `AAVE`, `ACE`, `ADA`, `AIXBT`, `APE`, `APT`, `AR`, `ARB`, `DOGE`, `ETH`, `LINK`, `PEPE`, `SOL`, `SUI`, `WIF`

Common usable period:

- `2024-04-05 08:00:00` to `2025-09-30 20:00:00`

Important gaps versus the original claim:

1. There is **no point-in-time top-30 market-cap history** in the repo.
2. There is **no native BTC dominance history** in the repo.
3. There is **no native total crypto market-cap history** in the repo.
4. Funding history is only partially available from Binance futures for the local symbol set.

## Reproduction Spec

Because the original data was not fully available, the following proxy rules were used.

### Universe

- Fixed local universe from `data/*_USDT_4h_730d.csv`
- No survivorship-safe dynamic top-30 rebuild was possible
- Manual sector map was applied for:
  - `layer1`, `layer2`, `meme`, `ai`, `defi`, `gaming`, `oracle`, `infra`, `nft`

### Regime Proxy

Original claim:

- `BTC.D < SMA20`
- `BTC.D SMA20 < SMA50`
- `Total crypto market cap > SMA200`

Local reproducible proxy used instead:

- Build an equal-weight normalized alt index from the local 15-coin universe
- Compute `btc_relative_proxy = normalized BTC / normalized alt_index`
- Regime is ON when:
  - `btc_relative_proxy < SMA20`
  - `SMA20 < SMA50`
  - `BTC daily close > SMA200`

This is a proxy for "BTC losing relative strength to alts inside a bull market".

### Entry Rules

- Timeframe: `4h`
- Long-only
- Signal evaluated on bar close
- Entry executed on next `4h` bar open
- Conditions:
  1. 14-day relative strength in top 20% of currently valid symbols
  2. `RSI(14) >= 54`
  3. `close > EMA21`
  4. `volume > SMA20(volume) * 1.75`
  5. `Supertrend(10, 3)` direction is up

### Exit Rules

- Initial stop: wider of recent swing-low distance and `2.8 * ATR(14)`
- Trail activated after `+18%`
- Optional 50% scale-out at `+28%`, then Supertrend trail on the remainder
- Time stop: `21 days = 126 bars`

### Risk Rules

- Starting capital: `$100,000`
- Risk per trade: `0.8%`
- Max concurrent positions: `6`
- Sector concentration limit: max `2` live positions per sector

### Costs

- Commission: `0.045%` round-trip (`0.0225%` per side)
- Funding:
  - Pulled from Binance USDM when available
  - Missing symbols fall back to zero funding cost

## Measured Results

Proxy backtest result:

| Metric | Result |
|---|---:|
| Start Equity | $100,000 |
| Final Equity | $97,770 |
| Total Return | -2.23% |
| CAGR | -1.50% |
| Max Drawdown | -8.76% |
| Sharpe | -0.15 |
| Calmar | -0.17 |
| Trades | 33 |
| Win Rate | 30.3% |
| Avg Win | +19.74% |
| Avg Loss | -13.24% |
| Expectancy | -3.24% per trade |
| Profit Factor | 0.66 |
| Monthly Win Rate | 11.8% |

Regime-on trades:

- Trades: `33`
- Win rate: `30.3%`
- Expectancy: `-3.24%`

The strategy did **not** produce positive EV under the reproducible proxy setup.

## Trade Breakdown

Best symbols by net PnL:

- `ARB`: `+1455.87`
- `DOGE`: `+1145.14`
- `WIF`: `+654.21`

Weakest symbols by net PnL:

- `LINK`: `-1425.10`
- `ADA`: `-1358.74`
- `SUI`: `-1100.65`
- `PEPE`: `-1013.56`

Monthly clustering:

- Best month: `2025-05`
- Weak months: `2024-12`, `2025-06`, `2025-07`, `2025-09`

The observed edge was **narrow and episodic**, not broad and persistent.

## Professional Assessment

The original numbers claimed:

- `1,964` trades
- `56.8%` win rate
- `+4.71%` expectancy
- `2.81` profit factor
- `94.6%` CAGR

The reproducible result here is dramatically different:

- `33` trades
- `30.3%` win rate
- `-3.24%` expectancy
- `0.66` profit factor
- `-1.50%` CAGR

That gap is too large to dismiss as noise. From a professional research perspective, at least one of the following must be true:

1. The claimed backtest used a materially different universe.
2. The claimed backtest used a materially different regime definition.
3. The original test likely benefited from selection bias, survivorship bias, or undocumented filters.
4. The exact implementation details behind the claim were not fully disclosed.

## Verdict

Using the evidence that can be reproduced in this repository:

- `RSM-D` is **not validated as a positive-EV strategy**
- The original performance claim is **not reproducible here**
- The current best professional conclusion is:

**"The claimed edge is unproven, and the locally reproducible proxy test is negative."**

## Next Step Required For Full Validation

To test the claim properly, the following must be added:

1. Point-in-time daily top-30 market-cap constituents
2. Exact `BTC.D` historical series
3. Exact total crypto market-cap historical series
4. Exact perp funding history for the traded symbols
5. The original sector taxonomy and inclusion rules

Without those inputs, a strong statement like "expectancy is clearly positive" is not justified.
