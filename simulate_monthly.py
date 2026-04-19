#!/usr/bin/env python3
import json
from pathlib import Path

LOGS_DIR = Path("multi_agent_logs")

def simulate_monthly_operations():
    """1ヶ月分のマルチエージェント運用をシミュレート"""
    
    # 前回実行結果を読み込む
    monitor_file = LOGS_DIR / "multi_agent_monitor.json"
    if not monitor_file.exists():
        print("[ERROR] Run multi_agent_system.py first")
        return
    
    with open(monitor_file, 'r') as f:
        baseline = json.load(f)
    
    tokens_per_session = baseline['token_usage']['total']
    cache_efficiency = baseline['savings_percentage']
    
    print("\n" + "="*80)
    print("MONTHLY OPERATION SIMULATION")
    print("="*80)
    
    # Scenario: 30日間の日次運用
    scenarios = [
        {
            "name": "Traditional (Single Agent)",
            "tokens_per_session": 9000,
            "cache_efficiency": 0
        },
        {
            "name": "Multi-Agent (3-Layer)",
            "tokens_per_session": tokens_per_session,
            "cache_efficiency": cache_efficiency
        },
        {
            "name": "Multi-Agent Optimized (2x efficiency)",
            "tokens_per_session": tokens_per_session,
            "cache_efficiency": cache_efficiency * 2
        }
    ]
    
    sessions_per_day = 2
    days = 30
    total_sessions = sessions_per_day * days
    
    print(f"\nAssumptions:")
    print(f"  - Sessions per day: {sessions_per_day}")
    print(f"  - Days in month: {days}")
    print(f"  - Total sessions: {total_sessions}")
    print(f"  - Claude API cost: $0.003/1000 input tokens")
    
    results = []
    
    for scenario in scenarios:
        name = scenario['name']
        tokens_base = scenario['tokens_per_session'] * total_sessions
        efficiency = scenario['cache_efficiency']
        
        # キャッシュによる削減
        cache_savings = tokens_base * (efficiency / 100)
        tokens_final = tokens_base - cache_savings
        
        # コスト計算
        cost = (tokens_final / 1000) * 0.003
        
        results.append({
            "name": name,
            "tokens_base": tokens_base,
            "cache_savings": cache_savings,
            "tokens_final": tokens_final,
            "cost": cost,
            "efficiency": efficiency
        })
        
        print(f"\n{'-'*80}")
        print(f"{name}")
        print(f"{'-'*80}")
        print(f"  Base consumption: {tokens_base:>12,.0f}t")
        print(f"  Cache savings:   {cache_savings:>12,.0f}t ({efficiency:.1f}%)")
        print(f"  Final usage:     {tokens_final:>12,.0f}t")
        print(f"  Monthly cost:    ${cost:>11.2f}")
    
    # Comparison Table
    print(f"\n{'-'*80}")
    print("COMPARISON TABLE")
    print(f"{'-'*80}")
    
    baseline = results[0]
    
    print(f"\n{'Scenario':<35} {'Tokens':>15} {'Cost':>10} {'Savings':>10}")
    print(f"{'-'*70}")
    
    for r in results:
        tokens_saved = baseline['tokens_final'] - r['tokens_final']
        cost_saved = baseline['cost'] - r['cost']
        savings_pct = (tokens_saved / baseline['tokens_final'] * 100) if baseline['tokens_final'] > 0 else 0
        
        print(f"{r['name']:<35} {r['tokens_final']:>12,.0f}t ${r['cost']:>8.2f} ${cost_saved:>8.2f}")
    
    # Best case analysis
    print(f"\n{'-'*80}")
    print("BEST CASE: Multi-Agent with Optimal Cache")
    print(f"{'-'*80}")
    
    best = results[2]
    vs_traditional = results[0]
    
    print(f"\nMonthly Performance:")
    print(f"  Tokens saved: {vs_traditional['tokens_final'] - best['tokens_final']:>12,.0f}t")
    print(f"  Cost saved:   ${vs_traditional['cost'] - best['cost']:>11.2f}")
    
    print(f"\nAnnual Impact:")
    annual_savings_tokens = (vs_traditional['tokens_final'] - best['tokens_final']) * 12
    annual_savings_cost = (vs_traditional['cost'] - best['cost']) * 12
    print(f"  Tokens saved: {annual_savings_tokens:>12,.0f}t")
    print(f"  Cost saved:   ${annual_savings_cost:>11.2f}")
    
    print("\n" + "="*80)
    
    # Save simulation results
    simulation_data = {
        "simulation_date": str(Path.cwd()),
        "assumptions": {
            "sessions_per_day": sessions_per_day,
            "days": days,
            "total_sessions": total_sessions
        },
        "scenarios": [
            {
                "name": r['name'],
                "tokens_final": int(r['tokens_final']),
                "cost": round(r['cost'], 2),
                "efficiency": r['efficiency']
            }
            for r in results
        ]
    }
    
    sim_file = LOGS_DIR / "monthly_simulation.json"
    with open(sim_file, 'w') as f:
        json.dump(simulation_data, f, indent=2)
    
    print(f"\nSimulation data saved to: {sim_file}")

if __name__ == "__main__":
    simulate_monthly_operations()
