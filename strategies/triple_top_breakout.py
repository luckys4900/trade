import numpy as np
import talib
from backtesting import Strategy


class TripleTopBreakout(Strategy):
    """
    【TVScreenerベース】トリプルトップブレイクアウト戦略（4h最適化版）
    Pine Script (tradingview_breakout_optimized.pine) を忠実に移植。
    ピボット検出はO(1)償却で毎バー1回のみ判定。
    """

    pivot_length = 7
    price_tolerance_pct = 1.5
    min_high_count = 3
    bb_period = 20
    bb_std = 2.0
    atr_period = 14
    sl_atr_mult = 2.5
    tp_atr_mult = 4.0
    max_hold_bars = 12
    volume_mult = 1.8
    use_volume_filter = True
    use_bb_filter = True
    use_regime_filter = True
    regime_lookback = 50
    pivot_memory_bars = 120
    risk_per_trade = 0.02
    use_lows_rising_filter = True
    _debug_counts = None

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
        self._entry_bar = None
        self._debug_counts = {'pivots': 0, 'tt_ok': 0, 'near_ok': 0, 'lr_ok': 0, 'vol_ok': 0, 'bb_ok': 0, 'regime_ok': 0, 'entries': 0}

    def next(self):
        n = len(self.data.Close)

        # --- Step 1: O(1) pivot detection ---
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
                self._debug_counts['pivots'] += 1

            cutoff = n - self.pivot_memory_bars
            while self._pivot_high_bars and self._pivot_high_bars[0] < cutoff:
                self._pivot_highs.pop(0)
                self._pivot_high_bars.pop(0)

        # --- Step 2: Position management ---
        if self.position:
            if self._entry_bar is not None:
                held = n - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
            return

        # --- Step 3: Warmup ---
        if n < max(self.atr_period, self.bb_period) + 2 * self.pivot_length + 5:
            return

        # --- Step 4: Triple top check ---
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
        near_high_ok = abs(close - avg_h) / avg_h <= tol

        if not (price_band_ok and near_high_ok):
            return
        self._debug_counts['tt_ok'] += 1
        self._debug_counts['near_ok'] += 1

        # Lows rising check
        lows_rising = True
        if self.use_lows_rising_filter:
            bars3 = self._pivot_high_bars[-self.min_high_count:]
            if len(bars3) >= 2:
                for i in range(1, len(bars3)):
                    pbar = bars3[i]
                    cbar = bars3[i - 1]
                    p_offset = max(0, n - 1 - pbar)
                    c_offset_start = max(0, n - 1 - cbar)
                    c_offset_end = n
                    if p_offset >= c_offset_start or c_offset_start >= c_offset_end:
                        continue
                    prev_low = min(self.data.Low[p_offset:c_offset_start])
                    curr_low = min(self.data.Low[c_offset_start:c_offset_end])
                    if curr_low <= prev_low:
                        lows_rising = False
                        break

        if not lows_rising:
            return
        self._debug_counts['lr_ok'] += 1

        # --- Step 5: Filters ---
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        if self.use_volume_filter:
            vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0
            if vol_avg <= 0 or self.data.Volume[-1] <= vol_avg * self.volume_mult:
                return
        self._debug_counts['vol_ok'] += 1

        if self.use_bb_filter:
            if len(self.bb_width) < 2:
                return
            if not (close > self.bb_upper[-1] and self.bb_width[-1] > self.bb_width[-2]):
                return
        self._debug_counts['bb_ok'] += 1

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
            for i in range(1, min(self.regime_lookback + 1, n - 1)):
                c2 = self.data.Close[-(i + 1)]
                c3 = self.data.Close[-(i + 2)] if (i + 2) <= n else c2
                if c3 > 0:
                    ret = abs(c2 - c3) / c3 * 100
                    total += 1
                    if cur_vol >= ret:
                        higher += 1
            if total > 0:
                pct = higher / total * 100
                if not (35 <= pct <= 80):
                    return
        self._debug_counts['regime_ok'] += 1

        # --- Step 6: Entry ---
        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult
        risk_dist = close - sl
        if risk_dist <= 0:
            return

        self.buy(sl=sl, tp=tp)
        self._entry_bar = n
        self._debug_counts['entries'] += 1
