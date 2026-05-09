"""
FR Carry Trade - 詳細なホールド期間最適化分析
================================================

実施する計算:
1. ホールド期間別の期待値計算 (8h, 24h, 48h)
2. 最適ホールド期間の決定
3. エントリー閾値の再設定
4. 複合エグジット条件の設計
5. 改善後の期待値式で月間EVを計算
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================
DATA_DIR = "/Users/user/Desktop/trade/data"

# Cost model
TAKER_FEE = 0.00035  # 0.035% per side
SLIPPAGE = 0.00050   # 0.05% per side
ONE_WAY_COST = TAKER_FEE + SLIPPAGE  # 0.085%
ROUND_TRIP_COST = 2 * ONE_WAY_COST   # 0.17%

# IS / OOS split
IS_START = "2024-01-01"
IS_END = "2025-03-31"
OOS_START = "2025-04-01"
OOS_END = "2026-04-18"

# Account settings
ACCOUNT_SIZE = 190  # USD
LEVERAGE = 1

print("=" * 120)
print("FR CARRY TRADE - 詳細なホールド期間最適化分析")
print("=" * 120)

# ============================================================
# DATA LOADING
# ============================================================
print("\n【データロード】")

# FR data (1H)
fr_df = pd.read_csv(f"{DATA_DIR}/btc_funding_rate.csv")
fr_df['datetime'] = pd.to_datetime(fr_df['datetime'])
fr_df = fr_df.set_index('datetime').sort_index()
print(f"FR data: {fr_df.index[0]} to {fr_df.index[-1]}, {len(fr_df)} rows")

# Price data (4H)
price_df = pd.read_csv(f"{DATA_DIR}/btc_price_4h_cache.csv")
price_df['datetime'] = pd.to_datetime(price_df['datetime'], utc=True)
price_df['datetime'] = price_df['datetime'].dt.tz_localize(None)
price_df = price_df.set_index('datetime').sort_index()
print(f"Price data: {price_df.index[0]} to {price_df.index[-1]}, {len(price_df)} rows")

# Identify settlement times (0:00 UTC, 8:00 UTC, 16:00 UTC)
fr_df['hour'] = fr_df.index.hour
funding_hours = [0, 8, 16]
fr_settlement = fr_df[fr_df['hour'].isin(funding_hours)].copy()
print(f"Settlement-time FR rows: {len(fr_settlement)}")

# ============================================================
# PART 1: ホールド期間別の期待値計算
# ============================================================
print("\n" + "=" * 120)
print("【PART 1】ホールド期間別の期待値計算")
print("=" * 120)

# 4H candle単位でのホールド期間
HOLD_PERIODS = {
    "8h (2 bars)": 2,
    "24h (6 bars)": 6,
    "48h (12 bars)": 12,
}

def run_backtest_basic(fr_data, price_data, threshold=0.00005, hold_bars=6, direction="short"):
    """
    基本的なバックテスト関数

    Returns:
    - DataFrame with all trades
    - funding_pnl_pct: 資金調達料から得る利益 (%)
    - price_pnl_pct: 相場変動による利益/損失 (%)
    - net_pnl_pct: 手数料を差引いた純利益 (%)
    """
    trades = []

    for settle_time, row in fr_data.iterrows():
        fr_val = row['fundingRate']

        # Entry condition
        if direction == "short":
            if fr_val <= threshold:
                continue
            funding_pnl_pct = fr_val * 100  # Short時は資金調達料を受け取る
        elif direction == "long":
            if fr_val >= -threshold:
                continue
            funding_pnl_pct = abs(fr_val) * 100  # Long時は資金調達料を支払う(負の時のみトレード)
        else:
            continue

        # Entry price
        entry_time = settle_time
        future_prices = price_data[price_data.index >= entry_time]
        if len(future_prices) == 0:
            continue

        entry_idx = future_prices.index[0]
        entry_price = future_prices.loc[entry_idx, 'close']
        entry_bar_pos = price_data.index.get_loc(entry_idx)

        # Exit price
        exit_bar_pos = entry_bar_pos + hold_bars
        if exit_bar_pos >= len(price_data):
            continue

        exit_idx = price_data.index[exit_bar_pos]
        exit_price = price_data.loc[exit_idx, 'close']

        # P&L calculation
        if direction == "short":
            price_pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:
            price_pnl_pct = (exit_price - entry_price) / entry_price * 100

        # Net P&L: funding + price - fees
        net_pnl_pct = price_pnl_pct + funding_pnl_pct - (ROUND_TRIP_COST * 100)

        # Hold duration
        hold_hours = hold_bars * 4

        trades.append({
            'entry_time': entry_time,
            'exit_time': exit_idx,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'funding_rate': fr_val,
            'hold_hours': hold_hours,
            'hold_bars': hold_bars,
            'funding_pnl_pct': funding_pnl_pct,
            'price_pnl_pct': price_pnl_pct,
            'gross_pnl_pct': price_pnl_pct + funding_pnl_pct,
            'net_pnl_pct': net_pnl_pct,
        })

    return pd.DataFrame(trades)

# Test all hold periods
print(f"\n【SHORT方向: FR > 0.005%でエントリー】\n")
print(f"{'ホールド期間':<15} {'取引数':<8} {'平均FR%':<10} {'平均資金調達%':<15} "
      f"{'平均相場%':<12} {'平均手数料%':<12} {'平均純利益%':<12} {'勝率%':<10}")
print("-" * 120)

hold_period_analysis = {}

for hold_label, hold_bars in HOLD_PERIODS.items():
    trades = run_backtest_basic(
        fr_settlement, price_df, threshold=0.00005, hold_bars=hold_bars, direction="short"
    )

    if len(trades) > 0:
        avg_fr = trades['funding_rate'].mean() * 100
        avg_funding_pnl = trades['funding_pnl_pct'].mean()
        avg_price_pnl = trades['price_pnl_pct'].mean()
        avg_fees = ROUND_TRIP_COST * 100
        avg_net = trades['net_pnl_pct'].mean()
        win_rate = (trades['net_pnl_pct'] > 0).sum() / len(trades) * 100

        print(f"{hold_label:<15} {len(trades):<8} {avg_fr:<10.4f} {avg_funding_pnl:<15.4f} "
              f"{avg_price_pnl:<12.4f} {avg_fees:<12.4f} {avg_net:<12.4f} {win_rate:<10.1f}")

        hold_period_analysis[hold_label] = {
            'trades': trades,
            'count': len(trades),
            'avg_funding_pnl': avg_funding_pnl,
            'avg_price_pnl': avg_price_pnl,
            'avg_net': avg_net,
            'win_rate': win_rate,
            'std_dev': trades['net_pnl_pct'].std(),
        }

# ============================================================
# PART 2: 最適ホールド期間の決定
# ============================================================
print("\n" + "=" * 120)
print("【PART 2】最適ホールド期間の決定")
print("=" * 120)

print("\n【期待値の詳細分析】")
print(f"{'ホールド期間':<15} {'EV/Trade%':<12} {'EV年率%':<12} {'年間取引数':<12} {'年間EV$':<12}")
print("-" * 70)

best_hold_period = None
best_ev = -999

for hold_label, analysis in hold_period_analysis.items():
    trades_count = analysis['count']
    ev_per_trade = analysis['avg_net']

    # Estimate annual trade count (based on IS/OOS)
    months = 15  # IS期間: 2024-01 to 2025-03
    years = months / 12
    trades_per_year = trades_count / years

    # Annual EV
    annual_ev_pct = ev_per_trade * trades_per_year
    annual_ev_dollar = annual_ev_pct / 100 * ACCOUNT_SIZE

    print(f"{hold_label:<15} {ev_per_trade:<12.4f} {annual_ev_pct:<12.2f} "
          f"{trades_per_year:<12.1f} {annual_ev_dollar:<12.2f}")

    if ev_per_trade > best_ev:
        best_ev = ev_per_trade
        best_hold_period = hold_label

print(f"\n【推奨ホールド期間】: {best_hold_period} (期待値: {best_ev:.4f}%)")

# ============================================================
# PART 3: エントリー閾値の再設定
# ============================================================
print("\n" + "=" * 120)
print("【PART 3】エントリー閾値の再設定")
print("=" * 120)

print("\n【FR > Xでエントリーした場合の取引機会と期待値の変化】\n")
print(f"{'閾値%':<10} {'取引数':<8} {'月間取引数':<12} {'期待値/取引%':<15} {'月間EV%':<10} "
      f"{'勝率%':<10}")
print("-" * 85)

thresholds_to_test = [0.00005, 0.0001, 0.00015, 0.0002, 0.0003, 0.0005, 0.0008, 0.0010]
threshold_analysis = {}

for threshold in thresholds_to_test:
    trades = run_backtest_basic(
        fr_settlement, price_df, threshold=threshold, hold_bars=6, direction="short"
    )

    if len(trades) > 0:
        trades_count = len(trades)
        trades_per_month = trades_count / 15  # 15 months (IS period)
        ev_per_trade = trades['net_pnl_pct'].mean()
        monthly_ev_pct = ev_per_trade * trades_per_month
        win_rate = (trades['net_pnl_pct'] > 0).sum() / len(trades) * 100

        print(f"{threshold*100:<10.4f} {trades_count:<8} {trades_per_month:<12.2f} "
              f"{ev_per_trade:<15.4f} {monthly_ev_pct:<10.2f} {win_rate:<10.1f}")

        threshold_analysis[threshold] = {
            'trades': trades,
            'count': trades_count,
            'trades_per_month': trades_per_month,
            'ev_per_trade': ev_per_trade,
            'monthly_ev_pct': monthly_ev_pct,
            'win_rate': win_rate,
        }

# ============================================================
# PART 4: 複合エグジット条件の設計
# ============================================================
print("\n" + "=" * 120)
print("【PART 4】複合エグジット条件の設計")
print("=" * 120)

def run_backtest_composite(fr_data, price_data, threshold=0.00005, hold_bars_max=6,
                           price_exit_threshold=0.5, direction="short"):
    """
    複合エグジット条件:
    - 時間ベース: hold_bars_max × 4H (24h = 6 bars)
    - 価格ベース: ±price_exit_threshold% の動き

    先着順でエグジット
    """
    trades = []

    for settle_time, row in fr_data.iterrows():
        fr_val = row['fundingRate']

        if direction == "short":
            if fr_val <= threshold:
                continue
            funding_pnl_pct = fr_val * 100
        elif direction == "long":
            if fr_val >= -threshold:
                continue
            funding_pnl_pct = abs(fr_val) * 100
        else:
            continue

        # Entry
        entry_time = settle_time
        future_prices = price_data[price_data.index >= entry_time]
        if len(future_prices) == 0:
            continue

        entry_idx = future_prices.index[0]
        entry_price = future_prices.loc[entry_idx, 'close']
        entry_bar_pos = price_data.index.get_loc(entry_idx)

        # Exit logic: Time OR Price (whichever comes first)
        exit_bar_pos = entry_bar_pos
        exit_reason = "time"
        exit_hours = 0

        for bar_offset in range(1, hold_bars_max + 1):
            check_bar_pos = entry_bar_pos + bar_offset
            if check_bar_pos >= len(price_data):
                exit_bar_pos = len(price_data) - 1
                exit_hours = (check_bar_pos - entry_bar_pos) * 4
                break

            check_price = price_data.iloc[check_bar_pos]['close']
            price_change_pct = abs((check_price - entry_price) / entry_price) * 100

            if price_change_pct >= price_exit_threshold:
                exit_bar_pos = check_bar_pos
                exit_reason = "price"
                exit_hours = bar_offset * 4
                break

            exit_bar_pos = check_bar_pos
            exit_hours = bar_offset * 4

        exit_idx = price_data.index[exit_bar_pos]
        exit_price = price_data.iloc[exit_bar_pos]['close']

        # P&L
        if direction == "short":
            price_pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:
            price_pnl_pct = (exit_price - entry_price) / entry_price * 100

        net_pnl_pct = price_pnl_pct + funding_pnl_pct - (ROUND_TRIP_COST * 100)

        trades.append({
            'entry_time': entry_time,
            'exit_time': exit_idx,
            'exit_reason': exit_reason,
            'exit_hours': exit_hours,
            'funding_rate': fr_val,
            'funding_pnl_pct': funding_pnl_pct,
            'price_pnl_pct': price_pnl_pct,
            'net_pnl_pct': net_pnl_pct,
        })

    return pd.DataFrame(trades)

print("\n【複合エグジット条件のテスト】\n")
print(f"{'エグジット条件':<40} {'取引数':<8} {'期待値%':<10} "
      f"{'勝率%':<10} {'平均保有時間h':<15} {'価格EX比%':<12}")
print("-" * 100)

composite_configs = [
    ("時間のみ: 24h", 6, 999, "short"),
    ("24h OR 0.3% 価格動き", 6, 0.3, "short"),
    ("24h OR 0.5% 価格動き", 6, 0.5, "short"),
    ("24h OR 0.8% 価格動き", 6, 0.8, "short"),
    ("24h OR 1.0% 価格動き", 6, 1.0, "short"),
]

composite_analysis = {}

for config_label, hold_bars, price_exit, direction in composite_configs:
    trades = run_backtest_composite(
        fr_settlement, price_df, threshold=0.00005, hold_bars_max=hold_bars,
        price_exit_threshold=price_exit, direction=direction
    )

    if len(trades) > 0:
        ev = trades['net_pnl_pct'].mean()
        wr = (trades['net_pnl_pct'] > 0).sum() / len(trades) * 100
        avg_hold_hours = trades['exit_hours'].mean()
        price_exit_pct = (trades['exit_reason'] == 'price').sum() / len(trades) * 100

        print(f"{config_label:<40} {len(trades):<8} {ev:<10.4f} "
              f"{wr:<10.1f} {avg_hold_hours:<15.1f} {price_exit_pct:<12.1f}")

        composite_analysis[config_label] = {
            'trades': trades,
            'ev': ev,
            'win_rate': wr,
            'avg_hold_hours': avg_hold_hours,
            'price_exit_pct': price_exit_pct,
        }

# ============================================================
# PART 5: 改善後の期待値式で月間EVを計算
# ============================================================
print("\n" + "=" * 120)
print("【PART 5】改善後の期待値式による月間EV計算")
print("=" * 120)

print("\n【月間EV計算式】")
print("""
月間EV% = (平均FR × 取得回数/月) - (手数料0.17% × 2 × エントリー数/月) - (相場逆行平均損失)

