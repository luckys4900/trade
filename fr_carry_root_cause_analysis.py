"""
FR Carry Trade - 赤字の根本原因分析
====================================

バックテスト結果が全て負の理由を徹底分析
- 平均FRの算出確認
- 資金調達料 vs 手数料の比較
- データの実際の値確認
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "/Users/user/Desktop/trade/data"

print("=" * 120)
print("FR Carry Trade - 赤字の根本原因分析")
print("=" * 120)

# ============================================================
# データロード
# ============================================================
print("\n【1. データの実態確認】")

fr_df = pd.read_csv(f"{DATA_DIR}/btc_funding_rate.csv")
fr_df['datetime'] = pd.to_datetime(fr_df['datetime'])
fr_df = fr_df.set_index('datetime').sort_index()

print(f"FR data: {len(fr_df)} rows, {fr_df.index[0]} to {fr_df.index[-1]}")

# Settlement times (0:00, 8:00, 16:00 UTC)
fr_df['hour'] = fr_df.index.hour
settlement_times = [0, 8, 16]
fr_settlement = fr_df[fr_df['hour'].isin(settlement_times)].copy()

print(f"\nSettlement-time FRs: {len(fr_settlement)} rows")

# ============================================================
# 統計値の詳細確認
# ============================================================
print("\n【2. 資金調達料(FR)の統計】")

fr_vals = fr_settlement['fundingRate'].values
print(f"  平均: {fr_vals.mean() * 100:.6f}%")
print(f"  中央値: {np.median(fr_vals) * 100:.6f}%")
print(f"  標準偏差: {fr_vals.std() * 100:.6f}%")
print(f"  最小値: {fr_vals.min() * 100:.6f}%")
print(f"  最大値: {fr_vals.max() * 100:.6f}%")

# Percentiles
print(f"\nPercentiles:")
for p in [5, 10, 25, 50, 75, 90, 95]:
    val = np.percentile(fr_vals, p)
    print(f"  {p}th: {val * 100:.6f}%")

# Positive FRs (Short利益)
positive_fr = fr_settlement[fr_settlement['fundingRate'] > 0]
print(f"\nPositive FRs (Short利益):")
print(f"  数: {len(positive_fr)} ({len(positive_fr)/len(fr_settlement)*100:.1f}%)")
print(f"  平均: {positive_fr['fundingRate'].mean() * 100:.6f}%")
print(f"  中央値: {positive_fr['fundingRate'].median() * 100:.6f}%")

# ============================================================
# 期待値の理論値計算
# ============================================================
print("\n【3. 理論的な期待値計算】")

TAKER_FEE = 0.00035
SLIPPAGE = 0.00050
ROUND_TRIP_COST = 2 * (TAKER_FEE + SLIPPAGE)

print(f"\nコスト構造:")
print(f"  Taker fee (both sides): {TAKER_FEE*100:.4f}% × 2 = {TAKER_FEE*2*100:.4f}%")
print(f"  Slippage (both sides): {SLIPPAGE*100:.4f}% × 2 = {SLIPPAGE*2*100:.4f}%")
print(f"  Total round-trip cost: {ROUND_TRIP_COST*100:.4f}%")

# 24時間でのFR獲得 (3回: 0:00, 8:00, 16:00 UTC)
fr_periods_per_day = 3
fr_per_24h_baseline = positive_fr['fundingRate'].mean() * fr_periods_per_day

print(f"\n24時間保有時の資金調達料獲得:")
print(f"  1期間あたりの平均FR: {positive_fr['fundingRate'].mean() * 100:.6f}%")
print(f"  1日3期間 × 平均FR: {fr_per_24h_baseline * 100:.6f}%")
print(f"  手数料: {ROUND_TRIP_COST*100:.4f}%")
print(f"  理論値: {(fr_per_24h_baseline - ROUND_TRIP_COST) * 100:.6f}%")

# ============================================================
# 実際のトレード分析
# ============================================================
print("\n【4. 実際のバックテストトレード分析】")

# Price dataロード
price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
price_df['datetime'] = pd.to_datetime(price_df['datetime'], utc=True)
price_df['datetime'] = price_df['datetime'].dt.tz_localize(None)
price_df = price_df.set_index('datetime').sort_index()

print(f"Price data: {len(price_df)} rows, {price_df.index[0]} to {price_df.index[-1]}")

# Simple backtest
def run_detailed_backtest(fr_data, price_data, threshold=0.00005, hold_bars=6):
    """Detailed backtest with debugging"""
    trades = []

    for settle_time, row in fr_data.iterrows():
        fr_val = row['fundingRate']

        if fr_val <= threshold:
            continue

        entry_time = settle_time
        future_prices = price_data[price_data.index >= entry_time]
        if len(future_prices) == 0:
            continue

        entry_idx = future_prices.index[0]
        entry_price = future_prices.loc[entry_idx, 'close']
        entry_bar_pos = price_data.index.get_loc(entry_idx)

        exit_bar_pos = entry_bar_pos + hold_bars
        if exit_bar_pos >= len(price_data):
            continue

        exit_idx = price_data.index[exit_bar_pos]
        exit_price = price_data.loc[exit_idx, 'close']

        # Price P&L (Short)
        price_pnl_pct = (entry_price - exit_price) / entry_price * 100

        # Funding P&L
        # 8時間ごとに3回受け取る
        funding_pnl_pct = fr_val * 100  # 最初の期間分

        # Net P&L
        net_pnl_pct = price_pnl_pct + funding_pnl_pct - (ROUND_TRIP_COST * 100)

        trades.append({
            'entry_time': entry_time,
            'exit_time': exit_idx,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'fr': fr_val,
            'funding_pnl_pct': funding_pnl_pct,
            'price_pnl_pct': price_pnl_pct,
            'cost_pct': ROUND_TRIP_COST * 100,
            'net_pnl_pct': net_pnl_pct,
        })

    return pd.DataFrame(trades)

trades = run_detailed_backtest(fr_settlement, price_df, threshold=0.00005, hold_bars=6)

if len(trades) > 0:
    print(f"\nTrade analysis (threshold=0.005%, hold=24h):")
    print(f"  Total trades: {len(trades)}")
    print(f"\nFunding P&L:")
    print(f"  Mean: {trades['funding_pnl_pct'].mean():.6f}%")
    print(f"  Median: {trades['funding_pnl_pct'].median():.6f}%")
    print(f"\nPrice P&L (adverse movement):")
    print(f"  Mean: {trades['price_pnl_pct'].mean():.6f}%")
    print(f"  Median: {trades['price_pnl_pct'].median():.6f}%")
    print(f"\nCost (fixed):")
    print(f"  Per trade: {trades['cost_pct'].mean():.6f}%")
    print(f"\nNet P&L:")
    print(f"  Mean: {trades['net_pnl_pct'].mean():.6f}%")
    print(f"  Std: {trades['net_pnl_pct'].std():.6f}%")
    print(f"  Min: {trades['net_pnl_pct'].min():.6f}%")
    print(f"  Max: {trades['net_pnl_pct'].max():.6f}%")
    print(f"  Win rate: {(trades['net_pnl_pct'] > 0).sum() / len(trades) * 100:.1f}%")

    # Detailed breakdown
    print(f"\n【5. P&L分解】")
    print(f"\n期待値 = 資金調達料 + 価格変動 - 手数料")
    print(f"      = {trades['funding_pnl_pct'].mean():.6f}% + {trades['price_pnl_pct'].mean():.6f}% - {ROUND_TRIP_COST*100:.6f}%")
    print(f"      = {trades['net_pnl_pct'].mean():.6f}%")

    # The key issue
    print(f"\n【6. 問題の根本原因】")
    print(f"\n資金調達料 ({trades['funding_pnl_pct'].mean():.6f}%) では手数料 ({ROUND_TRIP_COST*100:.6f}%) をカバーできない")
    print(f"  → 不足分: {ROUND_TRIP_COST*100 - trades['funding_pnl_pct'].mean():.6f}%")

    # What would be needed
    min_required_fr = ROUND_TRIP_COST / 3  # 3 periods over 24h, but just 1 FR value here
    print(f"\n損益分岐点:")
    print(f"  資金調達料が 0.17% 以上でも、価格変動がマイナスなら赤字")
    print(f"  実際の平均FR: {trades['funding_pnl_pct'].mean():.6f}%")
    print(f"  必要なFR (価格中立): {ROUND_TRIP_COST*100:.6f}%")
    print(f"  欠落: {ROUND_TRIP_COST*100 - trades['funding_pnl_pct'].mean():.6f}%")

# ============================================================
# 解決策の検討
# ============================================================
print("\n【7. 解決策の検討】")

print(f"""
FR Carry Tradeが赤字の理由:

