#!/usr/bin/env python3
"""
================================================================================
  RSI Momentum Swing Trader v6.0
  ---------------------------------------------------------------------------
  BTC/USD 4時間足 | Cursor実行対応

  ■ 実績根拠
  ---------------------------------------------------------------------------
  @AtomicScript (Medium) 実測バックテスト 4H BTC/USDT:
    WR 60%, PF 2.09, Sharpe 5.13, MaxDD -5.20%, 25 trades/年

  TradingView RSI-Adaptive T3 + Squeeze Momentum (30min BTC):
    WR 47.8%, PF 2.01, MaxDD -5.77%, 181 trades

  QuantifiedStrategies (RSI 91% WR 研究):
    RSI works best on daily/4H bars with short lookback (2-5 days)
    RSI crossover (not level) = proven edge

  ■ なぜ5分足を捨てたか
  ---------------------------------------------------------------------------
  - 5min 384 trades × 0.07% = 手数料だけで-26.88%（v1の死因）
  - 5min RSI: WR 45%, PF 0.47, Sharpe -3.8（@AtomicScript実測）
  - 4H RSI:   WR 60%, PF 2.09, Sharpe 5.13（同一戦略、時間軸だけ変更）
  - 結論: 同じ戦略でも時間軸で結果が10倍違う

  ■ 戦略アーキテクチャ（3層コンフルエンス）
  ---------------------------------------------------------------------------
  Layer 1 - RSI Crossover Signal:
    LONG:  RSI(14)が30以下に落ちた後、30を上抜け（oversold exit）
    SHORT: RSI(14)が70以上に上がった後、70を下抜け（overbought exit）

  Layer 2 - EMA Trend Filter:
    LONG:  Close > EMA(50)（上昇トレンド内でのみ）
    SHORT: Close < EMA(50)（下降トレンド内でのみ）

  Layer 3 - ATR Risk Management:
    SL = sl_atr × ATR(14)（ボラティリティ連動）
    TP = tp_atr × ATR(14)（R:R最低1:2保証）
    Time Stop = max_bars 本（最大20本 = 80時間）

  ■ 実行方法
  ---------------------------------------------------------------------------
  $ pip install backtesting yfinance numpy pandas
  $ python rsi_swing_trader_v6.py
================================================================================
"""

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ==============================================================================
# INDICATORS
# ==============================================================================

def ema_ind(series, period):
    return pd.Series(series).ewm(span=period, adjust=False).mean().values


def sma_ind(series, period):
    return pd.Series(series).rolling(period, min_periods=period).mean().values


def rsi_ind(series, period=14):
    """Wilder RSI（指数移動平均ベース）"""
    s = pd.Series(series)
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    return (100 - 100 / (1 + g / lo.replace(0, np.nan))).values


