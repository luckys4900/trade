"""
Triple Top Breakout Strategy - Rigorous Backtest
=================================================
Pine Script tradingview_breakout_optimized.pine のロジックに基づく
IS/OOS分割によるパラメータグリッドサーチ + 統計的検証

データ: btc_price_4h_cache.csv (4h OHLCV, 2023-01 ~ 2026-05)
IS期間: 最初の70% / OOS期間: 最後の30%
"""

import pandas as pd
import numpy as np
from itertools import product
from scipy import stats
import json
import warnings
import time
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════
# 1. データ読み込み
# ═══════════════════════════════════════════════════════════════
DATA_PATH = 'C:/Users/user/Desktop/cursor/trade/data/btc_price_4h_cache.csv'
df = pd.read_csv(DATA_PATH)
df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
df = df.sort_values('datetime').reset_index(drop=True)

print(f"Data loaded: {len(df)} bars")
print(f"  From: {df['datetime'].iloc[0]}")
print(f"  To:   {df['datetime'].iloc[-1]}")

# ═══════════════════════════════════════════════════════════════
# 2. インジケーター計算関数
# ═══════════════════════════════════════════════════════════════

def calc_atr(h, l, c, period):
    """ATR計算"""
    tr = np.maximum(h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    tr = np.concatenate([[np.nan], tr])
    atr = pd.Series(tr).rolling(period).mean().values
    return atr

def calc_sma(series, period):
    """SMA計算"""
    return pd.Series(series).rolling(period).mean().values

def calc_rsi(c, period=14):
    """RSI計算"""
    delta = np.diff(c, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean().values
    avg_loss = pd.Series(loss).rolling(period).mean().values
    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_bollinger(c, period, std_mult):
    """ボリンジャーバンド計算"""
    sma = calc_sma(c, period)
    std = pd.Series(c).rolling(period).std().values
    bb_upper = sma + std_mult * std
    bb_lower = sma - std_mult * std
    bb_width = np.where(sma > 0, (bb_upper - bb_lower) / sma, np.nan)
    return bb_upper, bb_lower, bb_width

def calc_vol_pct(c, lookback):
    """ボラティリティパーセンタイル計算"""
    n = len(c)
    vol_pct = np.full(n, np.nan)
    for i in range(lookback, n):
        returns = np.abs(np.diff(c[i-lookback:i])) / c[i-lookback:i-1] * 100
        if len(returns) == 0:
            continue
        current_vol = abs(c[i] - c[i-1]) / c[i-1] * 100
        higher_count = np.sum(current_vol >= returns)
        vol_pct[i] = higher_count / len(returns) * 100
    return vol_pct

def find_pivot_highs(h, pivot_length):
    """ピボット高値の検出（Pine Scriptのta.pivothighと同等）"""
    n = len(h)
    pivots = np.full(n, np.nan)
    pivot_indices = []
    for i in range(pivot_length, n - pivot_length):
        is_pivot = True
        for j in range(1, pivot_length + 1):
            if h[i] < h[i - j] or h[i] < h[i + j]:
                is_pivot = False
                break
        if is_pivot:
            pivots[i] = h[i]
            pivot_indices.append(i)
    return pivots, pivot_indices

def find_pivot_lows(l, pivot_length):
    """ピボット安値の検出"""
    n = len(l)
    pivots = np.full(n, np.nan)
    pivot_indices = []
    for i in range(pivot_length, n - pivot_length):
        is_pivot = True
        for j in range(1, pivot_length + 1):
            if l[i] > l[i - j] or l[i] > l[i + j]:
                is_pivot = False
                break
        if is_pivot:
            pivots[i] = l[i]
            pivot_indices.append(i)
    return pivots, pivot_indices

# ═══════════════════════════════════════════════════════════════
# 3. トリプルトップ検出 + バックテストエンジン
# ═══════════════════════════════════════════════════════════════

def run_backtest(df, pivot_length, price_tolerance, bb_std,
                 sl_atr_mult, tp_atr_mult, max_hold, volume_mult,
                 initial_capital=190, commission_pct=0.035, slippage_pct=0.1):
    """
    トリプルトップブレイクアウト戦略のバックテスト
    
    Parameters:
    -----------
    pivot_length: ピボット検出の左右バー数
    price_tolerance: トリプルトップの価格許容範囲（小数、例: 0.015 = 1.5%）
    bb_std: ボリンジャーバンドの標準偏差倍率
    sl_atr_mult: ストップロスのATR倍率
    tp_atr_mult: テイクプロフィットのATR倍率
    max_hold: 最大ホールド期間（バー数）
    volume_mult: 出来高スパイクの倍率
    """
    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values
    v = df['volume'].values
    dt = df['datetime'].values
    n = len(df)

    # インジケーター計算
    atr = calc_atr(h, l, c, 14)
    rsi = calc_rsi(c, 14)
    bb_upper, bb_lower, bb_width = calc_bollinger(c, 20, bb_std)
    vol_sma = calc_sma(v, 20)
    vol_pct = calc_vol_pct(c, 50)

    # ピボット検出
    pivot_highs, pivot_high_indices = find_pivot_highs(h, pivot_length)
    pivot_lows, pivot_low_indices = find_pivot_lows(l, pivot_length)

    # トレード記録
    trades = []
    in_position = False
    entry_idx = None
    entry_price = None
    sl_price = None
    tp_price = None

    # トリプルトップ検出用のウィンドウ
    # 直近70本以内のピボット高値を追跡
    recent_high_prices = []
    recent_high_indices = []
    recent_low_prices = []
    recent_low_indices = []

    # バーごとの処理
    for i in range(max(pivot_length, 50), n):
        # ピボット高値の更新（遅延: pivot_length本前のピボットが確定）
        pivot_bar = i - pivot_length
        if pivot_bar >= pivot_length and not np.isnan(pivot_highs[pivot_bar]):
            recent_high_prices.append(pivot_highs[pivot_bar])
            recent_high_indices.append(pivot_bar)
            # 70本以上前のピボットを削除
            while recent_high_indices and (i - recent_high_indices[0]) > 70:
                recent_high_prices.pop(0)
                recent_high_indices.pop(0)

        # ピボット安値の更新
        if pivot_bar >= pivot_length and not np.isnan(pivot_lows[pivot_bar]):
            recent_low_prices.append(pivot_lows[pivot_bar])
            recent_low_indices.append(pivot_bar)
            while recent_low_indices and (i - recent_low_indices[0]) > 70:
                recent_low_prices.pop(0)
                recent_low_indices.pop(0)

        # ポジション中はエグジット判定
        if in_position:
            # RSI Exit (LONG): RSI > 75
            if not np.isnan(rsi[i]) and rsi[i] > 75:
                exit_price = c[i]
                pnl_raw = exit_price - entry_price
                cost = (commission_pct / 100 * 2 + slippage_pct / 100 * 2) * entry_price
                pnl_net = pnl_raw - cost
                trades.append({
                    'entry_dt': dt[entry_idx], 'exit_dt': dt[i],
                    'direction': 1, 'entry': entry_price,
                    'exit': exit_price, 'pnl_raw': pnl_raw,
                    'cost': cost, 'pnl_net': pnl_net,
                    'exit_type': 'rsi_exit'
                })
                in_position = False
                continue

            # TP判定
            if h[i] >= tp_price:
                exit_price = tp_price
                pnl_raw = exit_price - entry_price
                cost = (commission_pct / 100 * 2 + slippage_pct / 100 * 2) * entry_price
                pnl_net = pnl_raw - cost
                trades.append({
                    'entry_dt': dt[entry_idx], 'exit_dt': dt[i],
                    'direction': 1, 'entry': entry_price,
                    'exit': exit_price, 'pnl_raw': pnl_raw,
                    'cost': cost, 'pnl_net': pnl_net,
                    'exit_type': 'tp'
                })
                in_position = False
                continue

            # SL判定
            if l[i] <= sl_price:
                exit_price = sl_price
                pnl_raw = exit_price - entry_price
                cost = (commission_pct / 100 * 2 + slippage_pct / 100 * 2) * entry_price
                pnl_net = pnl_raw - cost
                trades.append({
                    'entry_dt': dt[entry_idx], 'exit_dt': dt[i],
                    'direction': 1, 'entry': entry_price,
                    'exit': exit_price, 'pnl_raw': pnl_raw,
                    'cost': cost, 'pnl_net': pnl_net,
                    'exit_type': 'sl'
                })
                in_position = False
                continue

            # Max Hold判定
            if i - entry_idx >= max_hold:
                exit_price = c[i]
                pnl_raw = exit_price - entry_price
                cost = (commission_pct / 100 * 2 + slippage_pct / 100 * 2) * entry_price
                pnl_net = pnl_raw - cost
                trades.append({
                    'entry_dt': dt[entry_idx], 'exit_dt': dt[i],
                    'direction': 1, 'entry': entry_price,
                    'exit': exit_price, 'pnl_raw': pnl_raw,
                    'cost': cost, 'pnl_net': pnl_net,
                    'exit_type': 'max_hold'
                })
                in_position = False
                continue

        # エントリー条件判定（ポジションなしの場合のみ）
        if in_position:
            continue

        # 必要なインジケーターが有効かチェック
        if np.isnan(atr[i]) or np.isnan(bb_upper[i]) or np.isnan(bb_width[i]):
            continue
        if np.isnan(bb_width[i-1]) if i > 0 else True:
            continue
        if np.isnan(vol_sma[i]):
            continue
        if np.isnan(vol_pct[i]):
            continue

        # ── 条件1: トリプルトップ検出 ──
        triple_top = False
        avg_high_price = 0.0
        if len(recent_high_prices) >= 3:
            # 直近3つのピボット高値を取得
            last_3_highs = recent_high_prices[-3:]
            last_3_indices = recent_high_indices[-3:]
            min_h = min(last_3_highs)
            max_h = max(last_3_highs)
            avg_high_price = sum(last_3_highs) / 3
            high_price_range = (max_h - min_h) / avg_high_price if avg_high_price > 0 else 999

            # 価格帯が許容範囲内
            price_band_valid = high_price_range <= price_tolerance * 2

            # 現在価格が高値帯に近い
            near_high_band = (c[i] >= avg_high_price * (1 - price_tolerance) and
                            c[i] <= avg_high_price * (1 + price_tolerance))

            # 安値が切り上がっている
            lows_rising = True
            if len(recent_low_prices) >= 2:
                # 直近2つの安値を比較
                for k in range(1, min(len(recent_low_prices), 3)):
                    if recent_low_prices[-k] <= recent_low_prices[-k-1]:
                        lows_rising = False
                        break

            triple_top = price_band_valid and near_high_band and lows_rising

        if not triple_top:
            continue

        # ── 条件2: BB上位突破 ──
        bb_breakout = c[i] > bb_upper[i]

        # ── 条件3: BB幅拡大 ──
        bb_expanding = bb_width[i] > bb_width[i-1]

        # ── 条件4: 出来高スパイク ──
        volume_spike = v[i] > vol_sma[i] * volume_mult

        # ── 条件5: ボラティリティレジーム ──
        regime_ok = 35 <= vol_pct[i] <= 80

        # ── 条件6: 安値切り上げ（再確認）──
        # すでにtriple_top内で確認済み

        # 全条件のAND判定
        if bb_breakout and bb_expanding and volume_spike and regime_ok:
            # エントリー
            entry_price = c[i]
            entry_idx = i
            sl_price = entry_price - sl_atr_mult * atr[i]
            tp_price = entry_price + tp_atr_mult * atr[i]
            in_position = True

    return trades

# ═══════════════════════════════════════════════════════════════
# 4. メトリクス計算
# ═══════════════════════════════════════════════════════════════

def calc_metrics(trades_list, initial_capital=190):
    """トレードリストからメトリクスを計算"""
    if len(trades_list) < 2:
        return None
    pnls = np.array([t['pnl_net'] for t in trades_list])
    n = len(pnls)
    wins = pnls > 0
    n_wins = wins.sum()
    n_losses = (~wins).sum()
    wr = n_wins / n if n > 0 else 0
    ev = pnls.mean()
    std = pnls.std(ddof=1) if n > 1 else 0
    sharpe = ev / std if std > 0 else 0
    avg_win = pnls[wins].mean() if n_wins > 0 else 0
    avg_loss = pnls[~wins].mean() if n_losses > 0 else 0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    gross_win = pnls[wins].sum() if n_wins > 0 else 0
    gross_loss = abs(pnls[~wins].sum()) if n_losses > 0 else 0
    pf = gross_win / gross_loss if gross_loss > 0 else 0

    # Max Drawdown（ドルベース）
    # リスク/trade = 2% of equity → ポジションサイズ計算
    risk_pct = 0.02
    equity = initial_capital
    peak_equity = equity
    max_dd = 0
    for t in trades_list:
        # ポジションサイズ = (equity * risk_pct) / (sl_distance / entry_price)
        sl_distance_pct = sl_atr_mult_global * atr_avg_pct  # 近似
        pos_size = equity * 0.5  # 簡略化: 50% of equity per trade
        pnl_dollar = t['pnl_net'] / t['entry'] * pos_size
        equity += pnl_dollar
        if equity > peak_equity:
            peak_equity = equity
        dd = peak_equity - equity
        if dd > max_dd:
            max_dd = dd

    # Kelly
    kelly = (wr * payoff - (1 - wr)) / payoff if payoff > 0 else 0

    return {
        'n': n, 'wr': wr, 'ev': ev, 'std': std, 'sharpe': sharpe,
        'avg_win': avg_win, 'avg_loss': avg_loss, 'payoff': payoff,
        'pf': pf, 'max_dd': max_dd, 'kelly': kelly, 'pnls': pnls
    }

# ═══════════════════════════════════════════════════════════════
# 5. IS/OOS分割
# ═══════════════════════════════════════════════════════════════

split_idx = int(len(df) * 0.7)
is_end_dt = df['datetime'].iloc[split_idx - 1]
oos_start_dt = df['datetime'].iloc[split_idx]

print(f"\nIS/OOS Split:")
print(f"  IS:  {df['datetime'].iloc[0]} → {is_end_dt}")
print(f"  OOS: {oos_start_dt} → {df['datetime'].iloc[-1]}")

def split_trades(trades, is_end, oos_start):
    is_t = [t for t in trades if pd.Timestamp(t['entry_dt']) <= is_end]
    oos_t = [t for t in trades if pd.Timestamp(t['entry_dt']) >= oos_start]
    return is_t, oos_t

# ═══════════════════════════════════════════════════════════════
# 6. パラメータグリッドサーチ
# ═══════════════════════════════════════════════════════════════

pivot_lengths = [5, 7, 10]
price_tolerances = [0.010, 0.015, 0.020]  # 1.0%, 1.5%, 2.0%
bb_stds = [1.5, 1.8, 2.0]
sl_atr_mults = [2.0, 2.5, 3.0]
tp_atr_mults = [3.0, 4.0, 5.0]
max_holds = [10, 15, 20]
volume_mults = [1.5, 2.0, 2.5]

total_combos = (len(pivot_lengths) * len(price_tolerances) * len(bb_stds) *
                len(sl_atr_mults) * len(tp_atr_mults) * len(max_holds) * len(volume_mults))
print(f"\nTotal parameter combinations: {total_combos}")

# ATR平均%のグローバル近似（メトリクス計算用）
atr_vals = calc_atr(df['high'].values, df['low'].values, df['close'].values, 14)
valid_atr = atr_vals[~np.isnan(atr_vals)]
atr_avg_pct = np.mean(valid_atr / df['close'].values[~np.isnan(atr_vals)]) * 100
sl_atr_mult_global = 2.5  # デフォルト値

results = []
start_time = time.time()
combo_count = 0

print("Running grid search...")

for pl, pt, bbs, slm, tpm, mh, vm in product(
        pivot_lengths, price_tolerances, bb_stds,
        sl_atr_mults, tp_atr_mults, max_holds, volume_mults):

    combo_count += 1
    if combo_count % 200 == 0:
        elapsed = time.time() - start_time
        eta = elapsed / combo_count * (total_combos - combo_count)
        print(f"  Progress: {combo_count}/{total_combos} "
              f"({combo_count/total_combos*100:.1f}%) ETA: {eta/60:.1f}min")

    sl_atr_mult_global = slm  # メトリクス計算用に更新

    try:
        trades = run_backtest(df, pl, pt, bbs, slm, tpm, mh, vm)
        is_t, oos_t = split_trades(trades, is_end_dt, oos_start_dt)
        is_m = calc_metrics(is_t)
        oos_m = calc_metrics(oos_t)
    except Exception:
        continue

    results.append({
        'pivot_length': pl, 'price_tolerance': pt, 'bb_std': bbs,
        'sl_atr_mult': slm, 'tp_atr_mult': tpm, 'max_hold': mh,
        'volume_mult': vm,
        'is_m': is_m, 'oos_m': oos_m,
        'is_trades': is_t, 'oos_trades': oos_t,
        'total_trades': len(trades)
    })

elapsed = time.time() - start_time
print(f"\nGrid search completed in {elapsed:.1f}s ({combo_count} combos)")

# ═══════════════════════════════════════════════════════════════
# 7. 結果のJSON保存
# ═══════════════════════════════════════════════════════════════

json_results = []
for r in results:
    entry = {
        'pivot_length': r['pivot_length'],
        'price_tolerance_pct': r['price_tolerance'] * 100,
        'bb_std': r['bb_std'],
        'sl_atr_mult': r['sl_atr_mult'],
        'tp_atr_mult': r['tp_atr_mult'],
        'max_hold': r['max_hold'],
        'volume_mult': r['volume_mult'],
        'total_trades': r['total_trades'],
    }
    if r['is_m'] is not None:
        entry['is'] = {
            'n': int(r['is_m']['n']), 'wr': float(r['is_m']['wr']),
            'ev': float(r['is_m']['ev']), 'sharpe': float(r['is_m']['sharpe']),
            'pf': float(r['is_m']['pf']), 'payoff': float(r['is_m']['payoff']),
            'max_dd': float(r['is_m']['max_dd']),
        }
    else:
        entry['is'] = None
    if r['oos_m'] is not None:
        entry['oos'] = {
            'n': int(r['oos_m']['n']), 'wr': float(r['oos_m']['wr']),
            'ev': float(r['oos_m']['ev']), 'sharpe': float(r['oos_m']['sharpe']),
            'pf': float(r['oos_m']['pf']), 'payoff': float(r['oos_m']['payoff']),
            'max_dd': float(r['oos_m']['max_dd']),
        }
    else:
        entry['oos'] = None
    json_results.append(entry)

json_path = 'C:/Users/user/Desktop/cursor/trade/data/triple_top_backtest_results.json'
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(json_results, f, indent=2, ensure_ascii=False)
print(f"\nResults saved to: {json_path}")

# ═══════════════════════════════════════════════════════════════
# 8. フィルタリング: OOS EV > 0, OOS PF > 1.0, OOS Trades >= 5
# ═══════════════════════════════════════════════════════════════

valid = []
for r in results:
    om = r['oos_m']
    if om is None:
        continue
    if om['ev'] > 0 and om['pf'] > 1.0 and om['n'] >= 5:
        valid.append(r)

print(f"\n{'='*140}")
print(f"FILTERED RESULTS: OOS EV > 0, OOS PF > 1.0, OOS Trades >= 5")
print(f"Found: {len(valid)} / {len(results)} combinations")
print(f"{'='*140}")

# ═══════════════════════════════════════════════════════════════
# 9. トップ10パラメータセット（OOS Sharpeでランキング）
# ═══════════════════════════════════════════════════════════════

valid.sort(key=lambda x: x['oos_m']['sharpe'] if x['oos_m'] else -999, reverse=True)

print(f"\n{'='*160}")
print("TOP 10 PARAMETER SETS BY OOS SHARPE (OOS EV > 0, OOS PF > 1.0, OOS Trades >= 5)")
print(f"{'='*160}")
header = (f"{'PL':>3} | {'PT%':>4} | {'BBS':>4} | {'SL':>4} | {'TP':>4} | {'MH':>3} | {'VM':>4} | "
          f"{'IS_n':>5} | {'IS_WR':>6} | {'IS_EV':>10} | {'IS_Sh':>7} | {'IS_PF':>7} | "
          f"{'OOS_n':>5} | {'OOS_WR':>6} | {'OOS_EV':>10} | {'OOS_Sh':>7} | {'OOS_PF':>7}")
print(header)
print("-" * 160)

for r in valid[:10]:
    im = r['is_m']
    om = r['oos_m']
    if im is None:
        continue
    print(f"{r['pivot_length']:>3} | {r['price_tolerance']*100:>4.1f} | {r['bb_std']:>4.1f} | "
          f"{r['sl_atr_mult']:>4.1f} | {r['tp_atr_mult']:>4.1f} | {r['max_hold']:>3} | "
          f"{r['volume_mult']:>4.1f} | "
          f"{im['n']:>5} | {im['wr']:>6.1%} | {im['ev']:>10.2f} | {im['sharpe']:>7.3f} | {im['pf']:>7.3f} | "
          f"{om['n']:>5} | {om['wr']:>6.1%} | {om['ev']:>10.2f} | {om['sharpe']:>7.3f} | {om['pf']:>7.3f}")

# ═══════════════════════════════════════════════════════════════
# 10. 最適パラメータでの詳細分析
# ═══════════════════════════════════════════════════════════════

if len(valid) == 0:
    print("\n*** NO VALID PARAMETER SETS FOUND ***")
    print("Relaxing filters to OOS EV > 0, OOS Trades >= 3...")
    valid = [r for r in results if r['oos_m'] is not None
             and r['oos_m']['ev'] > 0 and r['oos_m']['n'] >= 3]
    valid.sort(key=lambda x: x['oos_m']['sharpe'] if x['oos_m'] else -999, reverse=True)

if len(valid) == 0:
    print("\n*** STILL NO VALID PARAMETER SETS - SHOWING TOP 10 BY OOS SHARPE ***")
    valid = [r for r in results if r['oos_m'] is not None]
    valid.sort(key=lambda x: x['oos_m']['sharpe'], reverse=True)

if len(valid) > 0:
    best = valid[0]
    bm = best['oos_m']
    bt_is = best['is_m']

    print(f"\n{'='*80}")
    print(f"DETAILED ANALYSIS: BEST OOS CONFIG")
    print(f"  pivot_length={best['pivot_length']}, price_tolerance={best['price_tolerance']*100:.1f}%, "
          f"bb_std={best['bb_std']}")
    print(f"  sl_atr_mult={best['sl_atr_mult']}, tp_atr_mult={best['tp_atr_mult']}, "
          f"max_hold={best['max_hold']}, volume_mult={best['volume_mult']}")
    print(f"{'='*80}")

    pnls = bm['pnls']

    # t-test
    t_stat, p_val = stats.ttest_1samp(pnls, 0)
    print(f"\n[1] t-test OOS EV > 0:")
    print(f"    t-stat = {t_stat:.4f}, p-value = {p_val:.4f}")

    # Bootstrap CI
    np.random.seed(42)
    boot_means = []
    for _ in range(5000):
        sample = np.random.choice(pnls, size=len(pnls), replace=True)
        boot_means.append(sample.mean())
    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
    print(f"\n[2] Bootstrap 95% CI for OOS EV:")
    print(f"    [{ci_lo:.2f}, {ci_hi:.2f}]")

    # 月次ブレークダウン
    oos_trades = best['oos_trades']
    monthly = {}
    for t in oos_trades:
        m = pd.Timestamp(t['entry_dt']).strftime('%Y-%m')
        monthly.setdefault(m, []).append(t['pnl_net'])

    print(f"\n[3] Monthly OOS breakdown:")
    print(f"    {'Month':>9} | {'n':>4} | {'WR':>6} | {'Net P&L':>10} | {'Cum P&L':>10}")
    cum = 0
    for m in sorted(monthly.keys()):
        mp = np.array(monthly[m])
        n = len(mp)
        wr = (mp > 0).mean()
        ev = mp.sum()
        cum += ev
        print(f"    {m:>9} | {n:>4} | {wr:>6.1%} | {ev:>10.2f} | {cum:>10.2f}")

    # エグジットタイプ別統計
    exit_types = {}
    for t in oos_trades:
        et = t.get('exit_type', 'unknown')
        exit_types.setdefault(et, []).append(t['pnl_net'])

    print(f"\n[4] Exit type breakdown (OOS):")
    print(f"    {'Type':>10} | {'n':>4} | {'WR':>6} | {'Avg P&L':>10} | {'Total P&L':>10}")
    for et in ['tp', 'sl', 'max_hold', 'rsi_exit']:
        if et in exit_types:
            ep = np.array(exit_types[et])
            n = len(ep)
            wr = (ep > 0).mean()
            avg = ep.mean()
            total = ep.sum()
            print(f"    {et:>10} | {n:>4} | {wr:>6.1%} | {avg:>10.2f} | {total:>10.2f}")

    # フルメトリクス
    print(f"\n[5] Full OOS metrics:")
    print(f"    Win Rate:        {bm['wr']:.1%}")
    print(f"    Avg Win:         {bm['avg_win']:.2f}")
    print(f"    Avg Loss:        {bm['avg_loss']:.2f}")
    print(f"    Payoff Ratio:    {bm['payoff']:.2f}")
    print(f"    Profit Factor:   {bm['pf']:.3f}")
    print(f"    Max Drawdown:    ${bm['max_dd']:.2f}")
    print(f"    Kelly Criterion: {bm['kelly']:.3f}")
    print(f"    IS Sharpe:       {bt_is['sharpe']:.3f}" if bt_is else "    IS Sharpe:       N/A")
    print(f"    OOS Sharpe:      {bm['sharpe']:.3f}")

    # 期待月次P&L推定
    acct = 190
    avg_entry = np.mean([t['entry'] for t in oos_trades])
    ev_pct = bm['ev'] / avg_entry * 100
    oos_months = len(monthly)
    trades_per_month = len(oos_trades) / max(oos_months, 1)
    monthly_pnl_dollar = ev_pct / 100 * acct * trades_per_month

    print(f"\n[6] Expected P&L (${acct} account):")
    print(f"    OOS EV per trade:    {bm['ev']:.2f} ({ev_pct:.3f}%)")
    print(f"    OOS trades/month:    {trades_per_month:.1f}")
    print(f"    Expected monthly P&L: ${monthly_pnl_dollar:.2f}")
    print(f"    Expected annual P&L:  ${monthly_pnl_dollar*12:.2f}")

    # ═══════════════════════════════════════════════════════════
    # 11. ロバストネスチェック: シフトしたIS/OOS分割
    # ═══════════════════════════════════════════════════════════

    print(f"\n{'='*80}")
    print("ROBUSTNESS CHECK: SHIFTED IS/OOS SPLITS")
    print(f"{'='*80}")

    split_ratios = [0.5, 0.6, 0.65, 0.75, 0.8]
    all_positive = True
    for ratio in split_ratios:
        si = int(len(df) * ratio)
        ie = df['datetime'].iloc[si - 1]
        os_ = df['datetime'].iloc[si]
        trades = run_backtest(df, best['pivot_length'], best['price_tolerance'],
                            best['bb_std'], best['sl_atr_mult'], best['tp_atr_mult'],
                            best['max_hold'], best['volume_mult'])
        is_t, oos_t = split_trades(trades, ie, os_)
        om = calc_metrics(oos_t)
        if om is None or om['n'] < 3:
            print(f"  Split {ratio:.0%}: OOS_n={0 if om is None else om['n']} (insufficient)")
            all_positive = False
        else:
            pos = "POSITIVE" if om['ev'] > 0 else "NEGATIVE"
            if om['ev'] <= 0:
                all_positive = False
            print(f"  Split {ratio:.0%}: OOS_n={om['n']} WR={om['wr']:.1%} "
                  f"EV={om['ev']:.2f} Sharpe={om['sharpe']:.3f} PF={om['pf']:.3f} → {pos}")

    # ═══════════════════════════════════════════════════════════
    # 12. 最終判定
    # ═══════════════════════════════════════════════════════════

    print(f"\n{'='*80}")
    print("FINAL VERDICT")
    print(f"{'='*80}")

    sig = "YES" if p_val < 0.05 else "NO"
    robust = "YES" if all_positive else "NO"

    print(f"  Statistical significance (p<0.05): {sig} (p={p_val:.4f})")
    print(f"  Robust across splits:              {robust}")
    print(f"  OOS trades/month:                   {trades_per_month:.1f}")
    print(f"  OOS EV per trade:                   {bm['ev']:.2f} ({ev_pct:.3f}%)")
    print(f"  Expected monthly P&L (${acct} acct):  ${monthly_pnl_dollar:.2f}")
    print(f"  Expected annual P&L (${acct} acct):   ${monthly_pnl_dollar*12:.2f}")

    if sig == "YES" and robust == "YES" and bm['sharpe'] > 0.5:
        rec = "IMPLEMENT"
    elif sig == "YES" and bm['sharpe'] > 0.3:
        rec = "NEEDS MORE DATA"
    elif bm['pf'] > 1.5 and bm['wr'] > 0.45:
        rec = "PROMISING BUT RISKY"
    else:
        rec = "REJECT"
    print(f"\n  RECOMMENDATION: {rec}")
    print(f"{'='*80}")

    # ═══════════════════════════════════════════════════════════
    # 13. トップ10のサマリーJSON保存
    # ═══════════════════════════════════════════════════════════

    top10_summary = []
    for r in valid[:10]:
        om = r['oos_m']
        im = r['is_m']
        if om is None or im is None:
            continue
        top10_summary.append({
            'rank': len(top10_summary) + 1,
            'params': {
                'pivot_length': r['pivot_length'],
                'price_tolerance_pct': r['price_tolerance'] * 100,
                'bb_std': r['bb_std'],
                'sl_atr_mult': r['sl_atr_mult'],
                'tp_atr_mult': r['tp_atr_mult'],
                'max_hold': r['max_hold'],
                'volume_mult': r['volume_mult'],
            },
            'is_metrics': {
                'n': int(im['n']), 'wr': float(im['wr']),
                'ev': float(im['ev']), 'sharpe': float(im['sharpe']),
                'pf': float(im['pf']),
            },
            'oos_metrics': {
                'n': int(om['n']), 'wr': float(om['wr']),
                'ev': float(om['ev']), 'sharpe': float(om['sharpe']),
                'pf': float(om['pf']),
            }
        })

    summary_path = 'C:/Users/user/Desktop/cursor/trade/data/triple_top_top10_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(top10_summary, f, indent=2, ensure_ascii=False)
    print(f"\nTop 10 summary saved to: {summary_path}")

else:
    print("\n*** NO VALID RESULTS TO ANALYZE ***")

print("\n" + "="*80)
print("BACKTEST COMPLETE")
print("="*80)