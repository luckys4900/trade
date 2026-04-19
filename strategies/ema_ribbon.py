import talib
import pandas as pd
from backtesting import Strategy

class EMA_Ribbon_VolumeSpike(Strategy):
    """
    【トレンド相場専用】EMAリボン + 出来高スパイク戦略
    
    特徴:
    - 複数EMAの配列でトレンド強度を判定
    - 出来高スパイクでモメンタム確認
    - プルバック（押し目・戻り目）でエントリー
    
    目標:
    - 勝率: 60-65%
    - リスクリワード: 1:2.5
    - 1日3-8回の厳選エントリー
    """
    
    # EMAリボン
    ema_fast = 5
    ema_mid1 = 10
    ema_mid2 = 20
    ema_slow = 50
    
    # 出来高
    volume_spike_multiplier = 2.0
    volume_ma_period = 20
    
    # リスク管理
    stop_loss_pct = 0.008  # 0.8%
    take_profit_pct = 0.020  # 2.0%（1:2.5のRR）
    
    def init(self):
        close = self.data.Close
        volume = self.data.Volume
        
        # EMAリボン
        self.ema5 = self.I(talib.EMA, close, self.ema_fast)
        self.ema10 = self.I(talib.EMA, close, self.ema_mid1)
        self.ema20 = self.I(talib.EMA, close, self.ema_mid2)
        self.ema50 = self.I(talib.EMA, close, self.ema_slow)
        
        # 出来高
        self.volume_ma = self.I(talib.SMA, volume, self.volume_ma_period)
        
        # ATR
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, close, 14)
    
    def next(self):
        price = self.data.Close[-1]
        volume = self.data.Volume[-1]
        
        # パーフェクトオーダーチェック
        long_trend = (self.ema5[-1] > self.ema10[-1] > self.ema20[-1] > self.ema50[-1])
        short_trend = (self.ema5[-1] < self.ema10[-1] < self.ema20[-1] < self.ema50[-1])
        
        # 出来高スパイク
        volume_spike = volume > self.volume_ma[-1] * self.volume_spike_multiplier
        
        if not self.position:
            
            # ロングエントリー（押し目買い）
            if (long_trend and
                volume_spike and
                self.data.Close[-2] < self.ema20[-2] and  # 前足でEMA20タッチ
                price > self.ema20[-1]):  # 現足で反発
                
                stop_loss = price * (1 - self.stop_loss_pct)
                take_profit = price * (1 + self.take_profit_pct)
                
                self.buy(
                    sl=stop_loss,
                    tp=take_profit
                )
            
            # ショートエントリー（戻り売り）
            elif (short_trend and
                  volume_spike and
                  self.data.Close[-2] > self.ema20[-2] and
                  price < self.ema20[-1]):
                
                stop_loss = price * (1 + self.stop_loss_pct)
                take_profit = price * (1 - self.take_profit_pct)
                
                self.sell(
                    sl=stop_loss,
                    tp=take_profit
                )
        
        # トレーリングストップ（利益が出たら損益分岐点に移動）
        else:
            if self.position.is_long and price > self.position.entry_price * 1.01:
                self.position.sl = self.position.entry_price * 1.002
            elif self.position.is_short and price < self.position.entry_price * 0.99:
                self.position.sl = self.position.entry_price * 0.998