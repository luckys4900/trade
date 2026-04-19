#!/usr/bin/env python3
"""
LightRAG Setup for Whale-Following Trading System
Analyzes dependency graph of trading strategies
"""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

STRATEGY_FILES = [
    "qwen_unified_live.py",
    "whale_monitor.py",
    "macro_filter.py",
]

def analyze_trading_system_structure():
    print("[*] Scanning strategy files...")
    file_stats = {}

    for filename in STRATEGY_FILES:
        filepath = PROJECT_ROOT / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                imports = [line for line in content.split('\n') if line.startswith('import ') or line.startswith('from ')]
                functions = [line for line in content.split('\n') if line.startswith('def ')]
                classes = [line for line in content.split('\n') if line.startswith('class ')]

                file_stats[filename] = {
                    'size': len(content),
                    'lines': len(content.split('\n')),
                    'imports': len(imports),
                    'functions': len(functions),
                    'classes': len(classes),
                }
            print(f"  [OK] {filename} ({file_stats[filename]['lines']} lines)")
        else:
            print(f"  [SKIP] {filename} - NOT FOUND")

    return file_stats

def create_dependency_graph():
    graph = {
        "nodes": [
            {"id": "whale_monitor", "label": "Whale Monitor", "type": "data_source", "cycle": "15-min", "file": "whale_monitor.py"},
            {"id": "macro_filter", "label": "Macro Filter", "type": "data_source", "cycle": "60-min", "file": "macro_filter.py"},
            {"id": "qwen_bot", "label": "Qwen Unified Bot", "type": "executor", "cycle": "1-min", "file": "qwen_unified_live.py"},
            {"id": "trading_logs", "label": "Trade Logs", "type": "output", "files": ["trade_alignment_log.json"]},
        ],
        "edges": [
            {"from": "whale_monitor", "to": "qwen_bot", "data": "whale_signal.json", "impact": "+0.5x multiplier if valid"},
            {"from": "macro_filter", "to": "qwen_bot", "data": "macro_state.json", "impact": "Skip entry if EXTREME, -0.5x if NORMAL"},
            {"from": "qwen_bot", "to": "trading_logs", "data": "entry_px, exit_px, outcome", "impact": "30-day validation"},
        ],
        "failure_modes": [
            {"node": "whale_monitor", "symptom": "whale_signal.json > 30 min old", "impact": "1.0x baseline only"},
            {"node": "macro_filter", "symptom": "macro_state.json > 90 min old", "impact": "constant 0.5x penalty"},
            {"node": "qwen_bot", "symptom": "No entries despite valid signal", "impact": "trading halt"},
        ]
    }
    return graph

if __name__ == "__main__":
    print("=" * 70)
    print("LightRAG Setup: Trading Strategy Dependency Analysis")
    print("=" * 70)

    print("\n[1] Analyzing trading strategy files...")
    stats = analyze_trading_system_structure()

    print("\nFile Statistics:")
    for filename, s in stats.items():
        print(f"  {filename}: {s['lines']} lines, {s['functions']} functions, {s['classes']} classes")

    print("\n[2] Creating dependency graph...")
    graph = create_dependency_graph()

    graph_file = PROJECT_ROOT / "lightrag_dependency_graph.json"
    with open(graph_file, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    print(f"  [OK] Saved to lightrag_dependency_graph.json")

    print("\n" + "=" * 70)
    print("SETUP COMPLETE")
    print("=" * 70)
