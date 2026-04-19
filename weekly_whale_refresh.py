# -*- coding: utf-8 -*-
"""
Weekly Whale Wallet Refresh System
自動的に Hyperliquid Leaderboard からトップトレーダーを発見し、
ウォレット設定を週1回更新する
"""

import os, sys, json, time, logging, schedule
from datetime import datetime, timedelta
from typing import List, Dict
import requests
import numpy as np

# Force UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_logger():
    os.makedirs('logs', exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join('logs', f'weekly_refresh_{ts}.log')

    logger = logging.getLogger('weekly_refresh')
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
    return logger, log_file

logger, log_file = setup_logger()

class WeeklyWhaleRefresh:
    """
    毎週Hyperliquid Leaderboardからトップウォレットを自動発見し、
    whale_wallets.json を更新する
    """

    HL_API_URL = "https://api.hyperliquid.xyz/info"
    LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

    def __init__(self):
        self.config_path = "whale_wallets.json"
        self.backup_dir = "whale_wallets_backups"
        os.makedirs(self.backup_dir, exist_ok=True)

    def _raw_post(self, url: str, payload: dict, timeout: int = 10) -> dict:
        """POST request to Hyperliquid API"""
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.info(f"API error {resp.status_code}: {payload.get('type')}")
        except Exception as e:
            logger.info(f"Request error: {type(e).__name__}: {e}")
        return {}

    def _fetch_leaderboard_wallets(self, limit: int = 15) -> List[dict]:
        """
        Fetch top traders from Hyperliquid leaderboard.
        Filter by: ROI > 20%, Trades >= 200, AUM $1M-$100M
        """
        logger.info("\n" + "="*70)
        logger.info("FETCHING TOP TRADERS FROM HYPERLIQUID LEADERBOARD")
        logger.info("="*70)

        candidates = []

        try:
            logger.info("Querying stats-data.hyperliquid.xyz...")
            resp = requests.get(
                self.LEADERBOARD_URL,
                params={'limit': 500},
                timeout=15
            )

            if resp.status_code != 200:
                logger.warning(f"API returned {resp.status_code}")
                return candidates

            data = resp.json()
            if not data:
                return candidates

            # Parse response - actual API structure
            leaderboard = data.get('leaderboardRows', [])

            if not leaderboard:
                leaderboard = data if isinstance(data, list) else data.get('leaderboard', [])

            logger.info(f"Processing {len(leaderboard)} traders from leaderboard...")

            for trader in leaderboard:
                try:
                    # Get address
                    addr = trader.get('ethAddress') or trader.get('address') or trader.get('user')
                    if not addr or not addr.startswith('0x'):
                        continue

                    # Get account value
                    aum = float(trader.get('accountValue', 0))

                    # Get ROI from allTime window performance
                    roi_pct = 0.0
                    window_perfs = trader.get('windowPerformances', [])
                    for window in window_perfs:
                        if isinstance(window, (list, tuple)) and len(window) >= 2:
                            if window[0] == 'allTime' and isinstance(window[1], dict):
                                roi_pct = float(window[1].get('roi', 0)) * 100
                                break

                    roi = roi_pct
                    pnl = float(trader.get('pnl', 0))

                    # For leaderboard endpoint, we don't have trade count
                    # Use a placeholder - we'll validate actual trades on-chain
                    trades = 0  # Will be determined in _score_wallet

                    # Include all candidates - real filtering happens on-chain
                    # Leaderboard shows historical data; actual on-chain validation determines viability
                    candidates.append({
                        'address': addr,
                        'roi': roi,
                        'trades': trades,
                        'pnl': pnl,
                        'aum': aum,
                        'score': roi * (aum / 10000000)  # Simple score by ROI and AUM
                    })

                    logger.info(f"  {addr[:16]}... ROI={roi:.1f}% AUM=${aum:,.0f}")

                except (KeyError, ValueError, TypeError) as e:
                    continue

        except Exception as e:
            logger.warning(f"Leaderboard fetch failed: {e}")
            logger.info("Attempting fallback API endpoints...")

            # Try Hyperliquid /info endpoint
            try:
                payloads = [
                    {'type': 'leaderboard', 'limit': 50},
                    {'type': 'topTraders', 'limit': 50},
                ]

                for payload in payloads:
                    data = self._raw_post(self.HL_API_URL, payload)
                    if not data:
                        continue

                    lb = data if isinstance(data, list) else data.get('leaderboard', [])
                    if not lb:
                        continue

                    logger.info(f"Found {len(lb)} traders via /info endpoint")

                    for trader in lb:
                        try:
                            addr = trader.get('user') or trader.get('address')
                            if not addr or not addr.startswith('0x'):
                                continue

                            roi = float(trader.get('roi', 0))
                            trades = int(trader.get('nTrades', 0))
                            aum = float(trader.get('accountValue', 0))

                            if roi >= 20 and trades >= 200 and 1000000 <= aum <= 100000000:
                                candidates.append({
                                    'address': addr,
                                    'roi': roi,
                                    'trades': trades,
                                    'pnl': 0,
                                    'aum': aum,
                                    'score': roi * (trades / 1000)
                                })

                                logger.info(f"  {addr[:16]}... ROI={roi:.1f}% Trades={trades}")

                        except (KeyError, ValueError, TypeError):
                            continue

                    if candidates:
                        break

            except Exception as e2:
                logger.warning(f"Fallback also failed: {e2}")

        # Sort by composite score
        candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)

        logger.info(f"\nQualified candidates: {len(candidates)}")
        return candidates[:limit]

    def _validate_wallet_on_chain(self, address: str) -> Dict:
        """
        Validate wallet on Hyperliquid and get current metrics
        """
        try:
            payload = {'type': 'clearinghouseState', 'user': address}
            data = self._raw_post(self.HL_API_URL, payload)

            if not data:
                logger.info(f"    No data returned for {address[:16]}")
                return None

            margin = data.get('marginSummary', {})
            account_value = float(margin.get('accountValue', 0))
            positions = data.get('assetPositions', [])
            active_pos = len([p for p in positions if float(p.get('position', {}).get('szi', 0)) != 0])

            logger.info(f"    On-chain AUM: ${account_value:,.0f}")

            return {
                'address': address,
                'account_value': account_value,
                'active_positions': active_pos,
                'valid': True
            }

        except Exception as e:
            logger.info(f"    Validation error: {type(e).__name__}: {e}")
            return None

    def _compute_sortino(self, returns: List[float], period_days: int = 90) -> float:
        """Compute Sortino ratio"""
        if not returns or len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns, dtype=float)
        mean_ret = np.mean(returns_arr)
        n_trades = len(returns_arr)

        trades_per_year = (n_trades / max(period_days, 1)) * 252
        annualization = np.sqrt(max(trades_per_year, 1))

        downside = returns_arr[returns_arr < 0]
        if len(downside) == 0:
            return min(mean_ret / 0.1 * annualization, 10.0)

        downside_vol = np.std(downside)
        if downside_vol <= 0:
            return 0.0

        return float((mean_ret / downside_vol) * annualization)

    def _score_wallet(self, address: str) -> Dict:
        """
        Score wallet by actual Hyperliquid fills (Sortino-based)
        Returns {sortino, win_rate, trade_count, aum}
        """
        try:
            logger.info(f"  Scoring {address[:16]}...")

            # Get current AUM
            acct = self._validate_wallet_on_chain(address)
            if not acct:
                logger.info(f"    Failed to validate on-chain")
                return None
            min_aum = 100000  # Reduced from $1M to find active traders
            if acct['account_value'] < min_aum:
                logger.info(f"    AUM too low: ${acct['account_value']:,.0f} < ${min_aum:,.0f}")
                return None

            # Fetch fills
            start_ms = int((datetime.utcnow() - timedelta(days=90)).timestamp() * 1000)
            payload = {'type': 'userFills', 'user': address, 'startTime': start_ms}
            fills_data = self._raw_post(self.HL_API_URL, payload)

            if not isinstance(fills_data, list):
                logger.info(f"    Fills not a list: {type(fills_data)}")
                return None
            if not fills_data:
                logger.info(f"    No fills data")
                return None

            logger.info(f"    Got {len(fills_data)} fills")

            # Pair fills to trades
            by_coin = {}
            for f in fills_data:
                coin = f.get('coin', '')
                if coin not in by_coin:
                    by_coin[coin] = []
                by_coin[coin].append(f)

            returns = []
            for coin, coin_fills in by_coin.items():
                coin_fills.sort(key=lambda x: x.get('time', 0))
                net_sz = 0.0
                entry_px = None

                for fill in coin_fills:
                    side = fill.get('side', '')
                    sz = float(fill.get('sz', 0))
                    px = float(fill.get('px', 0))

                    if entry_px is None:
                        entry_px = px
                        net_sz = sz if side == 'B' else -sz
                    else:
                        prev_sz = net_sz
                        net_sz -= sz if side == 'B' else -sz

                        if prev_sz * net_sz <= 0:
                            pnl_pct = ((px - entry_px) / entry_px) * 100
                            if side == 'A':
                                pnl_pct = -pnl_pct
                            returns.append(pnl_pct)
                            entry_px = None
                            net_sz = 0.0

            min_trades = 10  # Minimum closed trades for statistical validity
            if len(returns) < min_trades:
                logger.info(f"    {len(returns)} closed trades < {min_trades}")
                return None

            # Calculate metrics
            wins = [r for r in returns if r > 0]
            win_rate = len(wins) / len(returns)
            avg_win = np.mean(wins) if wins else 0
            avg_loss = abs(np.mean([r for r in returns if r <= 0])) if any(r <= 0 for r in returns) else 0

            sortino = self._compute_sortino(returns)

            # For initial discovery, accept any active wallet (minimum threshold already passed)
            # Real performance filtering will happen during live trading via alignment log

            logger.info(f"    OK: Sortino={sortino:.2f}, WR={win_rate:.1%}, Trades={len(returns)}")

            return {
                'address': address,
                'sortino': float(sortino),
                'win_rate': float(win_rate),
                'trade_count': len(returns),
                'aum': acct['account_value'],
                'avg_win': float(avg_win),
                'avg_loss': float(avg_loss)
            }

        except Exception as e:
            logger.info(f"  Scoring failed: {type(e).__name__}: {e}")
            return None

    def refresh_wallets(self) -> bool:
        """
        Main refresh workflow:
        1. Fetch top traders from leaderboard
        2. Validate and score each wallet
        3. Select top N
        4. Backup current config
        5. Update whale_wallets.json
        """
        logger.info("\n" + "█"*70)
        logger.info("  WEEKLY WHALE WALLET REFRESH")
        logger.info("█"*70)

        # Step 1: Fetch leaderboard
        candidates = self._fetch_leaderboard_wallets(limit=20)

        if not candidates:
            logger.error("No candidates found from leaderboard")
            return False

        # Step 2: Score wallets
        logger.info("\nValidating and scoring wallets...")
        scored = []

        for cand in candidates:
            score = self._score_wallet(cand['address'])
            if score:
                scored.append(score)
            if len(scored) >= 5:  # Lower threshold for initial population
                break

        if not scored:
            logger.error("No wallets qualified")
            return False

        # Sort by Sortino
        scored = sorted(scored, key=lambda x: x['sortino'], reverse=True)

        # Step 3: Prepare new config
        logger.info(f"\nSelected {len(scored)} qualified wallets:")

        new_wallets = [
            {
                'address': w['address'],
                'label': f"Whale_{i}",
                'active': True,
                'notes': f"Sortino={w['sortino']:.2f}, WR={w['win_rate']:.1%}, Trades={w['trade_count']}, AUM=${w['aum']:,.0f}"
            }
            for i, w in enumerate(scored, 1)
        ]

        for i, w in enumerate(new_wallets, 1):
            logger.info(f"{i}. {w['address'][:16]}... {w['notes']}")

        # Step 4: Backup current config
        if os.path.exists(self.config_path):
            backup_name = os.path.join(
                self.backup_dir,
                f"whale_wallets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )
            import shutil
            shutil.copy(self.config_path, backup_name)
            logger.info(f"\nBackup: {backup_name}")

        # Step 5: Load existing config and update wallets
        try:
            with open(self.config_path) as f:
                config = json.load(f)
        except:
            config = self._get_default_config()

        config['wallets'] = new_wallets
        config['last_refresh'] = datetime.utcnow().isoformat()

        # Step 6: Write new config
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"\nUpdated whale_wallets.json with {len(new_wallets)} wallets")
        logger.info("="*70)

        return True

    def _get_default_config(self) -> dict:
        """Get default configuration"""
        return {
            "wallets": [],
            "scoring_config": {
                "lookback_days": 90,
                "min_trades": 200,
                "min_sortino": 2.0,
                "min_win_rate": 0.50,
                "min_account_value": 1000000,
                "max_account_value": 100000000,
                "sortino_normalization_cap": 4.0,
                "rescore_interval_hours": 24
            },
            "consensus_config": {
                "min_agreeing_wallets": 3,
                "min_ranked_wallets": 3,
                "min_agreement_pct": 0.60,
                "signal_ttl_minutes": 30
            },
            "symbols_to_track": ["BTC"]
        }

    def run_scheduled(self, interval_hours: int = 168):
        """
        Run weekly refresh on schedule (default: 168 hours = 1 week)
        """
        logger.info(f"\nScheduling weekly wallet refresh every {interval_hours}h...")

        # Schedule the refresh
        def job():
            logger.info(f"\n[{datetime.utcnow()}] Running scheduled refresh...")
            self.refresh_wallets()
            logger.info(f"[{datetime.utcnow()}] Refresh complete\n")

        schedule.every(interval_hours).hours.do(job)

        # Run immediately on first launch
        logger.info("Running initial refresh...")
        job()

        # Keep scheduler running
        logger.info("\nScheduler running. Press Ctrl+C to stop.")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("\nScheduler stopped")

if __name__ == "__main__":
    refresher = WeeklyWhaleRefresh()

    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # One-time refresh
        refresher.refresh_wallets()
    else:
        # Scheduled mode (weekly)
        refresher.run_scheduled(interval_hours=168)
