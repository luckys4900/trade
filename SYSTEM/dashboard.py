#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Whale Trading System Dashboard - With Account Status"""

import json
import os
import sys
import subprocess
import time
import re
from datetime import datetime

def read_signal():
    try:
        with open('whale_signal.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def read_macro():
    try:
        with open('macro_state.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def read_contrarian_signal():
    try:
        with open('kronos_contrarian_signal.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def read_inflow_short_signal():
    """EV1 supplementary SHORT bias (inflow_short_signal.json); not a separate trade_state row."""
    try:
        with open('inflow_short_signal.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def read_account_state():
    try:
        with open('logs/account_state.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def read_trade_state():
    try:
        with open('trade_state_unified.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def get_process_count():
    try:
        result = subprocess.run(['tasklist'], capture_output=True, text=True)
        count = result.stdout.count('python')
        return count
    except:
        return 0

def read_last_log_line(logfile):
    """Read and extract key info from last log line"""
    try:
        if not os.path.exists(logfile):
            return None
        
        with open(logfile, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        if not lines:
            return None
        
        # Find last non-empty line
        for line in reversed(lines):
            line = line.strip()
            if line:
                # Extract the important part
                parts = line.split('] ', 1)
                if len(parts) > 1:
                    message = parts[1]
                else:
                    message = line
                
                # Truncate if too long
                if len(message) > 65:
                    message = message[:62] + "..."
                
                return message
        
        return None
    except:
        return None

def show_dashboard():
    os.system('cls' if os.name == 'nt' else 'clear')
    
    signal = read_signal()
    macro = read_macro()
    contrarian_signal = read_contrarian_signal()
    inflow_short = read_inflow_short_signal()
    account = read_account_state()
    trade_state = read_trade_state()
    proc_count = get_process_count()
    now = datetime.now()
    
    # Header
    print("=" * 72)
    print("WHALE FOLLOWING TRADING SYSTEM - DASHBOARD")
    print("=" * 72)
    print("Update: {}".format(now.strftime('%Y-%m-%d %H:%M:%S')))
    print()
    
    # Process Status
    print("[SYSTEM STATUS]")
    if proc_count >= 6:
        print("  Processes: {} running (OK, full stack)".format(proc_count))
    elif proc_count >= 4:
        print("  Processes: {} running (OK)".format(proc_count))
    else:
        print("  Processes: {} running (WARN - expect 4+; 6 if inflow + EV1 loop running)".format(proc_count))
    print()
    
    # Account Status
    print("[ACCOUNT STATUS]")
    if account:
        acc = account.get('account', {})
        balance = acc.get('balance', 0.0)
        equity = acc.get('equity', 0.0)
        margin_used = acc.get('margin_used', 0.0)
        withdrawable = acc.get('withdrawable', acc.get('available_margin'))

        print("  Balance: ${:.2f}".format(balance))
        print("  Equity: ${:.2f}".format(equity))
        print("  Margin Used: ${:.2f}".format(margin_used))
        if withdrawable is not None:
            print("  Withdrawable: ${:.2f}".format(float(withdrawable)))
        
        # Positions
        positions = account.get('positions', [])
        print()
        print("[POSITIONS]")
        if positions and len(positions) > 0 and positions[0].get('size', 0) != 0:
            for pos in positions:
                symbol = pos.get('symbol', 'N/A')
                size = pos.get('size', 0.0)
                side = pos.get('side', 'NONE')
                entry = pos.get('entry_price', 0.0)
                current = pos.get('current_price', 0.0)
                pnl = pos.get('unrealized_pnl', 0.0)
                
                if size != 0:
                    print("  {} ({:+.4f}): {} @ ${:.2f}, Current: ${:.2f} [PnL: ${:+.2f}]".format(
                        symbol, size, side, entry, current, pnl))
        else:
            print("  No active positions")
    else:
        print("  (No account data - bot may not be running)")
    print()
    
    # Whale Signal
    print("[WHALE SIGNAL]")
    if signal:
        direction = signal.get('direction', 'NONE')
        valid = signal.get('valid', False)
        strength = signal.get('strength', 0.0)
        n_ranked = signal.get('n_ranked', 0)
        
        status = "SIGNAL!" if valid else "WAITING"
        color_indicator = "[{}]".format(status)
        print("  Direction: {} {} | Strength: {:.2f} | Wallets: {}".format(
            direction, color_indicator, strength, n_ranked))
    else:
        print("  (No signal data)")
    print()
    
    # Macro Filter
    print("[MARKET CONDITIONS]")
    if macro:
        regime = macro.get('regime', 'UNKNOWN')
        atr = macro.get('atr_ratio', 0.0)
        caution = macro.get('caution_mode', False)
        
        status = "CAUTION!" if caution else "NORMAL"
        print("  Regime: {} ({}) | ATR: {:.4f}".format(regime, status, atr))
    else:
        print("  (No macro data)")
    print()

    print("[CONTRARIAN SIGNAL]")
    if contrarian_signal:
        contra_dir = contrarian_signal.get('contrarian_direction', 'NONE')
        kronos_dir = contrarian_signal.get('kronos_direction', 'UNKNOWN')
        valid = contrarian_signal.get('valid', False)
        samples = contrarian_signal.get('samples', 0)
        pred_close = contrarian_signal.get('pred_close', 0.0)
        current_close = contrarian_signal.get('current_close', 0.0)
        status = "SIGNAL!" if valid else "WAITING"
        print("  Kronos: {} -> Contrarian: {} [{}] | Samples: {}".format(
            kronos_dir, contra_dir, status, samples))
        print("  Pred: ${:.2f} | Current: ${:.2f}".format(pred_close, current_close))
    else:
        print("  (No contrarian signal)")
    print()

    print("[EV1 INFLOW SHORT]")
    if inflow_short:
        valid = inflow_short.get("valid", False)
        sig = inflow_short.get("signal", "NONE")
        strength = float(inflow_short.get("strength", 0.0))
        reason = inflow_short.get("reason", "")
        ex = inflow_short.get("last_event_exchange")
        ibtc = inflow_short.get("last_event_inflow_btc")
        ev_at = inflow_short.get("evaluated_at_utc", "")
        state = "BOOST" if valid else "OFF"
        print("  State: {} | Signal: {} | Strength: {:.2f}".format(state, sig, strength))
        if ex is not None or ibtc is not None:
            print("  Last event: {} | {:.2f} BTC".format(ex or "?", float(ibtc) if ibtc is not None else 0.0))
        if reason:
            r = reason if len(reason) <= 72 else reason[:69] + "..."
            print("  Reason: {}".format(r))
        if ev_at:
            print("  Evaluated: {}".format(ev_at))
    else:
        print("  (No inflow_short_signal.json — run inflow_short_signal_builder or START preflight)")
    print()

    print("[STRATEGY STATES]")
    if trade_state:
        for key, label in [
            ('ocpm', 'OCPM'),
            ('mr', 'RangeMR'),
            ('rsi_swing', 'RSISwing'),
            ('contrarian', 'Contrarian'),
        ]:
            state = trade_state.get(key, {})
            in_pos = state.get('in_pos', False)
            side = state.get('side', 'NONE') or 'NONE'
            size = state.get('size', 0.0)
            entry = state.get('entry_px', 0.0)
            status = "IN POSITION" if in_pos else "FLAT"
            print("  {:<12} {:<11} {:<5} size={:.4f} entry=${:.2f}".format(
                label + ':', status, side, size, entry))
    else:
        print("  (No strategy state)")
    print("  Note: EV1 is a SHORT size multiplier in the bot, not a row above.")
    print()
    
    # Latest Activity
    print("[LATEST ACTIVITY]")
    
    logs = [
        ('logs/whale_monitor_live.log', 'Whale'),
        ('logs/macro_filter_live.log', 'Macro'),
        ('logs/kronos_predictor_live.log', 'Kronos'),
        ('logs/qwen_unified_live.log', 'Bot'),
    ]
    
    for logfile, name in logs:
        last_line = read_last_log_line(logfile)
        if last_line:
            print("  {:<8} {}".format(name + ":", last_line))
        else:
            if os.path.exists(logfile):
                print("  {:<8} (no recent activity)".format(name + ":"))
            else:
                print("  {:<8} (log not found)".format(name + ":"))
    
    print()
    print("=" * 72)
    print("[AUTO-REFRESH] Every 5 sec | [EXIT] Ctrl+C")
    print("=" * 72)
    print()

if __name__ == '__main__':
    try:
        while True:
            show_dashboard()
            time.sleep(5)
    except KeyboardInterrupt:
        print("Dashboard stopped.")
        sys.exit(0)
