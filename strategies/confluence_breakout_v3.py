import numpy as np
import talib
from backtesting import Strategy


class ConfluenceBreakout(Strategy):
    """
    Variant 3: Multi-Timeframe Confluence Breakout
    パーセンタイルベース抵抗線 + RSIモメンタム確認
    ピボットマッチングに依存しない適応的アプローチ
    """

    resistance_lookback = 50
    touch_lookback = 60
    touch_threshold = 0.98
    min_touches = 2
    rsi_threshold = 50
    min_body_atr = 0.5
    atr_period = 14
    rsi_period = 14
    sl_atr_mult = 2.0
    tp_atr_mult = 5.0
    max_hold_bars = 18

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
        self._rsi_raw = talib.RSI(close, self.rsi_period)
        self.rsi = self.I(lambda: self._rsi_raw)
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)

        if self.position:
            if self._entry_bar is not None and (n - self._entry_bar) >= self.max_hold_bars:
                self.position.close()
                self._entry_bar = None
            return

        rl = self.resistance_lookback
        tl = self.touch_lookback
        if n < max(rl, tl, self.atr_period) + 10:
            return

        close = self.data.Close[-1]
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        resistance = max(self.data.High[n - rl:n])

        start = max(n - tl, rl)
        touches = 0
        for i in range(start, n):
            h = self.data.High[i]
            if h >= resistance * self.touch_threshold:
                touches += 1

        if touches < self.min_touches:
            return

        if close <= resistance:
            return

        if self.rsi[-1] <= self.rsi_threshold:
            return

        body = abs(close - self.data.Open[-1])
        if body < atr_val * self.min_body_atr:
            return

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult
        self.buy(sl=sl, tp=tp)
        self._entry_bar = n
