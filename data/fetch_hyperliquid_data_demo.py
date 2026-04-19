import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib
from pathlib import Path

# Hyperliquidからデータを取得できない場合のデモデータ生成
def generate_demo_data():
    """デモ用のBTC 5分足データを生成"""
    print("デモデータを生成中...")
    
    # 開始日から現在までの5分足データを生成
    start_date = datetime(2023, 1, 1)
    end_date = datetime.now()
    
    # 5分間隔で日付を生成
    date_range = pd.date_range(start=start_date, end=end_date, freq='5min')
    
    # 乱数シードを設定（再現性のため）
    np.random.seed(42)
    
    # 初期価格（2023年初頭のBTC価格）
    initial_price = 16500
    
    # 価格データ生成（ランダムウォーク + トレンド）
    returns = np.random.normal(0.0005, 0.01, len(date_range))  # 5分足リターン
    prices = [initial_price]
    
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # OHLCVデータ生成
    close_prices = np.array(prices)
    high_prices = close_prices * (1 + np.random.uniform(0, 0.005, len(date_range)))
    low_prices = close_prices * (1 - np.random.uniform(0, 0.005, len(date_range)))
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = initial_price
    
    # 出来高データ生成
    volumes = np.random.lognormal(10, 1, len(date_range))
    
    # DataFrame作成
    df = pd.DataFrame({
        'timestamp': date_range,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volumes
    })
    
    # タイムスタンプをインデックスに設定
    df.set_index('timestamp', inplace=True)
    
    # テクニカル指標を追加
    df = add_technical_indicators(df)
    
    # データを保存
    Path("./data/raw").mkdir(parents=True, exist_ok=True)
    df.to_csv('./data/raw/BTC_5m_hyperliquid.csv')
    
    print(f"\nデモデータ生成完了: {len(df)}本")
    print(f"期間: {df.index[0]} ～ {df.index[-1]}")
    
    return df

def add_technical_indicators(df):
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

if __name__ == "__main__":
    generate_demo_data()