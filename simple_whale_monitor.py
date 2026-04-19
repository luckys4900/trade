# -*- coding: utf-8 -*-
"""
Simple Whale Position Monitor - Position-based signal generation
Monitors current open positions of whale wallets to generate consensus signals
"""

import os, sys, json, time, logging, argparse, requests
from datetime import datetime
from typing import Optional, List, Dict

# Force UTF-8 on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_logger(log_dir="logs", name="simple_whale_monitor"):
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

class SimpleWhaleMonitor:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, config_path="whale_wallets.json",
                 output_path="whale_signal.json",
                 log_dir="logs"):
        self.config_path = config_path
        self.output_path = output_path
        self.logger = setup_logger(log_dir, "simple_whale_monitor")
        self.config = self._load_config()

    def _load_config(self) -> dict:
        try:
            with open(self.config_path) as f:
                cfg = json.load(f)
            self.logger.info(f"Loaded config: {len(cfg.get('wallets', []))} wallets")
            return cfg
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {"wallets": [], "scoring_config": {}, "consensus_config": {}}

    def _raw_post(self, payload: dict, timeout: int = 10) -> Optional[dict]:
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

    def get_current_positions(self, wallet: str) -> List[dict]:
        """Get current open positions for a wallet"""
        payload = {'type': 'clearinghouseState', 'user': wallet}
        state = self._raw_post(payload)

        if not state:
            return []

        positions = state.get('assetPositions', [])
        active_positions = []

        for pos in positions:
            pos_info = pos.get('position', {})
            szi = float(pos_info.get('szi', 0))

            if abs(szi) > 0.000001:  # Has active position
                size_usd = float(pos_info.get('positionValue', 0))
                entry_px = float(pos_info.get('entryPx', 0))
                unrealized_pnl = float(pos_info.get('unrealizedPnl', 0))

                active_positions.append({
                    'coin': pos_info.get('position', {}).get('coin', ''),
                    'size': szi,
                    'size_usd': size_usd,
                    'entry_px': entry_px,
                    'unrealized_pnl': unrealized_pnl,
                    'direction': 'LONG' if szi > 0 else 'SHORT'
                })

        return active_positions

    def analyze_wallet_positions(self, wallet: str) -> Optional[dict]:
        """Analyze wallet's recent trading activity"""
        # Get current state
        state = self._get_state(wallet)
        if not state:
            return None

        # Get recent fills (last 7 days)
        fills = self._get_recent_fills(wallet, days=7)

        # Filter BTC fills
        btc_fills = [f for f in fills if f.get('coin') == 'BTC']

        # Count BTC trades
        btc_trades = len(btc_fills)

        # Get account value
        margin = state.get('marginSummary', {})
        account_value = float(margin.get('accountValue', 0))

        # Analyze recent trading direction (last 48 hours)
        end_time = int(time.time() * 1000)
        start_time = end_time - (48 * 60 * 60 * 1000)

        recent_fills = [f for f in btc_fills if start_time <= f.get('time', 0) <= end_time]

        # Determine direction bias from recent fills
        recent_bias = 'NONE'
        if recent_fills:
            buy_fills = [f for f in recent_fills if f.get('side') == 'B']
            sell_fills = [f for f in recent_fills if f.get('side') == 'A']

            if len(buy_fills) > len(sell_fills) * 1.2:
                recent_bias = 'LONG'
            elif len(sell_fills) > len(buy_fills) * 1.2:
                recent_bias = 'SHORT'
            else:
                recent_bias = 'NONE'

        # Check if recently active (has BTC fills in last 7 days)
        is_recently_active = btc_trades >= 5

        # Get current BTC position
        positions = state.get('assetPositions', [])
        btc_position = next((p for p in positions if p.get('position', {}).get('coin', '') == 'BTC'), None)

        has_btc_position = btc_position is not None
        current_direction = None

        if has_btc_position:
            pos_info = btc_position.get('position', {})
            szi = float(pos_info.get('szi', 0))
            current_direction = 'LONG' if szi > 0 else 'SHORT' if szi < 0 else None

        # Use current position if exists, otherwise use recent bias
        final_direction = current_direction if current_direction else recent_bias

        return {
            'address': wallet,
            'account_value': account_value,
            'btc_trades_7d': btc_trades,
            'is_recently_active': is_recently_active,
            'has_btc_position': has_btc_position,
            'current_direction': current_direction,
            'recent_bias': recent_bias,
            'final_direction': final_direction,
            'recent_buys': len([f for f in recent_fills if f.get('side') == 'B']),
            'recent_sells': len([f for f in recent_fills if f.get('side') == 'A']),
            'positions_count': len(positions)
        }

    def _get_state(self, wallet: str) -> Optional[dict]:
        payload = {'type': 'clearinghouseState', 'user': wallet}
        return self._raw_post(payload)

    def _get_recent_fills(self, wallet: str, days: int = 7) -> List[dict]:
        end_time = int(time.time() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)

        payload = {
            'type': 'userFillsByTime',
            'user': wallet,
            'startTime': start_time,
            'endTime': end_time
        }

        data = self._raw_post(payload)
        return data if isinstance(data, list) else []

    def generate_consensus_signal(self, wallets: List[dict]) -> dict:
        """Generate consensus signal from recent trading activity"""
        # Filter for qualified wallets
        qualified = [
            w for w in wallets
            if w.get('is_recently_active', False) and
               w.get('final_direction') in ['LONG', 'SHORT']
        ]

        if not qualified:
            return {
                'direction': 'NONE',
                'strength': 0.0,
                'wallet_count': 0,
                'n_ranked': len(wallets),
                'avg_sortino': 0.0,
                'timestamp': int(time.time() * 1000),
                'valid': False,
                'message': 'No qualified wallets with recent BTC trading activity'
            }

        # Count directions
        long_count = sum(1 for w in qualified if w['final_direction'] == 'LONG')
        short_count = sum(1 for w in qualified if w['final_direction'] == 'SHORT')

        # Determine direction
        config = self.config.get('consensus_config', {})
        min_agreeing = config.get('min_agreeing_wallets', 2)
        min_agreement_pct = config.get('min_agreement_pct', 0.5)

        direction = 'NONE'
        if long_count >= min_agreeing and long_count >= len(qualified) * min_agreement_pct:
            direction = 'LONG'
        elif short_count >= min_agreeing and short_count >= len(qualified) * min_agreement_pct:
            direction = 'SHORT'

        # Calculate strength
        n_wallets = len(qualified)
        strength = 0.0
        if direction != 'NONE':
            strength = n_wallets / len(wallets)  # Simple strength metric

        return {
            'direction': direction,
            'strength': strength,
            'wallet_count': n_wallets,
            'n_ranked': len(wallets),
            'long_count': long_count,
            'short_count': short_count,
            'avg_sortino': 0.0,  # Position-based monitor doesn't calculate Sortino
            'timestamp': int(time.time() * 1000),
            "valid": direction != 'NONE'
        }

        # Count directions
        long_count = sum(1 for w in qualified if w['btc_direction'] == 'LONG')
        short_count = sum(1 for w in qualified if w['btc_direction'] == 'SHORT')

        # Determine direction
        config = self.config.get('consensus_config', {})
        min_agreeing = config.get('min_agreeing_wallets', 2)
        min_agreement_pct = config.get('min_agreement_pct', 0.5)

        direction = 'NONE'
        if long_count >= min_agreeing and long_count >= len(qualified) * min_agreement_pct:
            direction = 'LONG'
        elif short_count >= min_agreeing and short_count >= len(qualified) * min_agreement_pct:
            direction = 'SHORT'

        # Calculate strength
        n_wallets = len(qualified)
        strength = 0.0
        if direction != 'NONE':
            strength = n_wallets / len(wallets)  # Simple strength metric

        return {
            'direction': direction,
            'strength': strength,
            'wallet_count': n_wallets,
            'n_ranked': len(wallets),
            'long_count': long_count,
            'short_count': short_count,
            'avg_sortino': 0.0,  # Position-based monitor doesn't calculate Sortino
            'timestamp': int(time.time() * 1000),
            'valid': direction != 'NONE'
        }

    def run_once(self):
        """Run one monitoring cycle"""
        self.logger.info("=== Simple Whale Position Monitor ===")

        wallets_config = self.config.get('wallets', [])
        active_wallets = [w for w in wallets_config if w.get('active', True)]

        if not active_wallets:
            self.logger.warning("No active wallets configured")
            return

        # Analyze each wallet
        wallet_analyses = []
        for wallet_config in active_wallets:
            address = wallet_config['address']
            label = wallet_config.get('label', address[:8])

            self.logger.info(f"Analyzing {label} ({address[:16]}...)...")

            analysis = self.analyze_wallet_positions(address)
            if analysis:
                analysis['label'] = label
                wallet_analyses.append(analysis)

                self.logger.info(
                    f"  BTC Trades (7d): {analysis['btc_trades_7d']}, "
                    f"Active: {analysis['is_recently_active']}, "
                    f"Current: {analysis['current_direction']}, "
                    f"Recent Bias: {analysis['recent_bias']}, "
                    f"Final: {analysis['final_direction']}"
                )
            else:
                self.logger.debug(f"  No data available")

        # Generate consensus signal
        signal = self.generate_consensus_signal(wallet_analyses)

        # Save signal
        with open(self.output_path, 'w') as f:
            json.dump(signal, f, indent=2)

        # Log signal
        self.logger.info(f"\nSignal generated:")
        self.logger.info(f"  Direction: {signal['direction']}")
        self.logger.info(f"  Strength: {signal['strength']:.2f}")
        self.logger.info(f"  Wallets: {signal['wallet_count']} / {signal['n_ranked']}")
        self.logger.info(f"  Valid: {signal['valid']}")
        if signal.get('long_count') is not None:
            self.logger.info(f"  LONG: {signal['long_count']}, SHORT: {signal['short_count']}")

        return signal

def main():
    parser = argparse.ArgumentParser(description="Simple whale position monitor")
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    args = parser.parse_args()

    monitor = SimpleWhaleMonitor()

    if args.once:
        monitor.run_once()
    else:
        # Run continuously
        interval = 60 * 15  # 15 minutes
        monitor.logger.info(f"Starting continuous monitoring (interval: {interval}s)")

        while True:
            try:
                monitor.run_once()
            except Exception as e:
                monitor.logger.error(f"Error in monitoring cycle: {e}")

            time.sleep(interval)

if __name__ == "__main__":
    main()