1. 資金調達料が不十分 (平均 {trades['funding_pnl_pct'].mean():.6f}%)
   - 手数料 ({ROUND_TRIP_COST*100:.6f}%) をカバーできない
   - さらに価格逆行リスク ({abs(trades['price_pnl_pct'].mean()):.6f}%) もある

2. 高い手数料構造
   - Taker fee: {TAKER_FEE*100:.4f}% × 2 = {TAKER_FEE*2*100:.4f}%
   - Slippage: {SLIPPAGE*100:.4f}% × 2 = {SLIPPAGE*2*100:.4f}%
   - Total: {ROUND_TRIP_COST*100:.4f}% (想定より高い?)

3. 価格逆行による損失
   - Short時に価格が上昇 → 損失

【解決策案】

A. Makerを使う (手数料削減)
   - Maker fee: -0.0001% (リベート)
   - Impact: +0.07% per trade → プラスに!

B. より高いFRの時だけエントリー
   - 現在のFR分布を見直し
   - FR > 0.05% (0.005%) でのみエントリー

C. 複数方向でロング/ショートを両建て
   - Funding rate arbitrage
   - 価格リスク相殺

D. コインの選別
   - BTCより高いFRのアルト取引?
   - リスク/リターンの最適化

【統計的な結論】

この戦略は「現在のマーケット条件では利益が出ない」
- BTC: 平均FR {trades['funding_pnl_pct'].mean():.6f}% < Cost {ROUND_TRIP_COST*100:.6f}%
- 手数料が主な障害

推奨: 別の戦略を検討するか、Maker fee構造のブローカーを探す
""")

print("\n" + "=" * 120)
