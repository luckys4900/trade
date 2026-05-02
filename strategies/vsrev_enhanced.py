import numpy as np
import talib
from backtesting import Strategy


class VSRevEnhanced(Strategy):
    """
    VSRev拡張版: Volume Spike Reversal + BB Squeeze Confirmation
    現行VSRevの3条件 + BBスクイーズ解除を追加確認
    TVScreener PineのBB幅縮小→拡大パターンを統合
    """

    vol_ratio_threshold = 2.0
    rsi_long_threshold = 25.0
    rsi_short_threshold = 80.0
    atr_period = 14
    rsi_period = 14
    bb_period = 20
    bb_std = 2.0
    sl_atr_mult = 2.0
    tp_atr_mult = 5.0
    max_hold_bars = 6
    use_bb_squeeze = True
    bb_squeeze_lookback = 10

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
        self._rsi_raw = talib.RSI(close, self.rsi_period)
        self.rsi = self.I(lambda: self._rsi_raw)
        bb_u, bb_m, bb_l = talib.BBANDS(close, timeperiod=self.bb_period,
                                         nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0)
        self.bb_upper = self.I(lambda: bb_u)
        self.bb_middle = self.I(lambda: bb_m)
        self.bb_lower = self.I(lambda: bb_l)
        self._bb_width_raw = np.where(bb_m > 0, (bb_u - bb_l) / bb_m, 0)
        self.bb_width = self.I(lambda: self._bb_width_raw)
        self._vol_ma_raw = talib.SMA(volume, 20)
        self.vol_sma = self.I(lambda: self._vol_ma_raw)
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)

        if self.position:
            if self._entry_bar is not None:
                held = n - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_long and self.rsi[-1] > 70:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_short and self.rsi[-1] < 30:
                    self.position.close()
                    self._entry_bar = None
                    return
            return

        if n < max(self.atr_period, self.bb_period, 20) + 5:
            return

        close = self.data.Close[-1]
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0
        if vol_avg <= 0:
            return
        vol_ratio = self.data.Volume[-1] / vol_avg
        if vol_ratio < self.vol_ratio_threshold:
            return

        rsi_now = self.rsi[-1]
        rsi_prev = self.rsi[-2] if len(self.rsi) > 1 else rsi_now

        if self.use_bb_squeeze and len(self.bb_width) >= self.bb_squeeze_lookback + 1:
            was_squeezed = self.bb_width[-self.bb_squeeze_lookback] < np.percentile(
                self.bb_width[-self.bb_squeeze_lookback:], 30)
            expanding = self.bb_width[-1] > self.bb_width[-2]
            if not (was_squeezed and expanding):
                pass

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult

        if rsi_now < self.rsi_long_threshold and rsi_now > rsi_prev:
            self.buy(sl=sl, tp=tp)
            self._entry_bar = n
            return

        if rsi_now > self.rsi_short_threshold and rsi_now < rsi_prev:
            self.sell(sl=close + atr_val * self.sl_atr_mult,
                      tp=close - atr_val * self.tp_atr_mult)
            self._entry_bar = n


class VSRevMultiConfirm(Strategy):
    """
    VSRev拡張版: 複数確認コンフルエンス
    Volume Spike + RSI反転 + BBタッチ/ブレイク の3重確認
    BB下バンドタッチ後の反転を追加 → 勝率向上狙い
    """

    vol_ratio_threshold = 2.0
    rsi_long_threshold = 30.0
    rsi_short_threshold = 70.0
    atr_period = 14
    rsi_period = 14
    bb_period = 20
    bb_std = 2.0
    sl_atr_mult = 2.0
    tp_atr_mult = 5.0
    max_hold_bars = 8
    require_bb_touch = True

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
        self._rsi_raw = talib.RSI(close, self.rsi_period)
        self.rsi = self.I(lambda: self._rsi_raw)
        bb_u, bb_m, bb_l = talib.BBANDS(close, timeperiod=self.bb_period,
                                         nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0)
        self.bb_upper = self.I(lambda: bb_u)
        self.bb_middle = self.I(lambda: bb_m)
        self.bb_lower = self.I(lambda: bb_l)
        self._vol_ma_raw = talib.SMA(volume, 20)
        self.vol_sma = self.I(lambda: self._vol_ma_raw)
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)

        if self.position:
            if self._entry_bar is not None:
                held = n - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_long and self.rsi[-1] > 70:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_short and self.rsi[-1] < 30:
                    self.position.close()
                    self._entry_bar = None
                    return
            return

        if n < max(self.atr_period, self.bb_period, 20) + 5:
            return

        close = self.data.Close[-1]
        low = self.data.Low[-1]
        high = self.data.High[-1]
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0
        if vol_avg <= 0:
            return
        vol_ratio = self.data.Volume[-1] / vol_avg
        if vol_ratio < self.vol_ratio_threshold:
            return

        rsi_now = self.rsi[-1]
        rsi_prev = self.rsi[-2] if len(self.rsi) > 1 else rsi_now

        bb_l = self.bb_lower[-1]
        bb_u = self.bb_upper[-1]

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult

        long_bb = True
        short_bb = True
        if self.require_bb_touch:
            long_bb = low <= bb_l or close <= bb_l
            short_bb = high >= bb_u or close >= bb_u

        if rsi_now < self.rsi_long_threshold and rsi_now > rsi_prev and long_bb:
            self.buy(sl=sl, tp=tp)
            self._entry_bar = n
            return

        if rsi_now > self.rsi_short_threshold and rsi_now < rsi_prev and short_bb:
            self.sell(sl=close + atr_val * self.sl_atr_mult,
                      tp=close - atr_val * self.tp_atr_mult)
            self._entry_bar = n


