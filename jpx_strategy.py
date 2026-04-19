"""
Japanese Stock (JPX) RSI Momentum Strategy
Adaptation of rsi_swing_trader_v6 for Japanese Market
"""

import logging
import pandas as pd
import numpy as np
from backtesting import Strategy
from datetime import time

# インジケーター関数（既存のものと共通）
def rsi_ind(series, period=14):
    s = pd.Series(series)
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    return (100 - 100 / (1 + g / lo.replace(0, np.nan))).values

def ema_ind(series, period):
    return pd.Series(series).ewm(span=period, adjust=False).mean().values

def atr_ind(high, low, close, period=14):
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean().values

class JPXRSISwing(Strategy):
    """
    日本株向け RSI モメンタム戦略
    
    - 東証の取引時間（9:00-11:30, 12:30-15:00）を考慮
    - ストップ高・安による流動性欠如のリスクを考慮したATRベースの損切り
    """
    
    rsi_period = 14
    rsi_os = 30
    rsi_ob = 70
    ema_period = 50
    atr_period = 14
    sl_atr = 1.5
    tp_atr = 3.0
    risk_pct = 0.01  # 個別銘柄のためリスクは1%に設定
    
    def init(self):
        c = self.data.Close
        h, l = self.data.High, self.data.Low
        self.rsi = self.I(rsi_ind, c, self.rsi_period)
        self.ema = self.I(ema_ind, c, self.ema_period)
        self.atr = self.I(atr_ind, h, l, c, self.atr_period)
        
    def next(self):
        # 現在時刻の取得（データが日足の場合はスキップ、分足・時間足の場合に有効）
        curr_time = self.data.index[-1].time()
        
        # 日本株市場時間外ならエントリーしない（イントラデイデータの場合）
        if hasattr(self.data.index[-1], 'hour'):
            is_market_open = (
                (time(9, 0) <= curr_time <= time(11, 30)) or
                (time(12, 30) <= curr_time <= time(15, 0))
            )
            if not is_market_open:
                return

        if self.position:
            # 損切り・利確のロジックは backtesting.py が自動で行う
            return

        rsi_now = self.rsi[-1]
        rsi_prev = self.rsi[-2]
        c_now = self.data.Close[-1]
        ema_now = self.ema[-1]
        atr_now = self.atr[-1]
        
        if np.isnan(rsi_now) or np.isnan(ema_now) or np.isnan(atr_now):
            return

        # LONG
        if rsi_prev <= self.rsi_os and rsi_now > self.rsi_os and c_now > ema_now:
            price = c_now
            sl_d = atr_now * self.sl_atr
            tp_d = atr_now * self.tp_atr
            
            # リスクベースのポジションサイズ
            eq = self.equity
            sz = max(int(round(eq * self.risk_pct / sl_d)), 1)
            # 日本株は通常100株単位
            sz = (sz // 100) * 100
            if sz < 100: sz = 100
            
            # 資金不足チェック
            if sz * price > eq * 0.95:
                sz = int((eq * 0.95 // price) // 100) * 100
            
            if sz >= 100:
                self.buy(size=sz, sl=price - sl_d, tp=price + tp_d)
                
        # SHORT
        elif rsi_prev >= self.rsi_ob and rsi_now < self.rsi_ob and c_now < ema_now:
            price = c_now
            sl_d = atr_now * self.sl_atr
            tp_d = atr_now * self.tp_atr
            
            eq = self.equity
            sz = max(int(round(eq * self.risk_pct / sl_d)), 1)
            sz = (sz // 100) * 100
            if sz < 100: sz = 100
            
            if sz * price > eq * 0.95:
                sz = int((eq * 0.95 // price) // 100) * 100
                
            if sz >= 100:
                self.sell(size=sz, sl=price + sl_d, tp=price - tp_d)
