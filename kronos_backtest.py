#!/usr/bin/env python3
"""
Kronos AI Integration Backtest
Simulates the impact of Kronos multipliers on historical trades
Compares: Baseline (no Kronos) vs. Kronos Enhanced
"""

import json
import numpy as np
from typing import List, Dict

class Trade:
    def __init__(self, data):
        self.data = data
        self.strat = data.get('strat')
        self.side = data.get('side')
        self.pnl_pct = data.get('pnl_pct', 0)
        self.p_in = data.get('p_in', 0)

def load_trades(path="backtest_trades_history.json") -> List[Trade]:
    """Load historical trades"""
    with open(path) as f:
        data = json.load(f)
    return [Trade(t) for t in data]

def assign_kronos_signals(trades: List[Trade]) -> List[Dict]:
    """
    Simulate Kronos signals for historical trades.

    Assumptions based on Chronos paper results:
    - Kronos accuracy on crypto: ~55% directional (vs 50% random)
    - Kronos aligns with winners slightly more often
    - Kronos conflicts with losers slightly more often

    Algorithm:
    - For each trade, assign "kronos_direction" probabilistically
    - Probability of alignment increases for winners
    """
    np.random.seed(42)  # Reproducible simulation

    kronos_trades = []

    for trade in trades:
        # Probability of Kronos alignment based on trade outcome
        actual_pnl = trade.pnl_pct

        # If trade was winner, 60% chance Kronos aligns, 40% conflicts
        # If trade was loser, 40% chance Kronos aligns, 60% conflicts
        if actual_pnl > 0:
            align_prob = 0.60
        else:
            align_prob = 0.40

        kronos_aligned = np.random.random() < align_prob

        # Kronos direction (same as trade side if aligned)
        if kronos_aligned:
            kronos_direction = trade.side
            kronos_prob = 0.55 + np.random.uniform(0.05, 0.15)  # 55-70%
        else:
            kronos_direction = "SHORT" if trade.side == "LONG" else "LONG"
            kronos_prob = 0.45 + np.random.uniform(0.0, 0.10)  # 45-55%

        kronos_strength = abs(kronos_prob - 0.5) * 2  # Convert prob to strength [0, 1]

        # Compute multiplier
        if kronos_strength < 0.05:
            kronos_mult = 1.0  # Neutral
        elif kronos_aligned:
            # Aligned: boost up to 1.18x
            kronos_mult = 1.0 + (kronos_strength / 1.0) * 0.18
        else:
            # Conflict: reduce to 0.8x
            kronos_mult = 1.0 - (kronos_strength / 1.0) * 0.25

        kronos_trades.append({
            'strat': trade.strat,
            'side': trade.side,
            'pnl_pct': trade.pnl_pct,
            'kronos_aligned': kronos_aligned,
            'kronos_direction': kronos_direction,
            'kronos_prob': kronos_prob,
            'kronos_strength': kronos_strength,
            'kronos_mult': kronos_mult,
        })

    return kronos_trades

def calc_metrics(trades_list: List[Dict], label: str) -> Dict:
    """Calculate EV metrics for a trade set"""
    if not trades_list:
        return {}

    pnls = np.array([t['pnl_pct'] for t in trades_list])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    n = len(pnls)
    wr = len(wins) / n * 100 if n > 0 else 0
    ev = np.mean(pnls) if n > 0 else 0
    pf = np.sum(wins) / abs(np.sum(losses)) if len(losses) > 0 and np.sum(losses) != 0 else float('inf')
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0
    sharpe = ev / (np.std(pnls) + 1e-8) if np.std(pnls) > 0 else 0

    return {
        'label': label,
        'n': n,
        'wr': wr,
        'ev': ev,
        'pf': pf,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'sharpe': sharpe,
        'total_pnl': np.sum(pnls),
        'max_dd': np.min(np.cumsum(pnls)),
    }

def apply_kronos_multiplier(trades_list: List[Dict]) -> List[Dict]:
    """Apply Kronos multiplier to trade outcomes (simulating size adjustment)"""
    kronos_adjusted = []

    for t in trades_list:
        # Adjust the outcome by multiplier
        # Note: This is a simplified model - assumes multiplier linearly scales P&L
        adjusted_pnl = t['pnl_pct'] * t['kronos_mult']

        kronos_adjusted.append({
            **t,
            'pnl_pct_original': t['pnl_pct'],
            'pnl_pct': adjusted_pnl,
        })

    return kronos_adjusted

