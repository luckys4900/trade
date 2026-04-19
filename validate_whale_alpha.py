# -*- coding: utf-8 -*-
"""
Validate Whale Signal Alpha
Analyzes trade_alignment_log.json to measure EV improvement from whale signals
Run this after 30+ trades are recorded
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np

# ==================================================================
# EV VALIDATOR
# ==================================================================

class EVValidator:
    def __init__(self, log_file: str = "trade_alignment_log.json"):
        self.log_file = log_file
        self.trades = self._load_trades()

    def _load_trades(self) -> List[dict]:
        """Load trade alignment log"""
        if not os.path.exists(self.log_file):
            print(f"✗ {self.log_file} not found")
            return []

        try:
            with open(self.log_file) as f:
                trades = json.load(f)
            print(f"✓ Loaded {len(trades)} trade records")
            return trades
        except Exception as e:
            print(f"✗ Failed to load: {e}")
            return []

    def _group_trades(self) -> Dict[str, List[dict]]:
        """Group trades by alignment status"""
        aligned = []
        unaligned = []
        conflict = []

        for t in self.trades:
            if t.get('outcome') is None:
                # Skip unclosed trades
                continue

            outcome = float(t.get('outcome', 0)) / 100.0  # % to fraction

            if t.get('whale_aligned'):
                aligned.append({**t, 'outcome_frac': outcome})
            elif t.get('whale_direction') and t.get('whale_direction') != t.get('direction'):
                conflict.append({**t, 'outcome_frac': outcome})
            else:
                unaligned.append({**t, 'outcome_frac': outcome})

        return {
            'aligned': aligned,
            'unaligned': unaligned,
            'conflict': conflict
        }

    def _compute_ev(self, trades: List[dict]) -> Optional[dict]:
        """Compute EV metrics for a trade group"""
        if not trades:
            return None

        outcomes = [t['outcome_frac'] for t in trades]
        outcomes = np.array(outcomes)

        wins = outcomes[outcomes > 0]
        losses = outcomes[outcomes <= 0]

        win_rate = len(wins) / len(outcomes) if len(outcomes) > 0 else 0
        avg_win = np.mean(wins) if len(wins) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0

        ev = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        sharpe = ev / (np.std(outcomes) + 1e-8) if np.std(outcomes) > 0 else 0

        return {
            'count': len(trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'ev': ev,
            'sharpe': sharpe,
            'std_dev': np.std(outcomes)
        }

    def validate(self) -> None:
        """Run validation and print report"""
        if not self.trades:
            print("\n✗ No trades to validate")
            return

        print("\n" + "="*80)
        print("WHALE SIGNAL ALPHA VALIDATION REPORT")
        print("="*80)

        # Summary
        total_trades = len(self.trades)
        closed_trades = len([t for t in self.trades if t.get('outcome') is not None])

        print(f"\nTotal trade records: {total_trades}")
        print(f"Closed trades (with outcome): {closed_trades}")

        if closed_trades < 10:
            print("\n⚠️  Minimum 10 closed trades recommended for validation")
            print(f"    Current: {closed_trades}")
            return

        # Group trades
        groups = self._group_trades()
        print(f"\nTrade breakdown:")
        print(f"  • Whale Aligned:   {len(groups['aligned'])} trades")
        print(f"  • Whale Conflicted: {len(groups['conflict'])} trades")
        print(f"  • No Whale Signal:  {len(groups['unaligned'])} trades")

        # Compute metrics per group
        print("\n" + "="*80)
        print("EV METRICS BY GROUP")
        print("="*80 + "\n")

        metrics = {}
        for group_name, trades_list in groups.items():
            metrics[group_name] = self._compute_ev(trades_list)

        # Print table
        print(f"{'Group':<20} | {'Trades':>6} | {'WR':>6} | {'Avg Win':>10} | {'Avg Loss':>10} | {'EV':>10}")
        print("-" * 80)

        for group_name in ['aligned', 'unaligned', 'conflict']:
            m = metrics[group_name]
            if m is None:
                continue

            group_label = {
                'aligned': 'Whale Aligned',
                'unaligned': 'No Whale',
                'conflict': 'Whale Conflict'
            }[group_name]

            print(f"{group_label:<20} | {m['count']:>6} | {m['win_rate']:>5.1%} | "
                  f"{m['avg_win']:>9.2%} | {m['avg_loss']:>9.2%} | {m['ev']:>9.2%}")

        # Analysis
        print("\n" + "="*80)
        print("ANALYSIS")
        print("="*80 + "\n")

        aligned_ev = metrics['aligned']['ev'] if metrics['aligned'] else 0
        unaligned_ev = metrics['unaligned']['ev'] if metrics['unaligned'] else 0
        conflict_ev = metrics['conflict']['ev'] if metrics['conflict'] else 0

        alpha = aligned_ev - unaligned_ev

        print(f"EV Improvement (Aligned vs No Signal):")
        print(f"  Aligned EV:     {aligned_ev:>8.2%}")
        print(f"  No Whale EV:    {unaligned_ev:>8.2%}")
        print(f"  Alpha:          {alpha:>8.2%}")

        if metrics['conflict']['count'] > 0:
            print(f"\nConflict Analysis:")
            print(f"  Conflict EV:    {conflict_ev:>8.2%}")
            print(f"  Vs Aligned:     {conflict_ev - aligned_ev:>8.2%} (should be negative)")

        # Recommendation
        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80 + "\n")

        if closed_trades < 30:
            print(f"⚠️  Insufficient data ({closed_trades}/30 minimum)")
            print("   Continue running for 30+ closed trades before final decision.\n")
        elif alpha > 0.003:  # > 0.3%
            print(f"✓ WHALE SIGNAL IS GENERATING ALPHA: +{alpha:.2%} per trade")
            print("  → Keep whale_enabled = True")
            print("  → Continue monitoring and revalidate monthly\n")
        elif alpha > 0:
            print(f"⚠ MARGINAL ALPHA: +{alpha:.2%} per trade")
            print("  → Alpha exists but may be within noise")
            print("  → Recommended: extend validation period to 60 trades\n")
        else:
            print(f"✗ WHALE SIGNAL UNDERPERFORMING: {alpha:.2%} per trade")
            print("  → Consider setting whale_enabled = False")
            print("  → Use existing RSI strategy (60% WR, PF 2.09) only\n")

        # Statistical significance
        print("Statistical Confidence:")
        if aligned_ev is not None and metrics['aligned']:
            m = metrics['aligned']
            se = m['std_dev'] / np.sqrt(m['count']) if m['count'] > 0 else 0
            ci_95 = 1.96 * se
            print(f"  Aligned EV 95% CI: [{aligned_ev - ci_95:.2%}, {aligned_ev + ci_95:.2%}]")

        print("\n" + "="*80)

    def export_csv(self, output_file: str = "whale_validation_report.csv") -> None:
        """Export detailed report to CSV"""
        try:
            import csv
            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ts', 'strategy', 'direction', 'whale_aligned', 'whale_strength',
                    'whale_wallet_count', 'macro_regime', 'caution_mode', 'multiplier',
                    'base_sz', 'final_sz', 'outcome'
                ])
                writer.writeheader()
                writer.writerows(self.trades)
            print(f"✓ Exported to {output_file}")
        except Exception as e:
            print(f"✗ Export failed: {e}")

# ==================================================================
# MAIN
# ==================================================================

class KronosEVValidator(EVValidator):
    """Kronos AI signal alpha validator - extends EVValidator"""

    def _group_by_kronos(self) -> Dict[str, List[dict]]:
        """Group trades by Kronos alignment status"""
        kronos_aligned = []
        kronos_neutral = []
        kronos_conflict = []

        for t in self.trades:
            if t.get('outcome') is None:
                continue

            outcome = float(t.get('outcome', 0)) / 100.0

            k_direction = t.get('kronos_direction')
            trade_dir = t.get('direction')

            if k_direction is None or k_direction == 'NONE':
                kronos_neutral.append({**t, 'outcome_frac': outcome})
            elif k_direction == trade_dir:
                kronos_aligned.append({**t, 'outcome_frac': outcome})
            else:
                kronos_conflict.append({**t, 'outcome_frac': outcome})

        return {
            'aligned': kronos_aligned,
            'neutral': kronos_neutral,
            'conflict': kronos_conflict
        }

    def _validate_strength_calibration(self) -> None:
        """Analyze correlation between Kronos conviction (strength) and outcomes"""
        print("\n" + "="*80)
        print("KRONOS CONVICTION CALIBRATION ANALYSIS")
        print("="*80 + "\n")

        buckets = {
            'low (<0.1)': [],
            'mid (0.1-0.25)': [],
            'high (>0.25)': []
        }

        for t in self.trades:
            if t.get('outcome') is None or not t.get('kronos_aligned'):
                continue

            strength = t.get('kronos_strength', 0) or 0
            outcome = float(t.get('outcome', 0)) / 100.0

            if strength < 0.1:
                buckets['low (<0.1)'].append(outcome)
            elif strength < 0.25:
                buckets['mid (0.1-0.25)'].append(outcome)
            else:
                buckets['high (>0.25)'].append(outcome)

        print("EV by Kronos Conviction Level (aligned trades only):")
        print(f"{'Conviction Level':<25} | {'Trades':>6} | {'Avg EV':>10}")
        print("-" * 50)

        for bucket_name, outcomes in buckets.items():
            if not outcomes:
                continue
            avg_ev = np.mean(outcomes)
            print(f"{bucket_name:<25} | {len(outcomes):>6} | {avg_ev:>9.2%}")

    def validate_kronos(self) -> None:
        """Run Kronos-specific validation and print report"""
        if not self.trades:
            print("\n✗ No trades to validate")
            return

        print("\n" + "="*80)
        print("KRONOS AI SIGNAL ALPHA VALIDATION REPORT")
        print("="*80)

        # Summary
        total_trades = len(self.trades)
        closed_trades = len([t for t in self.trades if t.get('outcome') is not None])

        print(f"\nTotal trade records: {total_trades}")
        print(f"Closed trades (with outcome): {closed_trades}")

        if closed_trades < 10:
            print("\n⚠️  Minimum 10 closed trades recommended for validation")
            print(f"    Current: {closed_trades}")
            return

        # Group trades by Kronos alignment
        groups = self._group_by_kronos()
        print(f"\nTrade breakdown by Kronos signal:")
        print(f"  • Kronos Aligned:   {len(groups['aligned'])} trades")
        print(f"  • Kronos Conflicted: {len(groups['conflict'])} trades")
        print(f"  • Kronos Neutral:    {len(groups['neutral'])} trades")

        # Compute metrics per group
        print("\n" + "="*80)
        print("KRONOS EV METRICS")
        print("="*80 + "\n")

        metrics = {}
        for group_name, trades_list in groups.items():
            metrics[group_name] = self._compute_ev(trades_list)

        # Print table
        print(f"{'Group':<20} | {'Trades':>6} | {'WR':>6} | {'Avg Win':>10} | {'Avg Loss':>10} | {'EV':>10}")
        print("-" * 80)

        for group_name in ['aligned', 'neutral', 'conflict']:
            m = metrics[group_name]
            if m is None:
                continue

            group_label = {
                'aligned': 'Kronos Aligned',
                'neutral': 'Kronos Neutral',
                'conflict': 'Kronos Conflict'
            }[group_name]

            print(f"{group_label:<20} | {m['count']:>6} | {m['win_rate']:>5.1%} | "
                  f"{m['avg_win']:>9.2%} | {m['avg_loss']:>9.2%} | {m['ev']:>9.2%}")

        # Alpha Analysis
        print("\n" + "="*80)
        print("KRONOS ALPHA ANALYSIS")
        print("="*80 + "\n")

        m_aligned = metrics['aligned']
        m_neutral = metrics['neutral']

        if m_aligned and m_neutral:
            alpha = m_aligned['ev'] - m_neutral['ev']
            print(f"Kronos Alpha = EV(aligned) - EV(neutral)")
            print(f"             = {m_aligned['ev']:.4f} - {m_neutral['ev']:.4f}")
            print(f"             = {alpha:.4f} ({alpha*100:+.2f}%)")

            if alpha > 0.003:
                print("\n✓ Kronos signal shows POSITIVE alpha")
                print("  → VALID for live trading (shadow_mode=False)")
            elif alpha > 0.0:
                print("\n~ Kronos alpha is MARGINAL")
                print("  → Monitor further, consider tuning neutral band")
            else:
                print("\n✗ Kronos signal shows NEGATIVE alpha")
                print("  → DISABLE Kronos (kronos_enabled=False)")

        # Strength calibration
        self._validate_strength_calibration()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate signal alpha from trade_alignment_log.json"
    )
    parser.add_argument("--log", type=str, default="trade_alignment_log.json",
                        help="Path to trade alignment log")
    parser.add_argument("--mode", type=str, default="whale",
                        choices=["whale", "kronos", "both"],
                        help="Validation mode: whale, kronos, or both")
    parser.add_argument("--export", action="store_true",
                        help="Export detailed CSV report")
    args = parser.parse_args()

    if args.mode in ["whale", "both"]:
        validator = EVValidator(args.log)
        validator.validate()

    if args.mode in ["kronos", "both"]:
        kronos_validator = KronosEVValidator(args.log)
        kronos_validator.validate_kronos()

    if args.export:
        validator = EVValidator(args.log)
        validator.export_csv()
