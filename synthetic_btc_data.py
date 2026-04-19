"""
Generate synthetic BTC/USDT data with realistic volatility and trend patterns
for backtesting the volatility breakout strategy.
"""

import numpy as np
import pandas as pd
import datetime as dt


def generate_synthetic_btc_data(num_days=180, seed=42):
    """
    Generate synthetic BTC/USDT 1H data with:
    - Realistic volatility patterns
    - Trend sections
    - Range sections
    - Volatility squeezes
    - Split breakouts

    Parameters:
    -----------
    num_days : int
        Number of days of data to generate
    seed : int
        Random seed for reproducibility

    Returns:
    --------
    df : pd.DataFrame
        DataFrame with OHLCV data and ADX indicator
    """
    np.random.seed(seed)

    num_candles = num_days * 24
    print(f"[DATA] Generating {num_days} days of synthetic BTC data ({num_candles} candles)...")

    # Base parameters
    base_price = 100000.0
    volatility = 0.002  # 0.2% daily volatility
    trend_bias = 0.0005  # Slight upward bias

    # Create date range
    dates = pd.date_range(start='2025-01-01 00:00:00', periods=num_candles, freq='1H')

    # Initialize arrays
    close = np.zeros(num_candles)
    high = np.zeros(num_candles)
    low = np.zeros(num_candles)
    open_price = np.zeros(num_candles)
    volume = np.zeros(num_candles)

    current_price = base_price

    # State variables
    trend = 0  # +1 = bullish, -1 = bearish
    trend_duration = 0

    # Create trend and volatility segments
    for i in range(num_candles):
        # Update trend (randomly change every ~20 days)
        if trend_duration == 0:
            trend = np.random.choice([1, -1], p=[0.6, 0.4])
            trend_duration = np.random.randint(50, 300)  # 2-12 days

        trend_duration -= 1

        # Trend component
        trend_component = trend * trend_bias

        # Volatility component (higher during trends)
        volatility_multiplier = 1.5 if trend != 0 else 1.0
        noise = np.random.normal(0, volatility * volatility_multiplier)

        # Mean reversion for range periods
        if trend == 0 and i > 0:
            mean_reversion = (base_price - current_price) * 0.01
            noise += mean_reversion

        # Random volatility spikes
        spike = 0
        if np.random.random() < 0.005:  # 0.5% chance per candle
            spike = np.random.choice([-1, 1]) * volatility * 3

        # Generate OHLC
        current_price = current_price * (1 + trend_component + noise + spike)

        # Ensure price doesn't go too extreme
        current_price = max(10000, min(current_price, 500000))

        open_price[i] = current_price
        close[i] = current_price * (1 + np.random.normal(0, 0.0002))

        # High/Low
        move = np.abs(np.random.normal(0, volatility * 0.5))
        high[i] = max(current_price, close[i]) + move
        low[i] = min(current_price, close[i]) - move

        # Volume (higher during trends and spikes)
        base_vol = 1000
        vol_factor = 2.0 if trend != 0 else 1.0
        if spike != 0:
            vol_factor *= 3.0
        volume[i] = base_vol * vol_factor * np.random.uniform(0.5, 1.5)

    # Create DataFrame
    df = pd.DataFrame({
        'datetime': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    df.set_index('datetime', inplace=True)

    # Add realistic Squeeze-Breakout patterns
    print(f"[DATA] Injecting volatility squeeze patterns...")
    df = add_squeeze_breakout_patterns(df, num_days=num_days)

    # Calculate ADX
    print(f"[DATA] Calculating ADX...")
    df['adx'] = calculate_adx(df, period=14)

    print(f"[DATA] Generation complete!")
    print(f"  Price range: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")
    print(f"  Volume range: {df['volume'].min():.1f} - {df['volume'].max():.1f}")
    print(f"  ADX range: {df['adx'].min():.2f} - {df['adx'].max():.2f}")
    print(f"  Trading days: {df.index[-1].date()} to {df.index[0].date()}")

    return df


def add_squeeze_breakout_patterns(df, num_days=180):
    """
    Inject volatility squeeze and breakout patterns into the synthetic data.
    This creates realistic entries for the strategy.
    """
    num_candles = len(df)
    volatility = 0.002

    # Find periods where price has been ranging (ADX low, EMA crossover)
    squeeze_regions = []

    for i in range(50, num_candles - 100):
        # Check if current region has low volatility
        adx_recent = df['adx'].iloc[i-50:i].mean()

        if adx_recent < 15:  # Low volatility / ranging
            # Check if EMA50 < EMA200 (could flip to bullish)
            ema50 = df['close'].iloc[i-50:i].ewm(span=50).mean().iloc[-1]
            ema200 = df['close'].iloc[i-50:i].ewm(span=200).mean().iloc[-1]

            if ema50 > ema200:  # Bullish crossover
                # Find potential breakout point (10 candles later)
                breakout_idx = i + np.random.randint(20, 100)

                if breakout_idx < num_candles:
                    # Calculate expected breakout level
                    current_price = df['close'].iloc[i]
                    bb_width_mean = df['close'].iloc[i-50:i].std() * 2

                    # Inject squeeze: reduce volatility in next 20 candles
                    for j in range(i, min(i + 20, num_candles)):
                        vol_factor = 0.3  # 70% reduction in volatility
                        df.at[df.index[j], 'high'] = df.at[df.index[j], 'close'] + bb_width_mean * vol_factor
                        df.at[df.index[j], 'low'] = df.at[df.index[j], 'close'] - bb_width_mean * vol_factor
                        df.at[df.index[j], 'volume'] *= 0.5  # Reduced volume during squeeze

                    # Inject breakout: push price above BB upper
                    if breakout_idx < num_candles:
                        df.at[df.index[breakout_idx], 'close'] = df.at[df.index[breakout_idx], 'close'] * 1.03
                        df.at[df.index[breakout_idx], 'high'] = df.at[df.index[breakout_idx], 'close'] * 1.05
                        df.at[df.index[breakout_idx], 'volume'] *= 3.0  # High volume breakout

                        # Spread impact to next 5 candles
                        for j in range(breakout_idx + 1, min(breakout_idx + 5, num_candles)):
                            df.at[df.index[j], 'close'] *= 1.01
                            df.at[df.index[j], 'volume'] *= 1.5

    return df


def calculate_adx(df, period=14):
    """
    Calculate ADX indicator using numpy.

    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with high, low, close columns
    period : int
        ADX period

    Returns:
    --------
    adx : np.array
        ADX values
    """
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values

    # Calculate True Range (TR)
    tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
    tr[0] = high[0] - low[0]

    # Calculate +DM and -DM
    plus_dm = np.where((high - np.roll(high, 1)) > (np.roll(low, 1) - low),
                       high - np.roll(high, 1), 0)
    minus_dm = np.where((np.roll(low, 1) - low) > (high - np.roll(high, 1)),
                        np.roll(low, 1) - low, 0)
    plus_dm[0] = 0
    minus_dm[0] = 0

    # Smooth the values
    tr_smooth = pd.Series(tr).rolling(window=period).mean().values
    plus_dm_smooth = pd.Series(plus_dm).rolling(window=period).mean().values
    minus_dm_smooth = pd.Series(minus_dm).rolling(window=period).mean().values

    # Calculate DI+ and DI-
    di_plus = 100 * (plus_dm_smooth / tr_smooth)
    di_minus = 100 * (minus_dm_smooth / tr_smooth)

    # Calculate DX
    dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus)

    # Smooth DX to get ADX
    adx = pd.Series(dx).rolling(window=period).mean().values

    return adx


def generate_multiple_scenarios():
    """
    Generate multiple synthetic data scenarios for robust testing.
    """
    scenarios = []

    for seed in [42, 123, 456, 789, 101112]:
        print(f"\n[SCENARIO {seed}] Generating scenario...")
        df = generate_synthetic_btc_data(num_days=180, seed=seed)
        scenarios.append(df)
        print(f"[SCENARIO {seed}] Done.")

    return scenarios


if __name__ == '__main__':
    # Generate single scenario
    print("=" * 70)
    print(" BTC/USDT Synthetic Data Generator")
    print("=" * 70)

    df = generate_synthetic_btc_data(num_days=180, seed=42)

    print(f"\n[INFO] Data saved to btc_usdt_1h.csv")
    df.to_csv('btc_usdt_1h.csv')
    print(f"[INFO] {len(df)} candles saved.")