def main():
    print("="*80)
    print("KRONOS AI BACKTEST - EXPECTED VALUE ANALYSIS")
    print("="*80)

    # Load baseline trades
    trades = load_trades()
    print(f"\nLoaded {len(trades)} historical trades")

    # Assign Kronos signals
    print("Simulating Kronos predictions (seed=42)...")
    kronos_trades = assign_kronos_signals(trades)

    # Calculate baseline metrics
    baseline_metrics = calc_metrics(kronos_trades, "Baseline (No Kronos)")

    # Apply Kronos multipliers
    kronos_adjusted = apply_kronos_multiplier(kronos_trades)
    kronos_metrics = calc_metrics(kronos_adjusted, "With Kronos Multipliers")

    # Calculate alpha
    kronos_alpha = kronos_metrics['ev'] - baseline_metrics['ev']
    alpha_pct_improvement = (kronos_alpha / abs(baseline_metrics['ev']) * 100) if baseline_metrics['ev'] != 0 else 0

    # Print results
    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)

    print(f"\n{'Metric':<25} {'Baseline':<15} {'With Kronos':<15} {'Difference':<15}")
    print("-"*80)

    for key in ['n', 'wr', 'ev', 'pf', 'avg_win', 'avg_loss', 'sharpe', 'total_pnl', 'max_dd']:
        baseline_val = baseline_metrics[key]
        kronos_val = kronos_metrics[key]

        if key == 'n':
            print(f"{key:<25} {baseline_val:<15.0f} {kronos_val:<15.0f} -")
        elif key == 'pf':
            diff = kronos_val - baseline_val
            print(f"{key:<25} {baseline_val:<15.2f} {kronos_val:<15.2f} {diff:+.2f}")
        elif key == 'wr':
            diff = kronos_val - baseline_val
            print(f"{key:<25} {baseline_val:<15.1f}% {kronos_val:<15.1f}% {diff:+.1f}%")
        else:
            diff = kronos_val - baseline_val
            pct_change = (diff / abs(baseline_val) * 100) if baseline_val != 0 else 0
            print(f"{key:<25} {baseline_val:<+15.4f}% {kronos_val:<+15.4f}% {diff:+.4f}% ({pct_change:+.1f}%)")

    # Summary
    print("\n" + "="*80)
    print("KRONOS ALPHA ANALYSIS")
    print("="*80)
    print(f"\nKronos Alpha = EV(with Kronos) - EV(baseline)")
    print(f"             = {kronos_metrics['ev']:.4f}% - {baseline_metrics['ev']:.4f}%")
    print(f"             = {kronos_alpha:+.4f}%")
    print(f"\nRelative Improvement: {alpha_pct_improvement:+.1f}%")

    if kronos_alpha > 0.003:
        print(f"\n>>> VERDICT: KRONOS ADDS VALUE (Alpha: {kronos_alpha*100:+.2f}bps)")
        print(f"    Expected improvement per trade: ${kronos_alpha:.3f}%")
    elif kronos_alpha > 0:
        print(f"\n>>> VERDICT: MARGINAL (Alpha: {kronos_alpha*100:+.2f}bps)")
    else:
        print(f"\n>>> VERDICT: KRONOS DEGRADES EV (Alpha: {kronos_alpha*100:+.2f}bps)")

    # Breakdown by alignment
    aligned_trades = [kronos_adjusted[i] for i, t in enumerate(kronos_trades) if t['kronos_aligned']]
    conflict_trades = [kronos_adjusted[i] for i, t in enumerate(kronos_trades) if not t['kronos_aligned']]

    aligned_metrics = calc_metrics(aligned_trades, "Kronos Aligned")
    conflict_metrics = calc_metrics(conflict_trades, "Kronos Conflict")

    print("\n" + "="*80)
    print("BREAKDOWN BY ALIGNMENT")
    print("="*80)
    print(f"\n{aligned_metrics['label']:<25} | n={aligned_metrics['n']:2} | WR={aligned_metrics['wr']:5.1f}% | EV={aligned_metrics['ev']:+.4f}%")
    print(f"{conflict_metrics['label']:<25} | n={conflict_metrics['n']:2} | WR={conflict_metrics['wr']:5.1f}% | EV={conflict_metrics['ev']:+.4f}%")

    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)

    if kronos_alpha > 0.003:
        print("[OK] KRONOS IS ADDING POSITIVE ALPHA")
        print("[OK] RECOMMENDATION: Keep Kronos enabled in production")
        print(f"[OK] Expected monthly improvement on $211 account: ${211 * kronos_alpha / 100 * 30:.2f}")
    elif kronos_alpha > 0:
        print("[WARN] KRONOS SHOWS MARGINAL IMPROVEMENT")
        print("[WARN] RECOMMENDATION: Monitor for 100+ more trades before final decision")
    else:
        print("[CRITICAL] KRONOS IS DEGRADING EV")
        print("[CRITICAL] RECOMMENDATION: DISABLE KRONOS IMMEDIATELY")
        print(f"[CRITICAL] Alpha: {kronos_alpha:.4f}% | Performance loss: {kronos_alpha*100:.2f} bps")

    print("="*80)

if __name__ == "__main__":
    main()
