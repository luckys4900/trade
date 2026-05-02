# -*- coding: utf-8 -*-
"""
Triple Top Detection Indicator
Detects triple top patterns with volume and volatility confirmation
"""

import numpy as np
import pandas as pd
import talib as ta


class TripleTopIndicator:
    def __init__(self, pivot_length=7, price_tolerance=0.015, min_high_count=3,
                 bb_period=20, bb_std=1.8, atr_period=14, volume_mult=2.5,
                 regime_lookback=50, vol_pct_min=30, vol_pct_max=90):
        self.pivot_length = pivot_length
        self.price_tolerance = price_tolerance
        self.min_high_count = min_high_count
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.volume_mult = volume_mult
        self.regime_lookback = regime_lookback
        self.vol_pct_min = vol_pct_min
        self.vol_pct_max = vol_pct_max

    def compute_indicators(self, df):
        df = df.copy()

        df["atr"] = ta.ATR(df["high"], df["low"], df["close"], timeperiod=self.atr_period)

        upper, middle, lower = ta.BBANDS(df["close"], timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std)
        df["bb_upper"] = upper
        df["bb_middle"] = middle
        df["bb_lower"] = lower
        df["bb_width"] = (upper - lower) / middle

        df["vol_pct"] = df["close"].pct_change().abs().rolling(self.regime_lookback).rank(pct=True) * 100

        df["volume_ma"] = df["volume"].rolling(self.pivot_length * 3).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma"]

        df["pivot_high"] = df["high"].rolling(self.pivot_length, center=True).max() == df["high"]
        df["pivot_low"] = df["low"].rolling(self.pivot_length, center=True).min() == df["low"]

        return df

    def detect_triple_top(self, df):
        df = self.compute_indicators(df)
        signals = np.zeros(len(df), dtype=int)

        for i in range(self.pivot_length * 3, len(df)):
            if self._is_triple_top_signal(df, i):
                signals[i] = 1

        df["triple_top_signal"] = signals
        return df, signals

    def _is_triple_top_signal(self, df, i):
        current_close = df["close"].iloc[i]
        current_high = df["high"].iloc[i]
        current_low = df["low"].iloc[i]
        current_volume = df["volume"].iloc[i]
        current_bb_upper = df["bb_upper"].iloc[i]
        current_bb_width = df["bb_width"].iloc[i]
        current_bb_width_prev = df["bb_width"].iloc[i-1] if i > 0 else 0
        current_vol_pct = df["vol_pct"].iloc[i]
        current_volume_ratio = df["volume_ratio"].iloc[i]

        if not (self.vol_pct_min <= current_vol_pct <= self.vol_pct_max):
            return False

        if current_volume_ratio < self.volume_mult:
            return False

        if current_close < current_bb_upper:
            return False

        if current_bb_width <= current_bb_width_prev:
            return False

        pivot_highs = []
        pivot_highs_indices = []

        for j in range(max(0, i - self.pivot_length * 6), i):
            if df["pivot_high"].iloc[j]:
                pivot_highs.append(df["high"].iloc[j])
                pivot_highs_indices.append(j)

        if len(pivot_highs) < self.min_high_count:
            return False

        recent_highs = pivot_highs[-self.min_high_count:]
        avg_high = np.mean(recent_highs)
        high_range = max(recent_highs) - min(recent_highs)

        if high_range / avg_high > self.price_tolerance * 2:
            return False

        price_distance = abs(current_high - avg_high) / avg_high
        if price_distance > self.price_tolerance:
            return False

        pivot_lows = []
        for j in range(max(0, i - self.pivot_length * 6), i):
            if df["pivot_low"].iloc[j]:
                pivot_lows.append(df["low"].iloc[j])

        if len(pivot_lows) >= 2:
            if pivot_lows[-1] <= pivot_lows[-2]:
                return False

        return True
