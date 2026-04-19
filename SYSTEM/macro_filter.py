# -*- coding: utf-8 -*-
"""
Macro Filter - Volatility regime detection and economic calendar awareness
Monitors BTC volatility (ATR ratio) and upcoming economic events
"""

import os, sys, json, time, logging, argparse, csv
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import requests
import numpy as np

# ==================================================================
# LOGGER SETUP
# ==================================================================

def setup_logger(log_dir="logs", name="macro_filter"):
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{name}_{ts}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# ==================================================================
# MACRO FILTER
# ==================================================================

class MacroFilter:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, output_path="macro_state.json",
                 calendar_path="economic_calendar.csv",
                 log_dir="logs"):
        self.output_path = output_path
        self.calendar_path = calendar_path
        self.logger = setup_logger(log_dir, "macro_filter")
        self.last_macro_state = None

    def _raw_post(self, payload: dict, timeout: int = 10) -> Optional[dict]:
        """POST to Hyperliquid info endpoint"""
        try:
            resp = requests.post(self.HL_API_URL, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                self.logger.warning(f"HL API returned {resp.status_code}")
                return None
        except Exception as e:
            self.logger.warning(f"HL API error: {e}")
            return None

    def fetch_btc_candles(self, n_bars: int = 30, interval: str = "4h") -> List[dict]:
        """
        Fetch BTC candles using candleSnapshot POST.
        Pattern from hl_rsi_swing_v6.py
        """
        now_ms = int(time.time() * 1000)
        # 4h interval = 4*60*60*1000 ms per bar
        interval_ms = {'1m': 60000, '5m': 300000, '15m': 900000, '1h': 3600000,
                       '4h': 14400000, '1d': 86400000}
        step = interval_ms.get(interval, 14400000)
        start_ms = now_ms - (n_bars * step)

        payload = {
            'type': 'candleSnapshot',
            'req': {
                'coin': 'BTC',
                'interval': interval,
                'startTime': int(start_ms),
                'endTime': int(now_ms)
            }
        }

        data = self._raw_post(payload)
        if isinstance(data, list):
            return data
        return []

    def compute_atr_ratio(self, candles: List[dict], period: int = 14) -> Optional[float]:
        """
        Compute ATR(period) / close ratio.
        Wilder's ATR: TR averaged with smoothing.
        """
        if len(candles) < period:
            return None

        # Extract OHLC
        closes = np.array([float(c['c']) for c in candles], dtype=float)
        highs = np.array([float(c['h']) for c in candles], dtype=float)
        lows = np.array([float(c['l']) for c in candles], dtype=float)

        # Compute True Range
        tr = np.zeros(len(candles))
        tr[0] = highs[0] - lows[0]

        for i in range(1, len(candles)):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )

        # Wilder's ATR (Smooth using EMA-like approach)
        atr = tr[:period].mean()
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period

        # Return ratio to current close
        current_close = closes[-1]
        if current_close <= 0:
            return None

        ratio = atr / current_close
        return float(ratio)

    def classify_regime(self, atr_ratio: float) -> str:
        """Classify volatility regime by ATR ratio"""
        if atr_ratio >= 0.07:
            return "EXTREME"
        elif atr_ratio >= 0.04:
            return "HIGH"
        elif atr_ratio >= 0.015:
            return "NORMAL"
        else:
            return "LOW"

    def load_calendar(self) -> List[dict]:
        """Load economic calendar from CSV"""
        if not os.path.exists(self.calendar_path):
            self.logger.warning(f"Calendar file not found: {self.calendar_path}")
            return []

        try:
            events = []
            with open(self.calendar_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        dt_str = row.get('datetime', '')
                        dt = datetime.fromisoformat(dt_str)
                        event = {
                            'datetime': dt,
                            'datetime_str': dt_str,
                            'event': row.get('event', ''),
                            'impact': row.get('impact', 'LOW'),
                            'source': row.get('source', 'manual')
                        }
                        events.append(event)
                    except:
                        pass
            self.logger.info(f"Loaded {len(events)} calendar events")
            return events
        except Exception as e:
            self.logger.error(f"Failed to load calendar: {e}")
            return []

    def check_calendar_caution(self, events: List[dict],
                               window_hours: float = 12.0) -> dict:
        """
        Check if HIGH impact event within ±window_hours of now.
        """
        now = datetime.utcnow()
        caution = False
        next_event = ""
        next_event_name = ""
        hours_to_event = float('inf')

        for ev in events:
            if ev['impact'] != 'HIGH':
                continue

            ev_dt = ev['datetime']
            time_diff = (ev_dt - now).total_seconds() / 3600

            # Within window?
            if abs(time_diff) <= window_hours:
                caution = True

            # Track next event
            if time_diff > 0 and time_diff < hours_to_event:
                next_event = ev['datetime_str']
                next_event_name = ev['event']
                hours_to_event = time_diff

        return {
            'caution_mode': caution,
            'next_event': next_event,
            'next_event_name': next_event_name,
            'hours_to_event': float(hours_to_event) if hours_to_event != float('inf') else -1.0
        }

    def run_once(self) -> dict:
        """Execute one full cycle"""
        self.logger.info("=== Run Once ===")

        # Fetch candles
        candles = self.fetch_btc_candles(n_bars=30, interval='4h')
        if not candles:
            self.logger.warning("No candles fetched, using last known state")
            if self.last_macro_state:
                return self.last_macro_state
            return {
                'regime': 'NORMAL',
                'atr_ratio': 0.025,
                'caution_mode': False,
                'next_event': '',
                'next_event_name': '',
                'hours_to_event': -1.0,
                'timestamp': int(time.time() * 1000),
                'valid': False
            }

        # Compute ATR ratio
        atr_ratio = self.compute_atr_ratio(candles, period=14)
        if atr_ratio is None:
            atr_ratio = 0.025
            regime = 'NORMAL'
        else:
            regime = self.classify_regime(atr_ratio)

        # Check calendar
        events = self.load_calendar()
        cal_state = self.check_calendar_caution(events, window_hours=12.0)

        # Compose state
        state = {
            'regime': regime,
            'atr_ratio': float(atr_ratio),
            'caution_mode': cal_state['caution_mode'],
            'next_event': cal_state['next_event'],
            'next_event_name': cal_state['next_event_name'],
            'hours_to_event': cal_state['hours_to_event'],
            'timestamp': int(time.time() * 1000),
            'valid': True
        }

        self.last_macro_state = state

        # Write
        try:
            tmp_path = self.output_path + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(state, f, indent=2)
            import shutil
            shutil.move(tmp_path, self.output_path)
            self.logger.info(f"State written: regime={state['regime']}, atr={atr_ratio:.4f}, caution={state['caution_mode']}")
        except Exception as e:
            self.logger.error(f"Failed to write state: {e}")

        return state

    def run_loop(self, interval_seconds: int = 3600) -> None:
        """Run continuously"""
        self.logger.info(f"Starting loop with interval {interval_seconds}s (1 hour)")
        while True:
            try:
                self.run_once()
            except Exception as e:
                self.logger.error(f"Cycle error: {e}")

            time.sleep(interval_seconds)

# ==================================================================
# MAIN
# ==================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds")
    args = parser.parse_args()

    filter = MacroFilter()

    if args.once:
        filter.run_once()
    else:
        filter.run_loop(args.interval)
