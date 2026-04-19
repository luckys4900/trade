#!/usr/bin/env python3
"""
RSI Swing v6 徹底分析 + v7 改善版バックテスト
プロ目線での戦略評価・改善提案
"""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\cursor\trade')

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
from rsi_swing_trader_v6 import RSIMomentumSwing, ema_ind, rsi_ind, atr_ind, macd_ind

# ============================================================
# DATA LOAD
# ============================================================
df = pd.read_csv(r'C:\Users\user\Desktop\cursor\trade\btc_usdt_4h_1500d.csv',
                 parse_dates=['timestamp'], index_col='timestamp')
df = df[['Open','High','Low','Close','Volume']]
df = df[~df.index.duplicated(keep='last')].sort_index()

# データを3分割: 訓練(60%) / 検証(20%) / テスト(20%)
n = len(df)
train_end = int(n * 0.6)
val_end = int(n * 0.8)

df_train = df.iloc[:train_end]
df_val   = df.iloc[train_end:val_end]
df_test  = df.iloc[val_end:]

print(f"Total data: {n} bars ({df.index[0].date()} → {df.index[-1].date()})")
print(f"  Train: {len(df_train)} bars ({df_train.index[0].date()} → {df_train.index[-1].date()})")
print(f"  Val  : {len(df_val)} bars ({df_val.index[0].date()} → {df_val.index[-1].date()})")
print(f"  Test : {len(df_test)} bars ({df_test.index[0].date()} → {df_test.index[-1].date()})")

# ============================================================
# PHASE 1: v6 ベースライン評価（全期間）
# ============================================================
print("\n" + "="*80)
print("  PHASE 1: RSI Swing v6 ベースライン評価（全期間）")
print("="*80)

bt_all = Backtest(df, RSIMomentumSwing, cash=1_000_000, commission=0.0005,
                  margin=0.05, trade_on_close=False)

# 最適化パラメータ（前回判明）
print("\n--- v6 Optimized (SL=1.5, TP=6.0, RSI=14, EMA OFF) ---")
s_v6 = bt_all.run(sl_atr=1.5, tp_atr=6.0, rsi_period=14, use_ema=False)
print(f"  Return: {s_v6.get('Return [%]',0):+.2f}% | PF: {s_v6.get('Profit Factor',0):.2f} | "
      f"WR: {s_v6.get('Win Rate [%]',0):.1f}% | DD: {s_v6.get('Max. Drawdown [%]',0):.2f}% | "
      f"Trades: {s_v6.get('# Trades',0)}")

# ============================================================
# PHASE 2: Walk-Forward Analysis
# ============================================================
print("\n" + "="*80)
print("  PHASE 2: Walk-Forward Analysis（訓練→検証→テスト）")
print("="*80)

# 訓練データでパラメータ最適化
print("\n[Step 1] 訓練データでパラメータ最適化...")
bt_train = Backtest(df_train, RSIMomentumSwing, cash=1_000_000, commission=0.0005, margin=0.05)

best_score, best_params = 0, {}
for sl in [1.0, 1.5, 2.0, 2.5]:
    for tp in [2.0, 3.0, 4.0, 5.0, 6.0]:
        for rp in [7, 10, 14, 21]:
            for ue in [True, False]:
                for mb in [10, 15, 20, 30]:
                    try:
                        s = bt_train.run(sl_atr=sl, tp_atr=tp, rsi_period=rp, use_ema=ue, max_bars=mb)
                        nt = s.get('# Trades', 0)
                        if nt >= 5:
                            pf = s.get('Profit Factor', 0) or 0
                            if np.isnan(pf): pf = 0
                            wr = s.get('Win Rate [%]', 0)
                            dd = s.get('Max. Drawdown [%]', 0)
                            sc = pf * min(wr/50, 1.5) * max(1 - dd/50, 0.3)
                            if sc > best_score:
                                best_score = sc
                                best_params = {'sl_atr':sl, 'tp_atr':tp, 'rsi_period':rp, 'use_ema':ue, 'max_bars':mb}
                    except:
                        pass