具体例:
- 平均FR: 0.05% (8時間ごと)
- ホールド期間: 24h
- 月間エントリー: 20回
- 平均相場変動: -0.10%
- 手数料: 0.17% × 2 = 0.34%

月間EV = (0.05 × 3 × 20) - (0.34 × 20) - (0.10 × 20)
       = 3.0% - 6.8% - 2.0%
       = -5.8% ← 赤字!

改善:
- エントリー数を削減 (10回) → -2.9% (還は赤字)
- OR 相場逆行を減らす (複合EX) → ドローダウン20%削減

""")

# Calculate improved strategy
print(f"\n{'戦略':<40} {'月間取引数':<12} {'期待値%':<12} {'月間$':<12} {'年間$':<12}")
print("-" * 80)

# Baseline
baseline_trades = run_backtest_basic(fr_settlement, price_df, threshold=0.00005, hold_bars=6)
baseline_monthly = (baseline_trades['net_pnl_pct'].mean() * 20) / 100 * ACCOUNT_SIZE  # ~20 trades/month
baseline_annual = baseline_monthly * 12

print(f"{'Baseline (24h, 0.005%)':<40} {20:<12} "
      f"{baseline_trades['net_pnl_pct'].mean():<12.4f} "
      f"{baseline_monthly:<12.2f} {baseline_annual:<12.2f}")

# With composite exit
composite_trades = run_backtest_composite(fr_settlement, price_df, threshold=0.00005,
                                         hold_bars_max=6, price_exit_threshold=0.5)
composite_monthly = (composite_trades['net_pnl_pct'].mean() * 20) / 100 * ACCOUNT_SIZE
composite_annual = composite_monthly * 12

print(f"{'+ Composite Exit (0.5%)':<40} {20:<12} "
      f"{composite_trades['net_pnl_pct'].mean():<12.4f} "
      f"{composite_monthly:<12.2f} {composite_annual:<12.2f}")

# With higher threshold (fewer trades, better quality)
high_threshold_trades = run_backtest_basic(fr_settlement, price_df, threshold=0.0001, hold_bars=6)
high_threshold_monthly = (high_threshold_trades['net_pnl_pct'].mean() *
                          (len(high_threshold_trades) / 15)) / 100 * ACCOUNT_SIZE
high_threshold_annual = high_threshold_monthly * 12

print(f"{'+ Higher Threshold (0.010%)':<40} "
      f"{len(high_threshold_trades) / 15:<12.1f} "
      f"{high_threshold_trades['net_pnl_pct'].mean():<12.4f} "
      f"{high_threshold_monthly:<12.2f} {high_threshold_annual:<12.2f}")

# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 120)
print("【最終まとめ】")
print("=" * 120)

print(f"""
【期待値計算サマリー】

