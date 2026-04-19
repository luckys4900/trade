import talib
import pandas as pd
from backtesting import Strategy

class HyperliquidMicroBreakout(Strategy):
    """
    【プロ仕様】5分足マイクロブレイクアウト戦略
    
    エッジポイント:
    1. ボリンジャーバンドの圧縮（スクイーズ）からの拡大を検知
    2. 出来高急増 + ATR拡大のコンファメーション
    3. メイカー注文での指値エントリー（リベート獲得）
    4. 小さな利幅を高頻度で積み上げ
    
    パフォーマンス目標:
    - 勝率: 62-68%
    - プロフィットファクター: 1.8以上
    - 平均リスクリワード: 1:1.5
    - 1トレードの平均保有時間: 15-45分
    """
    
    # 最適化パラメータ（バックテストで調整）
    bb_period = 20
    bb_std = 2.0
    atr_period = 14
    volume_multiplier = 1.5  # 平均出来高の1.5倍以上
    
    # リスク管理
    risk_per_trade = 0.015  # 1.5%リスク
    profit_target_atr = 2.0  # ATRの2倍で利確
    stop_loss_atr = 1.0      # ATRの1倍で損切
    
    # エントリーフィルター
    min_squeeze_bars = 10    # 最低10本のレンジ継続後
    max_spread_pct = 0.05    # 0.05%以下のスプレッド
    
    def init(self):
        """インジケーター初期化"""
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume
        
        # ボリンジャーバンド
        self.bb_upper = self.I(talib.BBANDS, close, self.bb_period, self.bb_std, self.bb_std)[0]
        self.bb_middle = self.I(talib.BBANDS, close, self.bb_period, self.bb_std, self.bb_std)[1]
        self.bb_lower = self.I(talib.BBANDS, close, self.bb_period, self.bb_std, self.bb_std)[2]
        
        # ATR（真の範囲）
        self.atr = self.I(talib.ATR, high, low, close, self.atr_period)
        
        # 出来高移動平均
        self.volume_ma = self.I(talib.SMA, volume, 20)
        
        # ボリンジャーバンド幅（スクイーズ検知用）
        self.bb_width = self.I(lambda: (self.bb_upper - self.bb_lower) / self.bb_middle * 100)
        
        # RSI（オーバーエクステンション回避）
        self.rsi = self.I(talib.RSI, close, 14)
        
        # EMA（トレンドフィルター）
        self.ema_fast = self.I(talib.EMA, close, 9)
        self.ema_slow = self.I(talib.EMA, close, 21)
    
    def next(self):
        """毎足の実行ロジック"""
        
        # 現在の市場データ
        price = self.data.Close[-1]
        atr_value = self.atr[-1]
        volume_current = self.data.Volume[-1]
        volume_avg = self.volume_ma[-1]
        
        # スプレッドチェック（Hyperliquidは低スプレッド想定）
        spread_pct = (self.data.High[-1] - self.data.Low[-1]) / price
        if spread_pct > self.max_spread_pct:
            return  # スプレッドが広すぎる場合はスキップ
        
        # ボリンジャーバンド幅の履歴
        bb_width_current = self.bb_width[-1]
        bb_width_prev = self.bb_width[-2] if len(self.bb_width) > 1 else bb_width_current
        
        # ポジションがない場合のエントリーロジック
        if not self.position:
            
            # 【ロングエントリー条件】
            long_conditions = [
                # 1. ボリンジャーバンドが拡大開始
                bb_width_current > bb_width_prev,
                # 2. 価格が下部バンドから中央バンドへ反発
                self.data.Close[-2] <= self.bb_lower[-2],
                price > self.bb_lower[-1],
                # 3. 出来高が平均の1.5倍以上
                volume_current > volume_avg * self.volume_multiplier,
                # 4. EMAのトレンド確認（短期 > 長期）
                self.ema_fast[-1] > self.ema_slow[-1],
                # 5. RSIが買われすぎでない
                self.rsi[-1] < 70,
                self.rsi[-1] > 35,  # 極端な売られすぎでもない
            ]
            
            if all(long_conditions):
                # ポジションサイジング（1.5%リスク）
                stop_loss = price - (atr_value * self.stop_loss_atr)
                risk_amount = self.equity * self.risk_per_trade
                position_size = risk_amount / (price - stop_loss)
                
                # 利確目標
                take_profit = price + (atr_value * self.profit_target_atr)
                
                # メイカー注文でエントリー（指値）
                self.buy(
                    size=position_size,
                    sl=stop_loss,
                    tp=take_profit
                )
            
            # 【ショートエントリー条件】
            short_conditions = [
                bb_width_current > bb_width_prev,
                self.data.Close[-2] >= self.bb_upper[-2],
                price < self.bb_upper[-1],
                volume_current > volume_avg * self.volume_multiplier,
                self.ema_fast[-1] < self.ema_slow[-1],
                self.rsi[-1] > 30,
                self.rsi[-1] < 65,
            ]
            
            if all(short_conditions):
                stop_loss = price + (atr_value * self.stop_loss_atr)
                risk_amount = self.equity * self.risk_per_trade
                position_size = risk_amount / (stop_loss - price)
                take_profit = price - (atr_value * self.profit_target_atr)
                
                self.sell(
                    size=position_size,
                    sl=stop_loss,
                    tp=take_profit
                )
        
        # ポジション保有中のトレーリングストップ
        else:
            if self.position.is_long:
                # 利益が出ている場合、損益分岐点までストップを引き上げ
                if price > self.position.entry_price + (atr_value * 1.0):
                    new_sl = self.position.entry_price + (atr_value * 0.3)
                    if new_sl > self.position.sl:
                        self.position.sl = new_sl
            
            elif self.position.is_short:
                if price < self.position.entry_price - (atr_value * 1.0):
                    new_sl = self.position.entry_price - (atr_value * 0.3)
                    if new_sl < self.position.sl:
                        self.position.sl = new_sl