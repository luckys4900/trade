import requests
import pandas as pd
import numpy as np

url = 'https://api.binance.com/api/v3/klines'
params = {'symbol': 'BTCUSDT', 'interval': '4h', 'limit': 200}
resp = requests.get(url, params=params, timeout=15)
data = resp.json()
df = pd.DataFrame(data, columns=['timestamp','open','high','low','close','volume','ct','qav','trades','tbb','tbq','ignore'])
df['datetime'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms', utc=True).dt.tz_localize(None)
for c in ['open','high','low','close','volume']:
    df[c] = df[c].astype(float)

# Remove any zero/NaN closes
df = df[df['close'] > 0].reset_index(drop=True)

print('Total bars: %d' % len(df))
print('Last 3 closes: $%.2f, $%.2f, $%.2f' % (df.iloc[-3]['close'], df.iloc[-2]['close'], df.iloc[-1]['close']))
print()

df['ema_fast'] = df['close'].ewm(span=21, adjust=False).mean()
df['ema_slow'] = df['close'].ewm(span=55, adjust=False).mean()
df['ema_fast_slope'] = df['ema_fast'].pct_change(10)

df['trend'] = 'RANGE'
df.loc[(df['close'] > df['ema_slow']) & (df['ema_fast'] > df['ema_slow']) & (df['ema_fast_slope'] > 0), 'trend'] = 'UPTREND'
df.loc[(df['close'] < df['ema_slow']) & (df['ema_fast'] < df['ema_slow']) & (df['ema_fast_slope'] < 0), 'trend'] = 'DOWNTREND'

delta = df['close'].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(lower=0)).ewm(alpha=1/14, adjust=False).mean()
df['rsi'] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
df['rsi_prev'] = df['rsi'].shift(1)

tr = pd.concat([df['high']-df['low'],(df['high']-df['close'].shift(1)).abs(),(df['low']-df['close'].shift(1)).abs()],axis=1).max(axis=1)
df['atr'] = tr.ewm(alpha=1/14, min_periods=14).mean()

last = df.iloc[-1]
print('Current Price: $%.2f' % last['close'])
print('RSI: %.1f (prev: %.1f)' % (last['rsi'], last['rsi_prev']))
print('Trend: %s' % last['trend'])
print('EMA21: $%.2f' % last['ema_fast'])
print('EMA55: $%.2f' % last['ema_slow'])
print('ATR: $%.2f' % last['atr'])
print()

long_entry = (last['trend'] == 'UPTREND') and (last['rsi_prev'] <= 48.0) and (last['rsi'] > last['rsi_prev']) and (last['rsi'] < 55)
short_entry = (last['trend'] == 'DOWNTREND') and (last['rsi_prev'] >= 52.0) and (last['rsi'] < last['rsi_prev']) and (last['rsi'] > 45)
long_warn = (last['trend'] == 'UPTREND') and (48.0 < last['rsi'] <= 53.0) and (last['rsi'] < 55)
short_warn = (last['trend'] == 'DOWNTREND') and (47.0 <= last['rsi'] < 52.0) and (last['rsi'] > 45)

if long_entry:
    print('>>> LONG ENTRY SIGNAL <<<')
    print('Entry: $%.2f' % last['close'])
    print('SL: $%.2f' % (last['close'] - 3.0 * last['atr']))
    print('TP: $%.2f' % (last['close'] + 6.0 * last['atr']))
elif short_entry:
    print('>>> SHORT ENTRY SIGNAL <<<')
    print('Entry: $%.2f' % last['close'])
    print('SL: $%.2f' % (last['close'] + 3.0 * last['atr']))
    print('TP: $%.2f' % (last['close'] - 6.0 * last['atr']))
elif long_warn:
    print('>> WARNING: LONG approaching (RSI %.1f, need <= 48)' % last['rsi'])
elif short_warn:
    print('>> WARNING: SHORT approaching (RSI %.1f, need >= 52)' % last['rsi'])
else:
    print('No signal. Monitoring...')
    if last['trend'] == 'UPTREND':
        print('  LONG needs RSI to drop to 48 (currently %.1f)' % last['rsi'])
    elif last['trend'] == 'DOWNTREND':
        print('  SHORT needs RSI to rise to 52 (currently %.1f)' % last['rsi'])
    else:
        print('  Trend is RANGE, waiting for direction')
