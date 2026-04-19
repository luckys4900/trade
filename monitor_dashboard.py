#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime
import time

LOGS_DIR = Path("multi_agent_logs")

def print_dashboard():
    monitor_file = LOGS_DIR / "multi_agent_monitor.json"
    
    if not monitor_file.exists():
        print("[ERROR] No monitor data found.")
        return
    
    with open(monitor_file, 'r') as f:
        data = json.load(f)
    
    print("\n" + "="*80)
    print("MULTI-AGENT TRADING SYSTEM - LIVE DASHBOARD")
    print("="*80)
    
    print(f"\nSession ID: {data['session_id']}")
    print(f"Timestamp: {data['timestamp']}")
    
    # Token Usage Summary
    print("\n" + "-"*80)
    print("TOKEN USAGE SUMMARY")
    print("-"*80)
    
    tokens = data['token_usage']
    total = tokens['total']
    
    print(f"\n{'Layer':<25} {'Tokens':>12} {'% of Total':>12} {'Visual':>40}")
    print("-"*80)
    
    for layer, consumed in [('Layer1 (Planning)', tokens['layer1']), 
                            ('Layer2 (Execution)', tokens['layer2']),
                            ('Layer3 (Verify+Cache)', tokens['layer3'])]:
        pct = (consumed / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2) + "-" * (50 - int(pct / 2))
        print(f"{layer:<25} {consumed:>12}t {pct:>11.1f}% [{bar}]")
    
    print("-"*80)
    print(f"{'TOTAL':<25} {total:>12}t {'100.0%':>11}")
    
    # Cache Efficiency
    print("\n" + "-"*80)
    print("CACHE EFFICIENCY")
    print("-"*80)
    
    savings = tokens['cache_savings']
    efficiency = data['savings_percentage']
    
    print(f"\nCache Hits: {data['cache_hits']}")
    print(f"Tokens Saved: {savings}t")
    print(f"Efficiency Gain: {efficiency}%")
    
    if data['cache_hits'] > 0:
        print(f"\nEstimated Monthly Savings (100 sessions):")
        monthly_base = total * 100
        monthly_cached = total * 100 * (1 - efficiency/100)
        monthly_saving = monthly_base - monthly_cached
        print(f"  Without cache: {monthly_base:,}t")
        print(f"  With cache: {int(monthly_cached):,}t")
        print(f"  Savings: {int(monthly_saving):,}t ({efficiency}%)")
    
    # Execution Timeline
    print("\n" + "-"*80)
    print("EXECUTION TIMELINE")
    print("-"*80)
    
    events = data['timeline']
    if events:
        for event in events:
            time_str = event['timestamp'].split('T')[1][:8]
            layer = event['layer']
            event_type = event['event_type']
            
            if event_type == 'tokens':
                tokens_val = event['details'].get('consumed', 0)
                print(f"[{time_str}] {layer:<8} -> {event_type:<15} ({tokens_val}t)")
            else:
                print(f"[{time_str}] {layer:<8} -> {event_type}")
    
    # Layer Outputs
    print("\n" + "-"*80)
    print("LAYER OUTPUTS")
    print("-"*80)
    
    for layer_file in ['layer1_output.json', 'layer2_output.json', 'layer3_output.json']:
        path = LOGS_DIR / layer_file
        if path.exists():
            with open(path, 'r') as f:
                output = json.load(f)
            
            layer_num = layer_file.split('_')[0].upper()
            print(f"\n{layer_num}:")
            for key, value in output.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")
    
    # Comparison: Single Agent vs Multi-Agent
    print("\n" + "-"*80)
    print("EFFICIENCY COMPARISON")
    print("-"*80)
    
    print("\nTraditional Single Agent:")
    print(f"  Per session: 9,000t")
    print(f"  Monthly (100 sessions): 900,000t")
    print(f"  Monthly cost: $2.70")
    
    print(f"\nMulti-Agent (3-Layer with Cache):")
    print(f"  Per session: {total}t")
    print(f"  Monthly (100 sessions): {total * 100:,}t")
    monthly_cost = (total * 100) / 1000 * 0.003
    print(f"  Monthly cost: ${monthly_cost:.2f}")
    
    savings_total = 900000 - (total * 100)
    savings_percent = (savings_total / 900000) * 100
    savings_cost = 2.70 - monthly_cost
    
    print(f"\nSavings:")
    print(f"  Tokens: {savings_total:,}t/month ({savings_percent:.1f}%)")
    print(f"  Cost: ${savings_cost:.2f}/month")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    print_dashboard()
