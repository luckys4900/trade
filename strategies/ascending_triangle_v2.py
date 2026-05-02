import numpy as np
import talib
from backtesting import Strategy


class AscendingTriangleBreakout(Strategy):
    """
    Variant 2: Ascending Triangle Breakout
    フラット天井 + 安値切り上がり → ブレイクアウト
    lows_risingをパターンの一部として組み込み
    """

    pivot_length = 5
    price_tolerance_pct = 1.5
    min_high_count = 2
    pivot_memory = 80
    triangle_lookback = 80
    low_half_period = 40
    atr_period = 14
    bb_period = 20
    bb_std = 2.0
    sl_atr_mult = 1.5
    tp_atr_mult = 3.5
    max_hold_bars = 12

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
        bb_u, bb_m, bb_l = talib.BBANDS(close, timeperiod=self.bb_period,
                                         nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0)
        self._bb_width_raw = np.where(bb_m > 0, (bb_u - bb_l) / bb_m, 0)
        self.bb_width = self.I(lambda: self._bb_width_raw)
        self._pivot_highs = []
        self._pivot_high_bars = []
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)
        candidate = n - 1 - self.pivot_length
        if candidate >= self.pivot_length:
            val = self.data.High[candidate]
            is_pivot = True
            for j in range(1, self.pivot_length + 1):
                if self.data.High[candidate - j] >= val or self.data.High[candidate + j] >= val:
                    is_pivot = False
                    break
            if is_pivot:
                self._pivot_highs.append(val)
                self._pivot_high_bars.append(n - self.pivot_length)
            cutoff = n - self.pivot_memory
            while self._pivot_high_bars and self._pivot_high_bars[0] < cutoff:
                self._pivot_highs.pop(0)
                self._pivot_high_bars.pop(0)

        if self.position:
            if self._entry_bar is not None and (n - self._entry_bar) >= self.max_hold_bars:
                self.position.close()
                self._entry_bar = None
            return

        if n < max(self.triangle_lookback, self.atr_period) + 2 * self.pivot_length:
            return

        if len(self._pivot_highs) < self.min_high_count:
            return

        recent = self._pivot_highs[-self.min_high_count:]
        avg_h = sum(recent) / len(recent)
        if avg_h <= 0:
            return
        tol = self.price_tolerance_pct / 100.0
        price_range = (max(recent) - min(recent)) / avg_h
        if price_range > tol * 2:
            return

        hp = min(self.low_half_period, n // 2)
        if hp < 5:
            return
        recent_lows = list(self.data.Low[n - hp:n])
        older_lows = list(self.data.Low[n - 2 * hp:n - hp])
        if not older_lows:
            return
        min_recent = min(recent_lows)
        min_older = min(older_lows)
        if min_recent <= min_older:
            return

        close = self.data.Close[-1]
        if close <= avg_h:
            return

        if len(self.bb_width) < 5:
            return
        if self.bb_width[-1] <= self.bb_width[-5]:
            return

        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult
        self.buy(sl=sl, tp=tp)
        self._entry_bar = n