def atr_ind(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean().values  # Wilder ATR


def macd_ind(series, fast=12, slow=26, signal=9):
    """MACD line and signal line. Returns MACD histogram."""
    s = pd.Series(series)
    ema_f = s.ewm(span=fast, adjust=False).mean()
    ema_s = s.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - sig_line
    return hist.values


# ==============================================================================
# DATA — 4H足
# ==============================================================================

def load_data_4h(symbol="BTC-USD", period="60d"):
    """yfinanceで4H足データ取得。失敗時はsynthetic。

    periodが730日を超える場合は、1時間足を複数ウィンドウに分割して取得し、
    結合後に4Hへリサンプルする。
    """
    try:
        import yfinance as yf
        logging.info("Fetching %s 4H data (period=%s)...", symbol, period)

        df_list = []

        days = None
        if isinstance(period, str) and period.endswith("d"):
            try:
                days = int(period[:-1])
            except ValueError:
                days = None

        if days is not None and days > 720:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
            max_window_days = 720
            cur_start = start

            while cur_start < end:
                cur_end = min(cur_start + timedelta(days=max_window_days), end)
                logging.info(
                    "Downloading window: %s → %s",
                    cur_start.isoformat(),
                    cur_end.isoformat(),
                )
                df_win = yf.download(
                    symbol,
                    start=cur_start,
                    end=cur_end,
                    interval="1h",
                    progress=False,
                    auto_adjust=False,
                    group_by="column",
                )
                if not df_win.empty:
                    df_list.append(df_win)
                cur_start = cur_end

            if not df_list:
                raise RuntimeError("Empty")
            df = pd.concat(df_list)
        else:
            df = yf.download(
                symbol,
                period=period,
                interval="1h",
                progress=False,
                auto_adjust=False,
                group_by="column",
            )
            if df.empty:
                raise RuntimeError("Empty")

        cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        df = df.iloc[:, : len(cols)]
        df.columns = cols[: df.shape[1]]
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        # 1H → 4H リサンプル
        df4h = df.resample("4h").agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        ).dropna()

        logging.info("OK: %d bars (4H) via yfinance", len(df4h))
        return df4h[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        logging.warning("yfinance failed (%s) → synthetic 4H data", e)
        return _synth_4h(days=180)


def _synth_4h(days=180):
    """合成BTC 4H足データ（レジーム切替、ファットテール、モメンタム）"""
    np.random.seed(42)
    n = days * 6  # 4H = 6本/日
    ts = pd.date_range(
        datetime(2024, 7, 1, tzinfo=timezone.utc),
        periods=n,
        freq="4h",
        tz="UTC",
    )

    # レジーム: 0=レンジ, 1=上昇, 2=下降
    reg = np.zeros(n, dtype=int)
    cr = 0
    rd = 0
    for i in range(n):
        rd += 1
        if rd > 30 and np.random.random() < 0.02:  # ~50本(8日)でレジーム変更
            cr = np.random.choice([0, 1, 2], p=[0.30, 0.40, 0.30])
            rd = 0
        reg[i] = cr

    base = 60000.0
    cl = np.zeros(n)
    cl[0] = base
    mom = 0.0
    for i in range(1, n):
        r = reg[i]
        vol = 0.012  # 4Hの基準ボラ
        if r == 1:
            dr = 0.0015
            vol *= 1.2   # 上昇: +0.15%/4H drift
        elif r == 2:
            dr = -0.0012
            vol *= 1.3   # 下降
        else:
            dr = -(cl[i - 1] - base) / base * 0.002  # レンジ: 平均回帰
        noise = np.random.standard_t(df=4) * vol
        mom = 0.3 * mom + 0.7 * noise
        ret = dr + mom
        if np.random.random() < 0.005:
            ret += np.random.choice([-1, 1]) * np.random.uniform(0.02, 0.06)
        cl[i] = cl[i - 1] * (1 + ret)
        if i % 150 == 0:
            base = cl[i]

    op = np.roll(cl, 1)
    op[0] = cl[0]
    intr = np.abs(np.random.randn(n)) * 0.006
    hi = np.maximum(op, cl) * (1 + intr)
    lo = np.minimum(op, cl) * (1 - intr)
    vol = np.random.lognormal(12, 0.6, n)

    logging.info("Synthetic 4H: %d bars (%d days)", n, days)
    return pd.DataFrame(
        {"Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": vol},
        index=ts,
    )


# ==============================================================================
# STRATEGY
# ==============================================================================

from backtesting import Backtest, Strategy


class RSIMomentumSwing(Strategy):
    """
    RSI Momentum Swing Trader

    根拠: @AtomicScript実測 4H BTC: WR 60%, PF 2.09, Sharpe 5.13

    LONG:  RSI(14) が oversold(30)以下 → 30を上抜けクロス AND Close > EMA(50)
    SHORT: RSI(14) が overbought(70)以上 → 70を下抜けクロス AND Close < EMA(50)

    SL = sl_atr × ATR(14), TP = tp_atr × ATR(14)
    タイムストップ = max_bars 本
    """

    rsi_period: int = 14
    rsi_os: float = 30.0      # Oversold threshold
    rsi_ob: float = 70.0      # Overbought threshold
    ema_period: int = 50      # Trend filter
    atr_period: int = 14
    sl_atr: float = 1.5       # SL multiplier
    tp_atr: float = 3.0       # TP multiplier (1:2 R:R)
    risk_pct: float = 0.02    # 2% risk per trade (4H = fewer trades)
    max_bars: int = 20        # Max hold = 80 hours
    use_ema: bool = True      # EMA trend filter
    use_macd: bool = False    # Optional MACD confirmation

    def init(self):
        c = self.data.Close
        h, l = self.data.High, self.data.Low
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.ema50 = self.I(ema_ind, c, self.ema_period)
        self.atr = self.I(atr_ind, h, l, c, self.atr_period)
        self.macd_hist = self.I(macd_ind, c, 12, 26, 9)
        self._entry_bar = 0

    def next(self):
        # タイムストップ
        if self.position:
            if len(self.data) - self._entry_bar >= self.max_bars:
                self.position.close()
            return

        if len(self.data.Close) < max(self.rsi_period, self.ema_period, 26) + 3:
            return

        rsi_now = float(self.rsi[-1])
        rsi_prev = float(self.rsi[-2])
        c_now = float(self.data.Close[-1])
        ema_now = float(self.ema50[-1])
        atr_now = float(self.atr[-1])
        macd_now = float(self.macd_hist[-1])

        if any(
            np.isnan(x)
            for x in [rsi_now, rsi_prev, c_now, ema_now, atr_now, macd_now]
        ):
            return
        if atr_now <= 0:
            return

        # LONG: RSI crosses up through oversold
        long_rsi = (rsi_prev <= self.rsi_os) and (rsi_now > self.rsi_os)
        long_ema = (not self.use_ema) or (c_now > ema_now)
        long_macd = (not self.use_macd) or (macd_now > 0)

        if long_rsi and long_ema and long_macd:
            self._enter("long", c_now, atr_now)
            return

        # SHORT: RSI crosses down through overbought
        short_rsi = (rsi_prev >= self.rsi_ob) and (rsi_now < self.rsi_ob)
        short_ema = (not self.use_ema) or (c_now < ema_now)
        short_macd = (not self.use_macd) or (macd_now < 0)

        if short_rsi and short_ema and short_macd:
            self._enter("short", c_now, atr_now)

    def _enter(self, direction, price, atr_now):
        sl_d = atr_now * self.sl_atr
        tp_d = atr_now * self.tp_atr
        eq = float(self.equity)
        if eq <= 0:
            return
        sz = max(int(round(eq * self.risk_pct / sl_d)), 1)
        mx = int(eq * 0.95 / price)
        sz = min(sz, max(mx, 1))
        if direction == "long":
            self.buy(size=sz, sl=price - sl_d, tp=price + tp_d)
        else:
            self.sell(size=sz, sl=price + sl_d, tp=price - tp_d)
        self._entry_bar = len(self.data)


# ==============================================================================
# BACKTEST ENGINE
# ==============================================================================

def run():
    # 1500日分（約4年）の1時間足→4時間足データを使用
    data = load_data_4h("BTC-USD", "1500d")
    logging.info(
        "Data: %d bars (4H) | %s → %s", len(data), data.index[0], data.index[-1]
    )

    bt = Backtest(
        data,
        RSIMomentumSwing,
        cash=1_000_000,
        commission=0.0005,
        margin=0.05,
        trade_on_close=False,
        exclusive_orders=False,
    )

    stats = bt.run()
    _print(stats, "BASELINE (RSI 14, EMA 50, SL 1.5x, TP 3.0x)")

    # ABLATION STUDY
    print(f"\n{'='*75}")
    print("  ABLATION: フィルター効果分析")
    print(f"{'='*75}")
    _hdr()
    for name, p in [
        ("Baseline (EMA ON)", {}),
        ("EMA OFF (RSIのみ)", {"use_ema": False}),
        ("EMA ON + MACD ON", {"use_macd": True}),
    ]:
        try:
            _row(name, bt.run(**p))
        except Exception as ex:
            print(f"  {name:<40s} | ERROR: {ex}")

    # RSI PERIOD SENSITIVITY
    print(f"\n{'='*75}")
    print("  RSI Period 感度分析")
    print(f"{'='*75}")
    _hdr()
    for rp in [5, 7, 10, 14, 21]:
        try:
            _row(f"RSI({rp})", bt.run(rsi_period=rp))
        except Exception:
            pass

    # SL/TP GRID OPTIMIZATION
    print(f"\n{'='*75}")
    print("  SL/TP パラメータグリッド最適化")
    print(f"{'='*75}")
    print(
        f"  {'SL':>5} {'TP':>5} {'RSI':>5} {'EMA':>5} | "
        f"{'N':>4} {'WR%':>7} {'PF':>6} {'Ret%':>8} {'DD%':>8} {'Sharpe':>7}"
    )
    print(f"  {'-'*70}")

    best_score, best_p = 0, {}
    for sl in [1.0, 1.5, 2.0, 2.5, 3.0]:
        for tp in [2.0, 3.0, 4.0, 5.0, 6.0]:
            for rp in [7, 10, 14]:
                for use_e in [True, False]:
                    try:
                        s = bt.run(
                            sl_atr=sl,
                            tp_atr=tp,
                            rsi_period=rp,
                            use_ema=use_e,
                        )
                        nt = s.get("# Trades", 0)
                        if nt >= 3:
                            wr = s.get("Win Rate [%]", 0)
                            pf = s.get("Profit Factor", 0) or 0
                            if pf is None or np.isnan(pf):
                                pf = 0
                            r = s.get("Return [%]", 0)
                            dd = s.get("Max. Drawdown [%]", 0)
                            sh = s.get("Sharpe Ratio", 0) or 0
                            if np.isnan(sh):
                                sh = 0

                            # Composite score
                            sc = (
                                max(pf, 0) * 2.0
                                + max(sh, 0) * 1.5
                                + min(wr / 50, 1.5) * 1.0
                                + min(nt ** 0.5 / 3, 2.0) * 0.5
                                - max(-dd - 10, 0) * 0.3
                            )
                            if sc > best_score:
                                best_score = sc
                                best_p = {
                                    "sl_atr": sl,
                                    "tp_atr": tp,
                                    "rsi_period": rp,
                                    "use_ema": use_e,
                                }
                            ema_str = "ON" if use_e else "OFF"
                            print(
                                f"  {sl:>5.1f} {tp:>5.1f} {rp:>5} {ema_str:>5} | "
                                f"{nt:>4} {wr:>6.1f}% {pf:>5.2f} "
                                f"{r:>+7.2f}% {dd:>7.2f}% {sh:>6.2f}"
                            )
                    except Exception:
                        pass

    if best_p:
        print(f"\n  ★ 最適パラメータ: {best_p}  (Score={best_score:.2f})")
        sb = bt.run(**best_p)
        _print(sb, "OPTIMIZED")

    # RSI THRESHOLD SENSITIVITY
    print(f"\n{'='*75}")
    print("  RSI閾値 感度分析 (OS / OB)")
    print(f"{'='*75}")
    _hdr()
    bp = best_p if best_p else {}
    for os_val, ob_val in [(20, 80), (25, 75), (30, 70), (35, 65), (40, 60)]:
        try:
            _row(
                f"RSI OS={os_val} OB={ob_val}",
                bt.run(rsi_os=os_val, rsi_ob=ob_val, **bp),
            )
        except Exception:
            pass

    # EMA PERIOD SENSITIVITY
    print(f"\n{'='*75}")
    print("  EMA Period 感度分析")
    print(f"{'='*75}")
    _hdr()
    for ep in [20, 30, 50, 100, 200]:
        try:
            _row(f"EMA({ep})", bt.run(ema_period=ep, **bp))
        except Exception:
            pass

    print(f"\n{'='*75}")

    # HTML CHART
    try:
        out = Path.cwd() / "rsi_swing_v6_report.html"
        bt.plot(open_browser=False, filename=str(out))
        logging.info("Chart → %s", out)
    except Exception as e:
        logging.warning("Plot failed: %s", e)

    return stats


def _print(stats, label):
    print(f"\n{'='*75}")
    print(f"  RSI MOMENTUM SWING v6.0 - {label}")
    print(f"{'='*75}")
    for m in [
        "Start",
        "End",
        "Duration",
        "Exposure Time [%]",
        "Equity Final [$]",
        "Equity Peak [$]",
        "Return [%]",
        "Buy & Hold Return [%]",
        "Sharpe Ratio",
        "Sortino Ratio",
        "Calmar Ratio",
        "Max. Drawdown [%]",
        "Avg. Drawdown [%]",
        "# Trades",
        "Win Rate [%]",
        "Best Trade [%]",
        "Worst Trade [%]",
        "Avg. Trade [%]",
        "Profit Factor",
        "Expectancy [%]",
        "SQN",
    ]:
        if m in stats.index:
            print(f"  {m:<30s}: {stats[m]}")
    nt = stats.get("# Trades", 0)
    pf = stats.get("Profit Factor", 0) or 0
    wr = stats.get("Win Rate [%]", 0)
    r = stats.get("Return [%]", 0)
    dd = stats.get("Max. Drawdown [%]", 0)
    sh = stats.get("Sharpe Ratio", 0) or 0
    print(f"{'─'*75}")
    if nt == 0:
        print("  判定: トレードなし → フィルター緩和推奨")
    elif pf > 1.5:
        print(f"  判定: 強いエッジ検出 | PF={pf:.2f} WR={wr:.1f}% Sharpe={sh:.2f}")
    elif pf > 1.0:
        print(f"  判定: 正のエッジ | PF={pf:.2f} - パラメータ微調整で改善可能")
    else:
        print(f"  判定: エッジなし | PF={pf:.2f} - 構造変更が必要")
    print(f"{'='*75}")


def _hdr():
    print(
        f"  {'Config':<40s} | {'N':>4} {'WR%':>7} {'PF':>6} "
        f"{'Ret%':>8} {'DD%':>8} {'Sharpe':>7}"
    )
    print(f"  {'-'*78}")


def _row(name, s):
    nt = s.get("# Trades", 0)
    if nt > 0:
        wr = s.get("Win Rate [%]", 0)
        pf = s.get("Profit Factor", 0) or 0
        if np.isnan(pf):
            pf = 0
        r = s.get("Return [%]", 0)
        dd = s.get("Max. Drawdown [%]", 0)
        sh = s.get("Sharpe Ratio", 0) or 0
        if np.isnan(sh):
            sh = 0
        print(
            f"  {name:<40s} | {nt:>4} {wr:>6.1f}% {pf:>5.2f} "
            f"{r:>+7.2f}% {dd:>7.2f}% {sh:>6.2f}"
        )
    else:
        print(f"  {name:<40s} | no trades")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.exception("Fatal: %s", e)
        sys.exit(1)

