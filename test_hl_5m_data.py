# -*- coding: utf-8 -*-
"""
Hyperliquid 5分足データ取得確認テスト
"""

import sys
import json
from pathlib import Path

# Hyperliquid SDKのインポート
try:
    from hyperliquid.utils import constants
    from hyperliquid.api import API
    print("[INFO] Hyperliquid SDK imported successfully")
except ImportError as e:
    print(f"[ERROR] Hyperliquid SDK not installed: {e}")
    sys.exit(1)

def test_candles_snapshot():
    """candles_snapshotメソッドで5分足データを取得するテスト"""

    print("\n" + "="*70)
    print(" Hyperliquid 5分足データ取得確認テスト")
    print("="*70)

    # APIクラスを初期化
    print("\n[STEP 1] Initializing Hyperliquid API client...")
    try:
        api = API(base_url=constants.MAINNET_API_URL)
        print("[SUCCESS] API client initialized")
    except Exception as e:
        print(f"[ERROR] Failed to initialize API client: {e}")
        return

    # 5分足データを取得
    coin = "BTC"
    interval = "5m"  # 5分足
    lookback_days = 30

    print(f"\n[STEP 2] Fetching {lookback_days} days of {interval} candles for {coin}...")
    print(f"         This may take a few seconds...")

    try:
        # 現在時刻
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        start_time = now - dt.timedelta(days=lookback_days)

        # ミリ秒形式に変換
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

        print(f"         Start time: {start_time}")
        print(f"         End time: {now}")
        print(f"         Start (ms): {start_ms}")
        print(f"         End (ms): {end_ms}")

        # APIを直接呼び出し
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms
            }
        }

        print(f"         Sending request...")
        response = api.post("/info", payload)

        # レスポンスがリストの場合がある
        if isinstance(response, list):
            candles = response
        else:
            candles = response.get("candles", response.get("data", []))

        print(f"\n[SUCCESS] Successfully fetched {len(candles)} candles")

        if len(candles) == 0:
            print("[WARNING] No candles returned. Check API connectivity.")
            return

        # データの最初の数本を表示
        print("\n[STEP 3] Displaying first 3 candles:")
        print(f"{'#':<5} {'Timestamp (ms)':<20} {'Open':<15} {'High':<15} {'Low':<15} {'Close':<15} {'Volume':<15}")
        print("-" * 100)

        for i in range(min(3, len(candles))):
            candle = candles[i]
            t = candle.get('t', 0)
            o = candle.get('o', 0)
            h = candle.get('h', 0)
            l = candle.get('l', 0)
            c = candle.get('c', 0)
            v = candle.get('v', 0)

            print(f"{i:<5} {t:<20} {o:<15.2f} {h:<15.2f} {l:<15.2f} {c:<15.2f} {v:<15.2f}")

        # データの最後の数本を表示
        print("\n[STEP 4] Displaying last 3 candles:")
        print(f"{'#':<5} {'Timestamp (ms)':<20} {'Open':<15} {'High':<15} {'Low':<15} {'Close':<15} {'Volume':<15}")
        print("-" * 100)

        for i in range(max(0, len(candles)-3), len(candles)):
            candle = candles[i]
            t = candle.get('t', 0)
            o = candle.get('o', 0)
            h = candle.get('h', 0)
            l = candle.get('l', 0)
            c = candle.get('c', 0)
            v = candle.get('v', 0)

            print(f"{i:<5} {t:<20} {o:<15.2f} {h:<15.2f} {l:<15.2f} {c:<15.2f} {v:<15.2f}")

        # データの統計情報
        print("\n[STEP 5] Data Statistics:")
        closes = [candle.get('c', 0) for candle in candles]
        volumes = [candle.get('v', 0) for candle in candles]

        print(f"  Total candles: {len(candles)}")
        print(f"  Date range: {start_time.date()} to {now.date()}")
        print(f"  Price range: ${min(closes):.2f} - ${max(closes):.2f}")
        print(f"  Average close: ${sum(closes)/len(closes):.2f}")
        print(f"  Volume range: {min(volumes):.2f} - {max(volumes):.2f}")
        print(f"  Average volume: {sum(volumes)/len(volumes):.2f}")

        # データの有効性チェック
        print("\n[STEP 6] Data Validation:")
        issues = []

        if len(candles) == 0:
            issues.append("No candles returned")
        else:
            # 日付順のチェック
            timestamps = [candle.get('t', 0) for candle in candles]
            if timestamps != sorted(timestamps):
                issues.append("Timestamps are not in ascending order")

            # 値の範囲チェック（high >= close >= low）
            for i, candle in enumerate(candles):
                h = candle.get('h', 0)
                l = candle.get('l', 0)
                c = candle.get('c', 0)
                o = candle.get('o', 0)

                if not (h >= c >= l and h >= o >= l):
                    issues.append(f"Candle {i}: Invalid range (h={h}, l={l}, c={c}, o={o})")

                if o >= c and candle.get('isAsk', False):
                    # askカラムがある場合のエントリーチェック
                    if not (o >= c):
                        pass  # ask candlesは異なる形式

        if issues:
            print(f"  [ISSUES FOUND]:")
            for issue in issues:
                print(f"    - {issue}")
            return False
        else:
            print(f"  [VALIDATION PASSED] All checks passed!")
            return True

    except Exception as e:
        print(f"\n[ERROR] Failed to fetch candles: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_different_intervals():
    """他の時間足での取得も試す"""
    print("\n" + "="*70)
    print(" Testing other timeframes")
    print("="*70)

    api = API(base_url=constants.MAINNET_API_URL)

    intervals = ["1m", "15m", "1h", "4h", "1d"]

    for interval in intervals:
        print(f"\n[Test] Fetching {interval} candles...")
        try:
            import datetime as dt
            now = dt.datetime.now(dt.timezone.utc)
            start_ms = int((now - dt.timedelta(days=7)).timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)

            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": "BTC",
                    "interval": interval,
                    "startTime": start_ms,
                    "endTime": end_ms
                }
            }

            response = api.post("/info", payload)
            candles = response.get("candles", [])
            print(f"  [SUCCESS] {len(candles)} candles fetched")
        except Exception as e:
            print(f"  [ERROR] Failed for {interval}: {e}")

if __name__ == "__main__":
    result = test_candles_snapshot()

    if result:
        print("\n" + "="*70)
        print(" [RESULT] Data retrieval is working correctly!")
        print("="*70)
    else:
        print("\n" + "="*70)
        print(" [RESULT] Data retrieval has issues. Please check the output above.")
        print("="*70)
