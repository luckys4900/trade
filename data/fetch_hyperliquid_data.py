import hyperliquid
from hyperliquid.utils import constants
import pandas as pd
from datetime import datetime, timedelta
import time
import talib
from pathlib import Path

class HyperliquidDataFetcher:
    """Hyperliquidから5分足OHLCVデータを取得"""
    
    def __init__(self, symbol='BTC'):
        self.symbol = symbol
        # Hyperliquid Info APIの初期化
        self.info = hyperliquid.info.Info(constants.MAINNET_API_URL)
    
    def fetch_candles(self, interval='5m', start_time=None, end_time=None):
        """
        ローソク足データ取得
        
        Parameters:
        -----------
        interval : str
            '1m', '5m', '15m', '1h', '4h', '1d'
        start_time : datetime
            開始時刻
        end_time : datetime
            終了時刻
        
        Returns:
        --------
        pd.DataFrame : OHLCV + indicators
        """
        
        if start_time is None:
            start_time = datetime.now() - timedelta(days=365)
        if end_time is None:
            end_time = datetime.now()
        
        all_candles = []
        current_time = start_time
        
        print(f"📊 {self.symbol} {interval}足データ取得開始...")
        
        while current_time < end_time:
            try:
                # Hyperliquid APIでキャンドルデータ取得
                candles = self.info.candles_snapshot(
                    coin=self.symbol,
                    interval=interval,
                    start_time=int(current_time.timestamp() * 1000),
                    end_time=int((current_time + timedelta(days=7)).timestamp() * 1000)
                )
                
                if candles:
                    all_candles.extend(candles)
                    print(f"✓ {current_time.strftime('%Y-%m-%d')} - {len(candles)}本取得")
                
                current_time += timedelta(days=7)
                time.sleep(0.5)  # レート制限回避
                
            except Exception as e:
                print(f"❌ エラー: {e}")
                time.sleep(2)
                continue
        
        # DataFrameに変換
        df = pd.DataFrame(all_candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        ])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # 数値型に変換
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        print(f"\n✅ 取得完了: {len(df)}本")
        print(f"期間: {df.index[0]} ～ {df.index[-1]}")
        
        return df
    
    def add_technical_indicators(self, df):
        """テクニカル指標を追加"""
        # 基本的な指標
        df['SMA_20'] = talib.SMA(df['close'], 20)
        df['EMA_9'] = talib.EMA(df['close'], 9)
        df['EMA_21'] = talib.EMA(df['close'], 21)
        df['EMA_50'] = talib.EMA(df['close'], 50)
        
        # RSI
        df['RSI_9'] = talib.RSI(df['close'], 9)
        df['RSI_14'] = talib.RSI(df['close'], 14)
        
        # ボリンジャーバンド
        df['BB_Upper'], df['BB_Middle'], df['BB_Lower'] = talib.BBANDS(
            df['close'], timeperiod=20, nbdevup=2, nbdevdn=2
        )
        
        # ATR
        df['ATR'] = talib.ATR(df['high'], df['low'], df['close'], 14)
        
        # MACD
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = talib.MACD(
            df['close'], fastperiod=12, slowperiod=26, signalperiod=9
        )
        
        # 出来高移動平均
        df['Volume_MA'] = talib.SMA(df['volume'], 20)
        
        return df.dropna()


# 実行例
if __name__ == "__main__":
    # ディレクトリ作成
    Path("./data/raw").mkdir(parents=True, exist_ok=True)
    
    fetcher = HyperliquidDataFetcher(symbol='BTC')
    
    # 2023年1月から現在まで
    start = datetime(2023, 1, 1)
    df = fetcher.fetch_candles(interval='5m', start_time=start)
    
    # テクニカル指標追加
    df = fetcher.add_technical_indicators(df)
    
    # CSV保存
    df.to_csv('./data/raw/BTC_5m_hyperliquid.csv')
    print("💾 データ保存完了")