class VSRevAdaptive(Strategy):
    """
    VSRev拡張版: 適応型ボラティリティゲート
    高ボラ時（ATR拡大）のみエントリー → 逆張りの精度向上
    vol_pctゲート + トレンドフィルター(EMA) を追加
    """

    vol_ratio_threshold = 2.0
    rsi_long_threshold = 25.0
    rsi_short_threshold = 80.0
    atr_period = 14
    rsi_period = 14
    ema_period = 55
    sl_atr_mult = 2.0
    tp_atr_mult = 5.0
    max_hold_bars = 6
    min_vol_pct = 40.0
    max_vol_pct = 95.0
    vol_lookback = 50
    use_trend_filter = False

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        self._atr_raw = talib.ATR(high, low, close, self.atr_period)
        self.atr = self.I(lambda: self._atr_raw)
        self._rsi_raw = talib.RSI(close, self.rsi_period)
        self.rsi = self.I(lambda: self._rsi_raw)
        self._ema_raw = talib.EMA(close, self.ema_period)
        self.ema = self.I(lambda: self._ema_raw)
        self._vol_ma_raw = talib.SMA(volume, 20)
        self.vol_sma = self.I(lambda: self._vol_ma_raw)
        self._entry_bar = None

    def next(self):
        n = len(self.data.Close)

        if self.position:
            if self._entry_bar is not None:
                held = n - self._entry_bar
                if held >= self.max_hold_bars:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_long and self.rsi[-1] > 70:
                    self.position.close()
                    self._entry_bar = None
                    return
                if self.position.is_short and self.rsi[-1] < 30:
                    self.position.close()
                    self._entry_bar = None
                    return
            return

        if n < max(self.atr_period, self.ema_period, self.vol_lookback) + 5:
            return

        close = self.data.Close[-1]
        atr_val = self.atr[-1]
        if atr_val <= 0:
            return

        vol_avg = self.vol_sma[-1] if len(self.vol_sma) > 0 else 0
        if vol_avg <= 0:
            return
        vol_ratio = self.data.Volume[-1] / vol_avg
        if vol_ratio < self.vol_ratio_threshold:
            return

        if n >= self.vol_lookback:
            returns = np.abs(np.diff(self.data.Close[n - self.vol_lookback:n]))
            current_ret = abs(close - self.data.Close[-2])
            if len(returns) > 0:
                rank = np.sum(returns <= current_ret) / len(returns) * 100
                if rank < self.min_vol_pct or rank > self.max_vol_pct:
                    return

        rsi_now = self.rsi[-1]
        rsi_prev = self.rsi[-2] if len(self.rsi) > 1 else rsi_now

        sl = close - atr_val * self.sl_atr_mult
        tp = close + atr_val * self.tp_atr_mult

        if rsi_now < self.rsi_long_threshold and rsi_now > rsi_prev:
            if self.use_trend_filter and close < self.ema[-1]:
                pass
            else:
                self.buy(sl=sl, tp=tp)
                self._entry_bar = n
                return

        if rsi_now > self.rsi_short_threshold and rsi_now < rsi_prev:
            if self.use_trend_filter and close > self.ema[-1]:
                pass
            else:
                self.sell(sl=close + atr_val * self.sl_atr_mult,
                          tp=close - atr_val * self.tp_atr_mult)
                self._entry_bar = n
