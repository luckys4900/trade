import numpy as np
import talib
from backtesting import Strategy


class ResistanceClusterBreakout(Strategy):
    """
    Variant 1: Simplified Resistance Cluster Breakout
    ピボット高値がクラスタリング → 抵抗線形成 → ブレイクアウトでエントリー
    フィルター最小限、パターンそのものがエッジ
    """

    pivot_length = 5
    price_tolerance_pct = 2.0
    min_high_count = 2
    pivot_memory = 100
    atr_period = 14
    sl_atr_mult = 2.0
    tp_atr_mult = 4.0
    max_hold_bars = 15

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
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

        if n < max(self.atr_period, 30) + 2 * self.pivot_length:
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

        close = self.data.Close[-1]
        prev_high = self.data.High[-2]
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        if close <= avg_h:
            return
        if close <= prev_high:
            return

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult
        self.buy(sl=sl, tp=tp)
        self._entry_bar = n
