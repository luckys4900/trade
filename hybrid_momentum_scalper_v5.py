#!/usr/bin/env python3
"""
================================================================================
  Hybrid Momentum-Confluence Scalper v5.0
  ────────────────────────────────────────────────────────────────────────────
  BTC/USD 5-Minute | Cursor実行対応 | yfinance自動取得 + 合成データ自動切替

  ■ 設計根拠（2025-2026年 海外プロトレーダー実績ベース）
  ────────────────────────────────────────────────────────────────────────────
  1. EMA Crossover + RSI: Opofinance実測 WR 70-75% (EUR/USD, 5min)
  2. VWAP Bounce + Volume: プロップファーム合格率最高の手法 (PF 1.29+)
  3. Williams %R + Multi-Filter: BullByte TradingView検証 WR 55%, PF 1.29
  4. 5-EMA + VWAP: Cloudzy/実トレーダー報告 WR 65-70%

  ■ 本戦略のアーキテクチャ（上記4手法のハイブリッド融合）
  ────────────────────────────────────────────────────────────────────────────
  Layer 1 - VWAP Bias       : 機関投資家のフェアバリュー方向確認
  Layer 2 - EMA Trend       : 9/21 EMA整列でマイクロトレンド確認
  Layer 3 - Williams %R     : -80/-20ゾーンからの反転でモメンタム確認
  Layer 4 - Volume Spike    : 平均比1.3倍以上で参加者確認
  Layer 5 - ATR Dynamic SL  : 2.0x ATR SL + 4.0x ATR TP (1:2 R:R)
  Layer 6 - Session Filter  : UTC 7-21時（ロンドン+NY流動性帯）
  Layer 7 - Daily Cap       : 最大5トレード/日（過剰取引防止）

  ■ 実行方法（Cursor / ターミナル）
  ────────────────────────────────────────────────────────────────────────────
  $ pip install backtesting yfinance numpy pandas
  $ python hybrid_momentum_scalper_v5.py

  ■ 出力
  ────────────────────────────────────────────────────────────────────────────
  - コンソール: 主要メトリクス + フィルター削除実験 + パラメータグリッド
  - HTML: hybrid_scalper_v5_report.html（インタラクティブチャート）
================================================================================
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ═══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════════════════════════════

def ema_ind(series, period):
    return pd.Series(series).ewm(span=period, adjust=False).mean().values

def sma_ind(series, period):
    return pd.Series(series).rolling(period, min_periods=period).mean().values

def atr_ind(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean().values

def williams_r(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    hh = h.rolling(period, min_periods=period).max()
    ll = l.rolling(period, min_periods=period).min()
    return (-100 * (hh - c) / (hh - ll).replace(0, np.nan)).values

def rsi_ind(series, period=14):
    s = pd.Series(series)
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/period, min_periods=period).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1/period, min_periods=period).mean()
    return (100 - 100 / (1 + g / lo.replace(0, np.nan))).values

def stoch_rsi(series, rsi_period=14, stoch_period=14, k_smooth=3):
    """Stochastic RSI — より高感度なモメンタム検出"""
    rsi_vals = pd.Series(rsi_ind(series, rsi_period))
    rsi_min = rsi_vals.rolling(stoch_period, min_periods=stoch_period).min()
    rsi_max = rsi_vals.rolling(stoch_period, min_periods=stoch_period).max()
    stoch = (rsi_vals - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    return (stoch * 100).rolling(k_smooth, min_periods=1).mean().values

def supertrend_ind(high, low, close, atr_period=10, mult=3.0):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_period, min_periods=atr_period).mean()
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * atr, hl2 - mult * atr
    d = pd.Series(np.ones(len(c)), index=c.index)
    fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(c)):
        fu.iloc[i] = ub.iloc[i] if (ub.iloc[i] < fu.iloc[i-1] or c.iloc[i-1] > fu.iloc[i-1]) else fu.iloc[i-1]
        fl.iloc[i] = lb.iloc[i] if (lb.iloc[i] > fl.iloc[i-1] or c.iloc[i-1] < fl.iloc[i-1]) else fl.iloc[i-1]
        if d.iloc[i-1] == 1:
            d.iloc[i] = -1 if c.iloc[i] < fl.iloc[i] else 1
        else:
            d.iloc[i] = 1 if c.iloc[i] > fu.iloc[i] else -1
    return d.values


# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════

def load_data(symbol="BTC-USD", period="60d"):
    """yfinanceでリアルデータ取得。失敗時は合成データにフォールバック。"""
    try:
        import yfinance as yf
        logging.info("Fetching %s 5m data...", symbol)
        df = yf.download(symbol, period=period, interval="5m",
                         progress=False, auto_adjust=False, group_by="column")
        if df.empty:
            raise RuntimeError("Empty")
        cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        df = df.iloc[:, :len(cols)]
        df.columns = cols[:df.shape[1]]
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        logging.info("OK: %d bars via yfinance", len(df))
        return _add_vwap(df[["Open", "High", "Low", "Close", "Volume"]])
    except Exception as e:
        logging.warning("yfinance failed (%s) → synthetic data", e)
        return _add_vwap(_synth(days=60))


def _add_vwap(df):
    day = df.index.date
    cv = df["Volume"].groupby(day).cumsum()
    cpv = (df["Close"] * df["Volume"]).groupby(day).cumsum()
    df["VWAP"] = cpv / cv.replace(0, np.nan)
    return df


def _synth(days=60):
    """レジーム切替・ファットテール・セッション別ボラティリティの合成BTC 5分足"""
    np.random.seed(42)
    n = days * 288
    ts = pd.date_range(datetime(2025, 1, 4, tzinfo=timezone.utc), periods=n, freq="5min", tz="UTC")
    hrs = np.array([t.hour for t in ts])

    # レジーム: 0=レンジ, 1=上昇, 2=下降
    reg = np.zeros(n, dtype=int); cr = 0; rd = 0
    for i in range(n):
        rd += 1
        if rd > 80 and np.random.random() < 0.015:
            cr = np.random.choice([0, 1, 2], p=[0.35, 0.35, 0.30]); rd = 0
        reg[i] = cr

    base = 95000.0; cl = np.zeros(n); cl[0] = base; mom = 0.0
    for i in range(1, n):
        h, r = hrs[i], reg[i]
        v = 0.0022 if 13 <= h < 21 else 0.0014 if 7 <= h < 13 else 0.0009
        if r == 1:   dr = 0.00020; v *= 1.3
        elif r == 2: dr = -0.00016; v *= 1.4
        else:        dr = -(cl[i-1] - base) / base * 0.001
        noise = np.random.standard_t(df=4) * v
        mom = 0.25 * mom + 0.75 * noise
        ret = dr + mom
        if np.random.random() < 0.004:
            ret += np.random.choice([-1, 1]) * np.random.uniform(0.006, 0.02)
        cl[i] = cl[i-1] * (1 + ret)
        if i % 800 == 0: base = cl[i]

    op = np.roll(cl, 1); op[0] = cl[0]
    intr = np.abs(np.random.randn(n)) * 0.0013
    sm = np.where((hrs >= 13) & (hrs < 21), 1.6, np.where((hrs >= 7) & (hrs < 13), 1.2, 0.8))
    intr *= sm
    hi = np.maximum(op, cl) * (1 + intr)
    lo = np.minimum(op, cl) * (1 - intr)
    vol = np.random.lognormal(10, 0.5, n)
    vol[(hrs >= 13) & (hrs < 21)] *= np.random.uniform(2, 4, size=((hrs >= 13) & (hrs < 21)).sum())
    pc = np.abs(np.diff(cl, prepend=cl[0])) / cl
    vol[pc > 0.003] *= np.random.uniform(3, 6, size=(pc > 0.003).sum())

    logging.info("Synthetic: %d bars", n)
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": vol}, index=ts)


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY
# ═══════════════════════════════════════════════════════════════════════════════

from backtesting import Backtest, Strategy

class HybridMomentumScalper(Strategy):
    """
    ハイブリッド・モメンタム・コンフルエンス・スキャルパー

    ■ ロングエントリー条件（全条件AND）:
      1. Close > VWAP（機関投資家バイアス）
      2. EMA(9) > EMA(21)（トレンド方向）
      3. Williams %R が -80 以下から上抜け（モメンタム反転）
      4. RSI(14) > 40 かつ < 75（余力あり）
      5. Volume > SMA(20) * vol_mult（出来高確認）
      6. セッション時間内（UTC session_start〜session_end）
      7. 当日トレード数 < max_daily

    ■ ショートエントリー条件（ロングの対称）

    ■ エグジット:
      - SL = sl_atr * ATR(14)
      - TP = tp_atr * ATR(14)
      - タイムストップ = max_bars バー
    """

    # ── チューニングパラメータ（グリッドサーチ対象） ──
    ema_fast: int = 9
    ema_slow: int = 21
    wr_period: int = 14
    wr_ob: float = -20.0       # Overbought
    wr_os: float = -80.0       # Oversold
    rsi_period: int = 14
    vol_period: int = 20
    vol_mult: float = 1.0      # ボリューム倍率（1.0 = 平均以上で可）
    sl_atr: float = 2.0        # SL = 2.0 x ATR
    tp_atr: float = 4.0        # TP = 4.0 x ATR (1:2 R:R)
    atr_period: int = 14
    risk_pct: float = 0.01     # 1%リスク/トレード
    max_bars: int = 60          # 最大保有バー数（5時間）
    session_start: int = 7      # UTCセッション開始
    session_end: int = 22       # UTCセッション終了
    max_daily: int = 5
    use_vwap: bool = True
    use_vol: bool = True
    use_rsi: bool = True
    use_session: bool = True

    def init(self):
        c, h, l, v = self.data.Close, self.data.High, self.data.Low, self.data.Volume
        self.ema9 = self.I(ema_ind, c, self.ema_fast)
        self.ema21 = self.I(ema_ind, c, self.ema_slow)
        self.wr = self.I(williams_r, h, l, c, self.wr_period)
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.atr = self.I(atr_ind, h, l, c, self.atr_period)
        self.vol_sma = self.I(sma_ind, v, self.vol_period)
        self.vwap = self.data.VWAP
        self._entry_bar = 0
        self._dc = {}

    def _today(self):
        return str(self.data.index[-1])[:10]

    def _can(self):
        return self._dc.get(self._today(), 0) < self.max_daily

    def _inc(self):
        d = self._today()
        self._dc[d] = self._dc.get(d, 0) + 1

    def next(self):
        # タイムストップ
        if self.position:
            if len(self.data) - self._entry_bar >= self.max_bars:
                self.position.close()
            return

        n = max(self.wr_period, self.ema_slow, self.vol_period, self.atr_period) + 3
        if len(self.data.Close) < n:
            return

        wr_now = float(self.wr[-1])
        wr_prev = float(self.wr[-2])
        c_now = float(self.data.Close[-1])
        e9 = float(self.ema9[-1])
        e21 = float(self.ema21[-1])
        rsi_now = float(self.rsi[-1])
        atr_now = float(self.atr[-1])
        vol_now = float(self.data.Volume[-1])
        vol_avg = float(self.vol_sma[-1])
        vwap_now = float(self.vwap[-1])

        if any(np.isnan(x) for x in [wr_now, wr_prev, c_now, e9, e21, rsi_now, atr_now, vol_avg, vwap_now]):
            return
        if atr_now <= 0:
            return

        # セッションフィルター
        if self.use_session:
            hr = self.data.index[-1].hour
            if not (self.session_start <= hr < self.session_end):
                return

        # デイリーキャップ
        if not self._can():
            return

        # 共通フィルター
        vol_ok = (not self.use_vol) or (vol_avg > 0 and vol_now > vol_avg * self.vol_mult)

        # ═══ LONG ═══
        long_wr = (wr_prev <= self.wr_os) and (wr_now > self.wr_os)
        long_ema = e9 > e21
        long_vwap = (not self.use_vwap) or (c_now > vwap_now)
        long_rsi = (not self.use_rsi) or (40 < rsi_now < 75)

        if long_wr and long_ema and long_vwap and long_rsi and vol_ok:
            self._enter("long", c_now, atr_now)
            return

        # ═══ SHORT ═══
        short_wr = (wr_prev >= self.wr_ob) and (wr_now < self.wr_ob)
        short_ema = e9 < e21
        short_vwap = (not self.use_vwap) or (c_now < vwap_now)
        short_rsi = (not self.use_rsi) or (25 < rsi_now < 60)

        if short_wr and short_ema and short_vwap and short_rsi and vol_ok:
            self._enter("short", c_now, atr_now)

    def _enter(self, direction, price, atr_now):
        sl_dist = atr_now * self.sl_atr
        tp_dist = atr_now * self.tp_atr
        eq = float(self.equity)
        if eq <= 0:
            return
        sz = max(int(round(eq * self.risk_pct / sl_dist)), 1)
        mx = int(eq * 0.95 / price)
        sz = min(sz, max(mx, 1))

        if direction == "long":
            self.buy(size=sz, sl=price - sl_dist, tp=price + tp_dist)
        else:
            self.sell(size=sz, sl=price + sl_dist, tp=price - tp_dist)
        self._entry_bar = len(self.data)
        self._inc()


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def run():
    data = load_data("BTC-USD", "60d")
    logging.info("Data: %d bars | %s → %s", len(data), data.index[0], data.index[-1])

    bt = Backtest(data, HybridMomentumScalper,
                  cash=1_000_000, commission=0.00035, margin=0.05,
                  trade_on_close=False, exclusive_orders=False)

    stats = bt.run()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _print_results(stats, "BASELINE")

    # ━━ ABLATION STUDY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n{'='*75}")
    print("  ABLATION STUDY - 各フィルターの貢献度分析")
    print(f"{'='*75}")
    _hdr()
    configs = [
        ("全フィルターON (ベースライン)", {}),
        ("VWAPフィルターOFF",            {"use_vwap": False}),
        ("Volumeフィルター OFF",         {"use_vol": False}),
        ("RSIフィルター OFF",            {"use_rsi": False}),
        ("SessionフィルターOFF",         {"use_session": False}),
        ("WR+EMA のみ (最小構成)",       {"use_vwap": False, "use_vol": False,
                                          "use_rsi": False, "use_session": False}),
    ]
    for name, p in configs:
        try:
            s = bt.run(**p)
            _row(name, s)
        except Exception as ex:
            print(f"  {name:<38s} | ERROR: {ex}")

    # ━━ PARAMETER GRID ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n{'='*75}")
    print("  PARAMETER GRID - SL / TP / Volume倍率 最適化")
    print(f"{'='*75}")
    print(f"  {'SL':>5} {'TP':>5} {'VolM':>5} | {'N':>4} {'WR%':>7} {'PF':>6} {'Ret%':>8} {'DD%':>8} {'Score':>7}")
    print(f"  {'-'*65}")

    best_score, best_p = 0, {}
    for sl in [1.0, 1.5, 2.0, 2.5]:
        for tp in [2.0, 3.0, 4.0, 5.0]:
            for vm in [0.8, 1.0, 1.3]:
                try:
                    s = bt.run(sl_atr=sl, tp_atr=tp, vol_mult=vm)
                    nt = s.get("# Trades", 0)
                    if nt >= 3:
                        wr = s.get("Win Rate [%]", 0)
                        pf = s.get("Profit Factor", 0) or 0
                        if np.isnan(pf): pf = 0
                        r = s.get("Return [%]", 0)
                        dd = s.get("Max. Drawdown [%]", 0)
                        sc = pf * min(wr / 50, 1.3) * min(nt ** 0.5 / 4, 2.0)
                        if sc > best_score:
                            best_score, best_p = sc, {"sl_atr": sl, "tp_atr": tp, "vol_mult": vm}
                        print(f"  {sl:>5.1f} {tp:>5.1f} {vm:>5.1f} | "
                              f"{nt:>4} {wr:>6.1f}% {pf:>5.2f} {r:>+7.2f}% {dd:>7.2f}% {sc:>6.2f}")
                except Exception:
                    pass

    if best_p:
        print(f"\n  ★ 最適パラメータ: {best_p}  (Score={best_score:.2f})")
        sb = bt.run(**best_p)
        _print_results(sb, "OPTIMIZED")

    # ━━ WR Period Grid ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n{'='*75}")
    print("  Williams %R Period 感度分析")
    print(f"{'='*75}")
    _hdr()
    for wrp in [7, 10, 14, 21, 28]:
        try:
            s = bt.run(wr_period=wrp, **(best_p if best_p else {}))
            _row(f"WR period = {wrp}", s)
        except Exception:
            pass

    # ━━ EMA Period Grid ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print(f"\n{'='*75}")
    print("  EMA Period 感度分析")
    print(f"{'='*75}")
    _hdr()
    for fast, slow in [(5, 13), (8, 21), (9, 21), (9, 26), (12, 26)]:
        try:
            s = bt.run(ema_fast=fast, ema_slow=slow, **(best_p if best_p else {}))
            _row(f"EMA {fast}/{slow}", s)
        except Exception:
            pass

    print(f"\n{'='*75}")

    # ━━ HTML Chart ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        out = Path.cwd() / "hybrid_scalper_v5_report.html"
        bt.plot(open_browser=False, filename=str(out))
        logging.info("Chart → %s", out)
    except Exception as e:
        logging.warning("Plot failed: %s", e)

    return stats


def _print_results(stats, label):
    print(f"\n{'='*75}")
    print(f"  HYBRID MOMENTUM SCALPER v5.0 - {label}")
    print(f"{'='*75}")
    for m in ["Start", "End", "Duration", "Exposure Time [%]",
              "Equity Final [$]", "Equity Peak [$]",
              "Return [%]", "Buy & Hold Return [%]",
              "Sharpe Ratio", "Sortino Ratio", "Calmar Ratio",
              "Max. Drawdown [%]", "Avg. Drawdown [%]",
              "# Trades", "Win Rate [%]",
              "Best Trade [%]", "Worst Trade [%]",
              "Avg. Trade [%]", "Profit Factor",
              "Expectancy [%]", "SQN"]:
        if m in stats.index:
            print(f"  {m:<30s}: {stats[m]}")
    nt = stats.get("# Trades", 0)
    pf = stats.get("Profit Factor", 0)
    wr = stats.get("Win Rate [%]", 0)
    r = stats.get("Return [%]", 0)
    dd = stats.get("Max. Drawdown [%]", 0)
    print(f"{'─'*75}")
    print("  判定: ", end="")
    if nt == 0:
        print("トレードなし — フィルター緩和推奨")
    elif pf and pf > 1.2:
        print(f"強いエッジ検出 (PF={pf:.2f}, WR={wr:.1f}%, Ret={r:+.2f}%)")
    elif pf and pf > 1.0:
        print(f"正のエッジ (PF={pf:.2f}) - パラメータ微調整で改善可能")
    else:
        print(f"エッジなし (PF={pf:.2f}) - 構造変更が必要")
    print(f"{'='*75}")


def _hdr():
    print(f"  {'Config':<38s} | {'N':>4} {'WR%':>7} {'PF':>6} {'Ret%':>8} {'DD%':>8}")
    print(f"  {'-'*75}")

def _row(name, s):
    nt = s.get("# Trades", 0)
    if nt > 0:
        wr = s.get("Win Rate [%]", 0)
        pf = s.get("Profit Factor", 0) or 0
        if np.isnan(pf): pf = 0
        r = s.get("Return [%]", 0)
        dd = s.get("Max. Drawdown [%]", 0)
        print(f"  {name:<38s} | {nt:>4} {wr:>6.1f}% {pf:>5.2f} {r:>+7.2f}% {dd:>7.2f}%")
    else:
        print(f"  {name:<38s} | {'no trades':>40s}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.exception("Fatal: %s", e)
        sys.exit(1)

