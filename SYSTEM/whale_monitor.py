# -*- coding: utf-8 -*-
"""
Whale Wallet Monitor - Sortino-based ranking and consensus signal generation
Monitors top whale wallets, scores them, and generates alignment signals for main bot
"""

import os, sys, json, time, logging, argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import requests
import numpy as np

# ==================================================================
# LOGGER SETUP
# ==================================================================

def setup_logger(log_dir="logs", name="whale_monitor"):
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
# WHALE MONITOR
# ==================================================================

class WhaleMonitor:
    HL_API_URL = "https://api.hyperliquid.xyz/info"

    def __init__(self, config_path="whale_wallets.json",
                 output_path="whale_signal.json",
                 cache_path="whale_ranking_cache.json",
                 log_dir="logs"):
        self.config_path = self._resolve_path(config_path)
        self.output_path = output_path
        self.cache_path = cache_path
        self.logger = setup_logger(log_dir, "whale_monitor")
        self.config = self._load_config()

    def _resolve_path(self, path_str: str) -> str:
        """Resolve relative config path from CWD first, then script directory."""
        path = Path(path_str)
        if path.is_absolute():
            return str(path)

        if path.exists():
            return str(path)

        script_relative = Path(__file__).resolve().parent / path
        return str(script_relative)

    def _load_config(self) -> dict:
        """Load whale_wallets.json configuration"""
        try:
            with open(self.config_path) as f:
                cfg = json.load(f)
            self.logger.info(f"Loaded config: {len(cfg.get('wallets', []))} wallets")
            return cfg
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {"wallets": [], "scoring_config": {}, "consensus_config": {}}

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

    def fetch_fills_by_time(self, wallet: str, start_time_ms: int) -> List[dict]:
        """
        Fetch wallet fills with server-side time filtering
        API supports optional startTime parameter
        """
        payload = {
            "type": "userFills",
            "user": wallet,
            "startTime": start_time_ms
        }
        data = self._raw_post(payload)
        if isinstance(data, list):
            return data
        return []

    def _pair_fills_to_trades(self, fills: List[dict]) -> List[dict]:
        """
        Convert fills (individual events) to closed trades.
        Pairs entry and exit fills by tracking net size per coin.
        """
        if not fills:
            return []

        # Group fills by coin
        by_coin = {}
        for f in fills:
            coin = f.get('coin', '')
            if coin not in by_coin:
                by_coin[coin] = []
            by_coin[coin].append(f)

        trades = []
        for coin, coin_fills in by_coin.items():
            # Sort chronologically
            coin_fills.sort(key=lambda x: x.get('time', 0))

            # Track net size; when it crosses zero, a trade closes
            net_sz = 0.0
            entry_px = None
            entry_sz = None
            entry_side = None

            for fill in coin_fills:
                side = fill.get('side', '')  # 'A' (ask/sell) or 'B' (bid/buy)
                sz = float(fill.get('sz', 0))
                px = float(fill.get('px', 0))
                pnl_per = float(fill.get('closedPnl', 0)) if entry_sz else 0

                if entry_sz is None:
                    # First fill = entry
                    entry_px = px
                    entry_sz = sz
                    entry_side = side
                    net_sz = sz if side == 'B' else -sz
                else:
                    # Closing fill?
                    if side != entry_side:
                        # Opposite direction
                        prev_sz = net_sz
                        net_sz -= sz if side == 'B' else -sz  # net reduces

                        if prev_sz * net_sz <= 0:  # crossed zero
                            # Trade closed
                            exit_px = px
                            pnl_pct = ((exit_px - entry_px) / entry_px) * 100.0 if entry_px > 0 else 0
                            if entry_side == 'A':
                                pnl_pct = -pnl_pct  # flip for short

                            trades.append({
                                'coin': coin,
                                'direction': 'LONG' if entry_side == 'B' else 'SHORT',
                                'entry_px': entry_px,
                                'exit_px': exit_px,
                                'entry_sz': entry_sz,
                                'exit_sz': sz,
                                'pnl_pct': pnl_pct,
                                'pnl_abs': pnl_per,
                                'win': pnl_pct > 0,
                                'entry_time': fill.get('time', 0)
                            })

                            # Reset for next trade
                            entry_px = None
                            entry_sz = None
                            entry_side = None
                            net_sz = 0.0

        return trades

    def _compute_sortino(self, returns: List[float], period_days: int = 90) -> float:
        """
        Compute annualized Sortino ratio from per-trade returns (in %).
        Sortino only penalizes downside volatility.
        Uses actual trade frequency for annualization: sqrt(trades_per_year)
        """
        if not returns or len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns, dtype=float)
        mean_ret = np.mean(returns_arr)
        n_trades = len(returns_arr)

        # Annualization based on actual trade frequency
        trades_per_year = (n_trades / max(period_days, 1)) * 252
        annualization = np.sqrt(max(trades_per_year, 1))

        # Downside volatility: std of returns < 0
        downside = returns_arr[returns_arr < 0]
        if len(downside) == 0:
            # No losses = perfect return, cap at reasonable value
            return min(mean_ret / 0.1 * annualization, 10.0)

        downside_vol = np.std(downside)
        if downside_vol <= 0:
            return 0.0

        # Sortino = mean / downside_vol * annualization_factor
        sortino = (mean_ret / downside_vol) * annualization
        return float(sortino)

    def compute_wallet_metrics(self, fills: List[dict]) -> Optional[dict]:
        """
        Compute Sortino, win rate, EV from fills.
        Returns None if insufficient trades.
        """
        min_trades = self.config.get('scoring_config', {}).get('min_trades', 10)

        trades = self._pair_fills_to_trades(fills)
        if len(trades) < min_trades:
            return None

        returns = [t['pnl_pct'] for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        win_rate = len(wins) / len(returns) if returns else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0

        # Calculate period for Sortino annualization
        period_days = (datetime.utcnow() - datetime.utcfromtimestamp(trades[0]['entry_time']/1000)).days if trades else 90
        period_days = max(period_days, 1)

        sortino = self._compute_sortino(returns, period_days=period_days)
        ev = (win_rate * avg_win - (1 - win_rate) * avg_loss) / 100.0  # back to fraction

        return {
            'sortino': float(sortino),
            'win_rate': float(win_rate),
            'avg_win_pct': float(avg_win),
            'avg_loss_pct': float(avg_loss),
            'trade_count': len(trades),
            'ev': float(ev),
            'period_days': period_days
        }

    def score_wallets(self) -> List[dict]:
        """
        Fetch fills for all active wallets, compute metrics, filter by thresholds.
        Uses cache for rescore_interval_hours to avoid repeated API calls.
        """
        lookback_days = self.config.get('scoring_config', {}).get('lookback_days', 90)
        min_sortino = self.config.get('scoring_config', {}).get('min_sortino', 0.5)
        min_win_rate = self.config.get('scoring_config', {}).get('min_win_rate', 0.45)
        min_aum = self.config.get('scoring_config', {}).get('min_account_value', 0)
        max_aum = self.config.get('scoring_config', {}).get('max_account_value', float('inf'))
        rescore_hours = self.config.get('scoring_config', {}).get('rescore_interval_hours', 168)

        # Check cache
        ranked = []
        cache_valid = False
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path) as f:
                    cache = json.load(f)
                    cache_age_h = (time.time() - cache.get('timestamp', 0)) / 3600
                    if cache_age_h < rescore_hours:
                        ranked = cache.get('ranked_wallets', [])
                        cache_valid = True
                        self.logger.info(f"Using cached ranking ({cache_age_h:.1f}h old)")
            except:
                pass

        if cache_valid:
            return ranked

        # Rescore all wallets
        start_ms = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp() * 1000)
        wallets_cfg = self.config.get('wallets', [])

        scored = []
        for w_cfg in wallets_cfg:
            if not w_cfg.get('active', False):
                continue

            addr = w_cfg.get('address', '')
            label = w_cfg.get('label', 'unknown')

            # Check AUM first
            if min_aum > 0 or max_aum < float('inf'):
                acct = self._raw_post({'type': 'clearinghouseState', 'user': addr})
                if acct:
                    aum = float(acct.get('marginSummary', {}).get('accountValue', 0))
                    if not (min_aum <= aum <= max_aum):
                        self.logger.debug(f"{label}: AUM ${aum:,.0f} outside range [$${min_aum:,.0f} - ${max_aum:,.0f}]")
                        continue

            fills = self.fetch_fills_by_time(addr, start_ms)
            metrics = self.compute_wallet_metrics(fills)

            if metrics is None:
                # Use default neutral metrics for wallets without sufficient closed trades
                # Real performance will be measured during live trading via alignment log
                metrics = {
                    'sortino': 0.0,
                    'win_rate': 0.5,
                    'trade_count': len(fills) // 2,  # Estimate from fill count
                    'ev': 0.0
                }
                self.logger.debug(f"{label}: Using default metrics ({len(fills)} fills, trade count estimated)")

            if metrics['win_rate'] < min_win_rate:
                self.logger.debug(f"{label}: win_rate {metrics['win_rate']:.1%} < {min_win_rate:.0%}")
                continue

            if metrics['sortino'] < min_sortino:
                self.logger.debug(f"{label}: sortino {metrics['sortino']:.2f} < {min_sortino}")
                continue

            scored.append({
                'address': addr,
                'label': label,
                'sortino': metrics['sortino'],
                'win_rate': metrics['win_rate'],
                'trade_count': metrics['trade_count'],
                'ev': metrics['ev'],
                'qualified': True
            })
            self.logger.info(f"{label}: sortino={metrics['sortino']:.2f}, wr={metrics['win_rate']:.1%}, trades={metrics['trade_count']}, ev={metrics['ev']:.4f}")

        # Sort by Sortino descending
        ranked = sorted(scored, key=lambda x: x['sortino'], reverse=True)

        # Cache
        try:
            cache = {
                'timestamp': time.time(),
                'ranked_wallets': ranked
            }
            with open(self.cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
        except:
            pass

        return ranked

    def get_current_positions(self, wallets: List[str]) -> dict:
        """
        Get current positions for list of wallets via clearinghouseState
        """
        positions = {}
        symbols = self.config.get('symbols_to_track', ['BTC'])

        for wallet in wallets:
            payload = {'type': 'clearinghouseState', 'user': wallet}
            data = self._raw_post(payload)

            if not data:
                positions[wallet] = {}
                continue

            positions[wallet] = {}
            asset_pos = data.get('assetPositions', [])
            for ap in asset_pos:
                pos = ap.get('position', {})
                coin = pos.get('coin', '')
                if coin not in symbols:
                    continue

                szi = float(pos.get('szi', 0))
                if szi > 0:
                    positions[wallet][coin] = 'LONG'
                elif szi < 0:
                    positions[wallet][coin] = 'SHORT'

        return positions

    def compute_consensus(self, ranked_wallets: List[dict],
                          positions: dict, symbol: str = 'BTC') -> dict:
        """
        Compute consensus signal from ranked wallets' current positions.
        """
        min_wallets = self.config.get('consensus_config', {}).get('min_agreeing_wallets', 3)
        min_pct = self.config.get('consensus_config', {}).get('min_agreement_pct', 0.60)
        norm_cap = self.config.get('scoring_config', {}).get('sortino_normalization_cap', 3.0)

        longs = []
        shorts = []

        for w in ranked_wallets:
            addr = w['address']
            if addr not in positions:
                continue

            dir = positions[addr].get(symbol)
            if dir == 'LONG':
                longs.append(w)
            elif dir == 'SHORT':
                shorts.append(w)

        # Determine direction
        direction = 'NONE'
        agreeing = []
        n_ranked = max(len(ranked_wallets), 1)

        if len(longs) >= min_wallets and (len(longs) / n_ranked) >= min_pct and len(longs) > len(shorts):
            direction = 'LONG'
            agreeing = longs
        elif len(shorts) >= min_wallets and (len(shorts) / n_ranked) >= min_pct and len(shorts) > len(longs):
            direction = 'SHORT'
            agreeing = shorts

        # Compute strength
        strength = 0.0
        if agreeing:
            avg_sortino = np.mean([w['sortino'] for w in agreeing])
            strength = (len(agreeing) / n_ranked) * (avg_sortino / norm_cap)
            strength = min(strength, 1.0)

        return {
            'direction': direction,
            'strength': float(strength),
            'wallet_count': len(agreeing),
            'n_ranked': len(ranked_wallets),
            'avg_sortino': float(np.mean([w['sortino'] for w in agreeing])) if agreeing else 0.0,
            'timestamp': int(time.time() * 1000),
            'valid': direction != 'NONE'
        }

    def write_signal(self, signal: dict) -> None:
        """Atomic write to whale_signal.json"""
        try:
            tmp_path = self.output_path + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(signal, f, indent=2)
            # Atomic rename
            import shutil
            shutil.move(tmp_path, self.output_path)
            self.logger.info(f"Signal written: {signal['direction']}, strength={signal['strength']:.2f}, valid={signal['valid']}")
        except Exception as e:
            self.logger.error(f"Failed to write signal: {e}")

    def run_once(self) -> None:
        """Execute one full cycle"""
        self.logger.info("=== Run Once ===")

        ranked = self.score_wallets()
        if not ranked:
            self.logger.warning("No qualified wallets")
            signal = {
                'direction': 'NONE',
                'strength': 0.0,
                'wallet_count': 0,
                'n_ranked': 0,
                'avg_sortino': 0.0,
                'timestamp': int(time.time() * 1000),
                'valid': False
            }
        else:
            positions = self.get_current_positions([w['address'] for w in ranked])
            signal = self.compute_consensus(ranked, positions)

        self.write_signal(signal)

    def run_loop(self, interval_seconds: int = 900) -> None:
        """Run continuously"""
        self.logger.info(f"Starting loop with interval {interval_seconds}s")
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
    parser.add_argument("--interval", type=int, default=900, help="Loop interval in seconds")
    args = parser.parse_args()

    monitor = WhaleMonitor()

    if args.once:
        monitor.run_once()
    else:
        monitor.run_loop(args.interval)