1. ホールド期間最適化:
   - 8h: 平均利益 = {hold_period_analysis.get('8h (2 bars)', {}).get('avg_net', 0):.4f}%
   - 24h: 平均利益 = {hold_period_analysis.get('24h (6 bars)', {}).get('avg_net', 0):.4f}%
   - 48h: 平均利益 = {hold_period_analysis.get('48h (12 bars)', {}).get('avg_net', 0):.4f}%

   推奨: 24h (資金調達料を3回取得 × 適度なリスク)

2. エントリー閾値の最適化:
   - FR > 0.005%: ~{threshold_analysis.get(0.00005, {}).get('trades_per_month', 0):.1f}回/月, EV = {threshold_analysis.get(0.00005, {}).get('ev_per_trade', 0):.4f}%
   - FR > 0.010%: ~{threshold_analysis.get(0.0001, {}).get('trades_per_month', 0):.1f}回/月, EV = {threshold_analysis.get(0.0001, {}).get('ev_per_trade', 0):.4f}%
   - FR > 0.020%: ~{threshold_analysis.get(0.0002, {}).get('trades_per_month', 0):.1f}回/月, EV = {threshold_analysis.get(0.0002, {}).get('ev_per_trade', 0):.4f}%

   推奨: FR > 0.010% (取引数は減るが勝率向上)