print(f"  Best params (train): {best_params} (Score={best_score:.2f})")

# 検証データでオーバーフィットチェック
print("\n[Step 2] 検証データでオーバーフィットチェック...")
bt_val = Backtest(df_val, RSIMomentumSwing, cash=1_000_000, commission=0.0005, margin=0.05)
s_val = bt_val.run(**best_params)
print(f"  Val  Return: {s_val.get('Return [%]',0):+.2f}% | PF: {s_val.get('Profit Factor',0):.2f} | "
      f"WR: {s_val.get('Win Rate [%]',0):.1f}% | DD: {s_val.get('Max. Drawdown [%]',0):.2f}% | "
      f"Trades: {s_val.get('# Trades',0)}")

# テストデータで最終評価
print("\n[Step 3] テストデータ（未知の期間）で最終評価...")
bt_test = Backtest(df_test, RSIMomentumSwing, cash=1_000_000, commission=0.0005, margin=0.05)
s_test = bt_test.run(**best_params)
print(f"  Test Return: {s_test.get('Return [%]',0):+.2f}% | PF: {s_test.get('Profit Factor',0):.2f} | "
      f"WR: {s_test.get('Win Rate [%]',0):.1f}% | DD: {s_test.get('Max. Drawdown [%]',0):.2f}% | "
      f"Trades: {s_test.get('# Trades',0)}")

# ============================================================
# PHASE 3: 改善版 v7 パラメータセット比較
# ============================================================
print("\n" + "="*80)
print("  PHASE 3: 改善版パラメータ比較（テスト期間）")
print("="*80)

configs = {
    "v6 Optimized (baseline)": {'sl_atr':1.5, 'tp_atr':6.0, 'rsi_period':14, 'use_ema':False, 'max_bars':20},
    "Conservative (SL広め)":   {'sl_atr':2.5, 'tp_atr':5.0, 'rsi_period':14, 'use_ema':False, 'max_bars':30},
    "Aggressive (TP長め)":     {'sl_atr':1.5, 'tp_atr':8.0, 'rsi_period':10, 'use_ema':False, 'max_bars':30},
    "EMA Filter ON":           {'sl_atr':2.0, 'tp_atr':4.0, 'rsi_period':14, 'use_ema':True,  'max_bars':20},
    "RSI Short Period":        {'sl_atr':2.0, 'tp_atr':5.0, 'rsi_period':7,  'use_ema':False, 'max_bars':15},
    "Balanced":                {'sl_atr':2.0, 'tp_atr':5.0, 'rsi_period':14, 'use_ema':False, 'max_bars':20},
}

print(f"\n  {'Config':<30s} | {'Ret%':>8} {'PF':>6} {'WR%':>6} {'DD%':>7} {'N':>4} {'Sharpe':>7}")
print(f"  {'-'*75}")

for name, params in configs.items():
    try:
        s = bt_test.run(**params)
        nt = s.get('# Trades', 0)
        ret = s.get('Return [%]', 0)
        pf = s.get('Profit Factor', 0) or 0
        wr = s.get('Win Rate [%]', 0)
        dd = s.get('Max. Drawdown [%]', 0)
        sh = s.get('Sharpe Ratio', 0) or 0
        if np.isnan(pf): pf = 0
        if np.isnan(sh): sh = 0
        print(f"  {name:<30s} | {ret:>+7.2f}% {pf:>5.2f} {wr:>5.1f}% {dd:>6.2f}% {nt:>4} {sh:>6.2f}")
    except Exception as e:
        print(f"  {name:<30s} | ERROR: {e}")

# ============================================================
# PHASE 4: 市場レジーム別分析
# ============================================================
print("\n" + "="*80)
print("  PHASE 4: 市場レジーム別パフォーマンス分析")
print("="*80)

