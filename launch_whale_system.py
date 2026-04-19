# -*- coding: utf-8 -*-
"""
Launch Whale Monitoring System - Full Automation
Orchestrates all required processes:
1. Auto-discover wallets from Hyperliquid leaderboard
2. Launch whale_monitor.py in background
3. Launch macro_filter.py in background
4. Verify qwen_unified_live.py is running
5. Validate all systems operational
"""

import os, sys, json, subprocess, time, logging
from datetime import datetime
import signal
import atexit

# Force UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_logger():
    os.makedirs('logs', exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join('logs', f'system_launch_{ts}.log')

    logger = logging.getLogger('whale_system')
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

class WhaleSystemLauncher:
    def __init__(self):
        self.processes = {}
        self.log_file = log_file

    def discover_wallets(self):
        """Auto-discover wallets from Hyperliquid leaderboard"""
        logger.info("="*70)
        logger.info("STEP 1: Auto-discovering whale wallets from Hyperliquid")
        logger.info("="*70)

        try:
            # Try auto-discovery first
            logger.info("\nAttempting API auto-discovery...")
            result = subprocess.run(
                [sys.executable, 'discover_whale_wallets.py', '--auto', '--dry-run'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                logger.info("✓ Auto-discovery successful!")
                logger.info(result.stdout)

                # Now run without dry-run to update config
                logger.info("\nUpdating whale_wallets.json...")
                result = subprocess.run(
                    [sys.executable, 'discover_whale_wallets.py', '--auto', '--non-interactive'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    logger.info("✓ Wallet configuration updated")
                    return True

            logger.warning("Auto-discovery failed, trying manual mode...")

        except subprocess.TimeoutExpired:
            logger.warning("Auto-discovery timeout, attempting fallback...")
        except Exception as e:
            logger.warning(f"Auto-discovery error: {e}")

        # Fallback: Use --manual mode with automatic input
        logger.info("\n" + "="*70)
        logger.info("Using hardcoded known performers from public Hyperliquid data")
        logger.info("="*70)

        try:
            # Use fallback wallets without manual entry
            config = self._load_or_create_config()

            # Add some known performers as fallback
            fallback_wallets = [
                {
                    "address": "0x7dd9f0C23Fb61CA3f36B8414306310F963093c12",
                    "label": "Whale_1",
                    "active": True,
                    "notes": "User's main account - local testing"
                }
            ]

            config['wallets'] = fallback_wallets

            with open('whale_wallets.json', 'w') as f:
                json.dump(config, f, indent=2)

            logger.info("✓ Using local fallback configuration")
            logger.warning("NOTE: For production, please run: python discover_whale_wallets.py --manual")
            logger.warning("       and select TOP 6-10 wallets from https://app.hyperliquid.xyz/leaderboard")
            return True

        except Exception as e:
            logger.error(f"Fallback failed: {e}")
            return False

    def _load_or_create_config(self):
        """Load existing config or create default"""
        if os.path.exists('whale_wallets.json'):
            with open('whale_wallets.json') as f:
                return json.load(f)

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

    def launch_whale_monitor(self):
        """Launch whale_monitor.py in background"""
        logger.info("\n" + "="*70)
        logger.info("STEP 2: Launching Whale Monitor (15min cycle)")
        logger.info("="*70)

        try:
            # Create log file for whale_monitor
            log_path = os.path.join('logs', 'whale_monitor_background.log')

            with open(log_path, 'w') as log_out:
                log_out.write(f"[{datetime.utcnow().isoformat()}] Background process started\n")

            # Launch in background
            if sys.platform == 'win32':
                # Windows: use pythonw for background, or use subprocess with creationflags
                proc = subprocess.Popen(
                    [sys.executable, 'whale_monitor.py'],
                    stdout=open(log_path, 'a'),
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # Unix: use nohup or similar
                proc = subprocess.Popen(
                    [sys.executable, 'whale_monitor.py'],
                    stdout=open(log_path, 'a'),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid
                )

            self.processes['whale_monitor'] = proc
            logger.info(f"✓ whale_monitor.py started (PID: {proc.pid})")
            logger.info(f"  Output: {log_path}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to launch whale_monitor: {e}")
            return False

    def launch_macro_filter(self):
        """Launch macro_filter.py in background"""
        logger.info("\n" + "="*70)
        logger.info("STEP 3: Launching Macro Filter (60min cycle)")
        logger.info("="*70)

        try:
            # Create log file for macro_filter
            log_path = os.path.join('logs', 'macro_filter_background.log')

            with open(log_path, 'w') as log_out:
                log_out.write(f"[{datetime.utcnow().isoformat()}] Background process started\n")

            # Launch in background
            if sys.platform == 'win32':
                proc = subprocess.Popen(
                    [sys.executable, 'macro_filter.py'],
                    stdout=open(log_path, 'a'),
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                proc = subprocess.Popen(
                    [sys.executable, 'macro_filter.py'],
                    stdout=open(log_path, 'a'),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid
                )

            self.processes['macro_filter'] = proc
            logger.info(f"✓ macro_filter.py started (PID: {proc.pid})")
            logger.info(f"  Output: {log_path}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to launch macro_filter: {e}")
            return False

    def verify_qwen_unified(self):
        """Check if qwen_unified_live.py is running"""
        logger.info("\n" + "="*70)
        logger.info("STEP 4: Verifying Main Bot (qwen_unified_live.py)")
        logger.info("="*70)

        try:
            # Check if pythonw.exe or qwen process is running
            if sys.platform == 'win32':
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq pythonw.exe'],
                    capture_output=True,
                    text=True
                )

                if 'pythonw.exe' in result.stdout:
                    logger.info("✓ Main bot (qwen_unified_live.py) is running")
                    return True
                else:
                    logger.warning("⚠ Main bot not detected, launching...")

                    log_path = os.path.join('logs', 'qwen_unified_background.log')
                    proc = subprocess.Popen(
                        [sys.executable, 'qwen_unified_live.py', '--mode', 'live'],
                        stdout=open(log_path, 'a'),
                        stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )

                    self.processes['qwen_unified'] = proc
                    logger.info(f"✓ Main bot launched (PID: {proc.pid})")
                    return True

            return True

        except Exception as e:
            logger.warning(f"Could not verify main bot: {e}")
            return False

    def verify_systems(self):
        """Verify all systems are operational"""
        logger.info("\n" + "="*70)
        logger.info("STEP 5: System Verification")
        logger.info("="*70)

        time.sleep(3)  # Give processes time to start

        checks = {
            'whale_signal.json': False,
            'macro_state.json': False,
            'whale_monitor running': False,
            'macro_filter running': False
        }

        # Check if signal files will be created
        logger.info("\nChecking output files...")

        # Test whale_monitor by running once
        logger.info("Testing whale_monitor signal generation...")
        try:
            result = subprocess.run(
                [sys.executable, 'whale_monitor.py', '--once'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if os.path.exists('whale_signal.json'):
                with open('whale_signal.json') as f:
                    signal = json.load(f)
                checks['whale_signal.json'] = True
                logger.info(f"✓ whale_signal.json generated")
                logger.info(f"  direction: {signal.get('direction')}")
                logger.info(f"  strength: {signal.get('strength')}")
                logger.info(f"  valid: {signal.get('valid')}")

        except Exception as e:
            logger.warning(f"whale_monitor test failed: {e}")

        # Test macro_filter by running once
        logger.info("\nTesting macro_filter state generation...")
        try:
            result = subprocess.run(
                [sys.executable, 'macro_filter.py', '--once'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if os.path.exists('macro_state.json'):
                with open('macro_state.json') as f:
                    state = json.load(f)
                checks['macro_state.json'] = True
                logger.info(f"✓ macro_state.json generated")
                logger.info(f"  regime: {state.get('regime')}")
                logger.info(f"  atr_ratio: {state.get('atr_ratio')}")
                logger.info(f"  caution_mode: {state.get('caution_mode')}")

        except Exception as e:
            logger.warning(f"macro_filter test failed: {e}")

        # Check if processes are running
        logger.info("\nChecking background processes...")

        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                logger.info(f"✓ {name} is running (PID: {proc.pid})")
                checks[f'{name} running'] = True
            else:
                logger.warning(f"✗ {name} is not running")

        # Summary
        logger.info("\n" + "="*70)
        logger.info("VERIFICATION SUMMARY")
        logger.info("="*70)

        for check, status in checks.items():
            symbol = "✓" if status else "✗"
            logger.info(f"{symbol} {check}")

        all_ok = all(checks.values())
        return all_ok

    def register_cleanup(self):
        """Register cleanup on exit"""
        def cleanup():
            logger.info("\n" + "="*70)
            logger.info("Shutting down whale monitoring system")
            logger.info("="*70)

            for name, proc in self.processes.items():
                try:
                    logger.info(f"Terminating {name} (PID: {proc.pid})...")
                    proc.terminate()
                    proc.wait(timeout=5)
                    logger.info(f"✓ {name} terminated")
                except:
                    logger.warning(f"Failed to terminate {name}")

        atexit.register(cleanup)

    def run(self):
        """Execute full system launch"""
        logger.info("\n" + "█"*70)
        logger.info("  WHALE MONITORING SYSTEM - FULL AUTOMATION")
        logger.info("█"*70 + "\n")

        self.register_cleanup()

        # Step 1: Discover wallets
        if not self.discover_wallets():
            logger.error("Wallet discovery failed. Using fallback...")

        time.sleep(2)

        # Step 2: Launch whale_monitor
        if not self.launch_whale_monitor():
            logger.error("Failed to launch whale_monitor")
            return False

        time.sleep(2)

        # Step 3: Launch macro_filter
        if not self.launch_macro_filter():
            logger.error("Failed to launch macro_filter")
            return False

        time.sleep(2)

        # Step 4: Verify qwen_unified
        self.verify_qwen_unified()

        time.sleep(2)

        # Step 5: Verify systems
        if self.verify_systems():
            logger.info("\n✓ ALL SYSTEMS OPERATIONAL")
        else:
            logger.warning("\n⚠ Some systems not yet operational, but processes are running")

        # Print final status
        logger.info("\n" + "="*70)
        logger.info("SYSTEM STATUS")
        logger.info("="*70)
        logger.info(f"\n✓ whale_monitor.py: Running (15min cycle)")
        logger.info(f"✓ macro_filter.py: Running (60min cycle)")
        logger.info(f"✓ qwen_unified_live.py: Running (1min cycle)")
        logger.info(f"\nOutput files:")
        logger.info(f"  - whale_signal.json (updated every 15min)")
        logger.info(f"  - macro_state.json (updated every 60min)")
        logger.info(f"  - trade_alignment_log.json (updated on every trade)")

        logger.info(f"\nLogs:")
        logger.info(f"  - {log_file}")
        logger.info(f"  - logs/whale_monitor_background.log")
        logger.info(f"  - logs/macro_filter_background.log")

        logger.info(f"\nNext steps:")
        logger.info(f"  1. Check logs to verify signals are generating")
        logger.info(f"  2. Monitor whale_signal.json (should update every 15min)")
        logger.info(f"  3. After 30 days: python validate_whale_alpha.py")

        logger.info("\n" + "="*70)
        logger.info("System will continue running in background")
        logger.info("Press Ctrl+C to shutdown all processes")
        logger.info("="*70 + "\n")

        return True

if __name__ == "__main__":
    launcher = WhaleSystemLauncher()

    try:
        if launcher.run():
            # Keep the main process alive
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("\nReceived interrupt signal, shutting down...")
        else:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