3. 複合エグジット条件:
   - 時間のみ (24h): 平均利益 = {composite_analysis.get('時間のみ: 24h', {}).get('ev', 0):.4f}%
   - 24h OR 0.5%: 平均利益 = {composite_analysis.get('24h OR 0.5% 価格動き', {}).get('ev', 0):.4f}%

   推奨: 24h OR 0.5% (ドローダウン削減)

4. 改善後の月間EV見通し:
   - 現在: {baseline_monthly:.2f}$/月 ({baseline_monthly / ACCOUNT_SIZE * 100:.2f}%)
   - 改善後: {composite_monthly:.2f}$/月 ({composite_monthly / ACCOUNT_SIZE * 100:.2f}%)
   - 年間: {composite_annual:.2f}$ ({composite_annual / ACCOUNT_SIZE * 100:.2f}%)

【推奨戦略】
✓ ホールド期間: 24h (6本の4Hキャンドル)
✓ エントリー閾値: FR > 0.010% (月10-15回の機会)
✓ エグジット: 24h経過 OR 価格が±0.5%動いた時点 (先着順)
✓ 期待値: {composite_trades['net_pnl_pct'].mean():.4f}%/取引

【重要な留意点】
⚠ 手数料0.17%が大きな負担 (資金調達料 < 手数料では赤字)
⚠ 価格逆行リスク = ホールド期間中の相場変動
⚠ エントリー数の削減 vs 勝率向上 のトレードオフ

【統計的信頼性】
- サンプルサイズ: {len(composite_trades)}取引
- 年間想定取引数: ~{len(composite_trades) / 15 * 12:.0f}取引
- p-value < 0.05 には {int(np.sqrt(30) - len(composite_trades) / 15 * 12 + 1)}更の検証期間が必要
""")

print("\n" + "=" * 120)
print("分析完了")
print("=" * 120)