# 年別パフォーマンス
for year in [2022, 2023, 2024, 2025, 2026]:
    df_y = df[(df.index.year == year)]
    if len(df_y) < 100:
        continue
    bt_y = Backtest(df_y, RSIMomentumSwing, cash=1_000_000, commission=0.0005, margin=0.05)
    try:
        s_y = bt_y.run(**best_params)
        nt = s_y.get('# Trades', 0)
        ret = s_y.get('Return [%]', 0)
        pf = s_y.get('Profit Factor', 0) or 0
        wr = s_y.get('Win Rate [%]', 0)
        dd = s_y.get('Max. Drawdown [%]', 0)
        if np.isnan(pf): pf = 0
        # 市場環境判定
        yr_ret = (df_y['Close'].iloc[-1] / df_y['Close'].iloc[0] - 1) * 100
        if yr_ret > 20: regime = "BULL"
        elif yr_ret < -20: regime = "BEAR"
        else: regime = "RANGE"
        print(f"  {year} ({regime:>5}, BTC {yr_ret:>+6.1f}%): Ret {ret:>+6.2f}% | PF {pf:.2f} | WR {wr:.1f}% | DD {dd:.2f}% | {nt} trades")
    except:
        pass

# ============================================================
# PHASE 5: プロ目線での分析レポート
# ============================================================
print("\n" + "="*80)
print("  PHASE 5: 総合評価レポート")
print("="*80)

# 最良の設定で詳細分析
best_config_name = "Balanced"
best_config = configs[best_config_name]
s_final = bt_test.run(**best_config)

nt = s_final.get('# Trades', 0)
ret = s_final.get('Return [%]', 0)
pf = s_final.get('Profit Factor', 0) or 0
wr = s_final.get('Win Rate [%]', 0)
dd = s_final.get('Max. Drawdown [%]', 0)
avg_trade = s_final.get('Avg. Trade [%]', 0)
exp = s_final.get('Expectancy [%]', 0)
sh = s_final.get('Sharpe Ratio', 0) or 0
sqn = s_final.get('SQN', 0) or 0

print(f"""
{'='*70}
  RSI SWING STRATEGY - FINAL EVALUATION (Test Period)
{'='*70}
  Configuration    : {best_config}
  Period           : {df_test.index[0].date()} → {df_test.index[-1].date()}
{'-'*70}
  Return           : {ret:+.2f}%
  Profit Factor    : {pf:.2f}
  Win Rate         : {wr:.1f}%
  Avg Trade        : {avg_trade:+.3f}%
  Expectancy       : {exp:+.3f}%
  Sharpe Ratio     : {sh:.2f}
  SQN              : {sqn:.2f}
  Max Drawdown     : {dd:.2f}%
  Total Trades     : {nt}
{'='*70}
  EVALUATION:
""")

# プロ目線での評価基準
checks = []
checks.append(("PF > 1.3", pf > 1.3, f"{pf:.2f}"))
checks.append(("WR > 40%", wr > 40, f"{wr:.1f}%"))
checks.append(("DD < 20%", dd < 20, f"{dd:.2f}%"))
checks.append(("Sharpe > 0.5", sh > 0.5, f"{sh:.2f}"))
checks.append(("SQN > 1.5", sqn > 1.5, f"{sqn:.2f}"))
checks.append(("Trades >= 20", nt >= 20, f"{nt}"))
checks.append(("Exp > 0", exp > 0, f"{exp:+.3f}%"))

passed = sum(1 for _,ok,_ in checks if ok)
for name, ok, val in checks:
    print(f"  {'✅' if ok else '❌'} {name}: {val}")

print(f"\n  Score: {passed}/{len(checks)}")
if passed >= 6:
    print("  >>> PRODUCTION READY <<<")
elif passed >= 4:
    print("  >>> CONDITIONAL - 要改善 <<<")
else:
    print("  >>> NOT RECOMMENDED <<<")
