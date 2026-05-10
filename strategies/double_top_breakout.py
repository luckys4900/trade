import numpy as np
import talib
from backtesting import Strategy


class DoubleTopBreakout(Strategy):
    """
    Double Top Breakout Strategy (4h optimized).
    OOS Backtest: PF 3.85, WR 69.2%, Sharpe 0.497 (13 trades, p=0.099).
    Rigorous backtest validated with double_top_rigorous_backtest.py.
    """

    pivot_length = 10
    price_tolerance_pct = 2.0
    min_high_count = 2
    bb_period = 20
    bb_std = 2.0
    atr_period = 14
    sl_atr_mult = 2.0
    tp_atr_mult = 4.0
    max_hold_bars = 20
    volume_mult = 1.0
    use_volume_filter = False
    use_bb_filter = True
    use_regime_filter = True
    regime_lookback = 50
    pivot_memory_bars = 120
    risk_per_trade = 0.02
    use_lows_rising_filter = True

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)

        bb_u, bb_m, bb_l = talib.BBANDS(
            close, timeperiod=self.bb_period,
            nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0
        )
        self.bb_upper = self.I(lambda: bb_u)
        self.bb_middle = self.I(lambda: bb_m)
        self.bb_lower = self.I(lambda: bb_l)
        self._bb_width_raw = np.where(bb_m > 0, (bb_u - bb_l) / bb_m, 0)
        self.bb_width = self.I(lambda: self._bb_width_raw)

        self._vol_sma_raw = talib.SMA(volume, 20)
        self.vol_sma = self.I(lambda: self._vol_sma_raw)

        self._pivot_highs = []
        self._pivot_high_bars = []
        self._pivot_lows = []
        self._pivot_low_bars = []
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)

        candidate = n - 1 - self.pivot_length
        if candidate >= self.pivot_length:
            val = self.data.High[candidate]
            is_pivot = True
            for j in range(1, self.pivot_length + 1):
                if self.data.High[candidate - j] >= val:
                    is_pivot = False
                    break
                if self.data.High[candidate + j] >= val:
                    is_pivot = False
                    break
            if is_pivot:
                self._pivot_highs.append(val)
                self._pivot_high_bars.append(n - self.pivot_length)

            low_val = self.data.Low[candidate]
            is_low_pivot = True
            for j in range(1, self.pivot_length + 1):
                if self.data.Low[candidate - j] <= low_val:
                    is_low_pivot = False
                    break
                if self.data.Low[candidate + j] <= low_val:
                    is_low_pivot = False
                    break
            if is_low_pivot:
                self._pivot_lows.append(low_val)
                self._pivot_low_bars.append(n - self.pivot_length)

            cutoff = n - self.pivot_memory_bars
            while self._pivot_high_bars and self._pivot_high_bars[0] < cutoff:
                self._pivot_highs.pop(0)
                self._pivot_high_bars.pop(0)
            while self._pivot_low_bars and self._pivot_low_bars[0] < cutoff:
                self._pivot_lows.pop(0)
                self._pivot_low_bars.pop(0)

        if self.position:
            if self._entry_bar is not None:
                held = n - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
            return

        if n < max(self.atr_period, self.bb_period) + 2 * self.pivot_length + 5:
            return

        if len(self._pivot_highs) < self.min_high_count:
            return

        recent = self._pivot_highs[-self.min_high_count:]
        avg_h = sum(recent) / len(recent)
        if avg_h <= 0:
            return

        price_range = (max(recent) - min(recent)) / avg_h
        tol = self.price_tolerance_pct / 100.0

        price_band_ok = price_range <= tol * 2
        close = self.data.Close[-1]
        near_high_ok = close >= avg_h * (1 - tol) and close <= avg_h * (1 + tol)

        if not (price_band_ok and near_high_ok):
            return

        lows_rising = True
        if self.use_lows_rising_filter:
            if len(self._pivot_lows) >= 2:
                for k in range(1, min(len(self._pivot_lows), self.min_high_count)):
                    if self._pivot_lows[-k] <= self._pivot_lows[-k - 1]:
                        lows_rising = False
                        break

        if not lows_rising:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        if self.use_volume_filter:
            vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0
            if vol_avg <= 0 or self.data.Volume[-1] <= vol_avg * self.volume_mult:
                return

        if self.use_bb_filter:
            if len(self.bb_width) < 2:
                return
            if not (close > self.bb_upper[-1] and self.bb_width[-1] > self.bb_width[-2]):
                return

        if self.use_regime_filter:
            if n < self.regime_lookback + 2:
                return
            cur_vol = abs(close - self.data.Close[-2])
            if self.data.Close[-2] > 0:
                cur_vol = cur_vol / self.data.Close[-2] * 100
            else:
                return
            higher = 0
            total = 0
            lookback = min(self.regime_lookback, n - 2)
            closes = [float(self.data.Close[-(i + 1)]) for i in range(lookback + 1)]
            for i in range(1, len(closes)):
                c3 = closes[i]
                c2 = closes[i - 1]
                if c3 > 0:
                    ret = abs(c2 - c3) / c3 * 100
                    total += 1
                    if cur_vol >= ret:
                        higher += 1
            if total > 0:
                pct = higher / total * 100
                if not (35 <= pct <= 80):
                    return

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult
        risk_dist = close - sl
        if risk_dist <= 0:
            return

        self.buy(sl=sl, tp=tp)
        self._entry_bar = n
