import os
import json
import time
from glob import glob

def get_latest_log():
    log_files = glob("logs/unified_live_*.log")
    if not log_files: return None
    return max(log_files, key=os.path.getmtime)

def read_state():
    if os.path.exists("trade_state_unified.json"):
        try:
            with open("trade_state_unified.json") as f:
                return json.load(f)
        except: pass
    return {}

def draw_dashboard():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("\033[1;36m" + "="*60)
        print("  QWEN UNIFIED TERMINAL DASHBOARD (polyrec-style)")
        print("="*60 + "\033[0m")
        
        state = read_state()
        bar = state.get('current_bar', 0)
        
        # Read latest log line for price/bal info
        latest_log = get_latest_log()
        price_str, bal_str, rsi_str, trend_str = "N/A", "N/A", "N/A", "N/A"
        recent_logs = []
        if latest_log:
            try:
                with open(latest_log, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_logs = lines[-5:]
                    for line in reversed(lines):
                        if "Price: $" in line:
                            parts = line.split('|')
                            for p in parts:
                                if "Price:" in p: price_str = p.replace("Price:","").strip()
                                if "Bal:" in p: bal_str = p.replace("Bal:","").strip()
                                if "RSI:" in p: rsi_str = p.replace("RSI:","").strip()
                                if "Trend:" in p: trend_str = p.replace("Trend:","").strip()
                            break
            except: pass

        print(f"\n\033[1;32m[ MARKET DATA ]\033[0m")
        print(f" Current Bar : {bar}")
        print(f" BTC Price   : \033[1;33m{price_str}\033[0m")
        print(f" Account Bal : \033[1;32m{bal_str}\033[0m")
        print(f" RSI (4h)    : {rsi_str}")
        print(f" Trend       : {trend_str}")
        
        print(f"\n\033[1;35m[ STRATEGY POSITIONS ]\033[0m")
        print(f" {'Strategy':<12} | {'Status':<10} | {'Side':<6} | {'Entry':<10} | {'Stop/TP':<15}")
        print("-" * 60)
        for strat in ["ocpm", "mr", "rsi_swing"]:
            s_data = state.get(strat, {})
            name = s_data.get('name', strat.upper())
            in_pos = s_data.get('in_pos', False)
            side = s_data.get('side', '-')
            entry = s_data.get('entry_px', 0)
            stop = s_data.get('stop', 0)
            status = "\033[1;32mACTIVE\033[0m" if in_pos else "\033[1;30mWAITING\033[0m"
            side_colored = f"\033[1;32m{side}\033[0m" if side=="LONG" else (f"\033[1;31m{side}\033[0m" if side=="SHORT" else side)
            print(f" {name:<12} | {status:<19} | {side_colored:<15} | {entry:<10.2f} | SL:{stop:.2f}")

        print(f"\n\033[1;36m[ SYSTEM LOGS ]\033[0m")
        for log in recent_logs[-5:]:
            print(f"  {log.strip()}")
            
        print("\n\033[1;30m(Press Ctrl+C to exit dashboard)\033[0m")
        time.sleep(2)

if __name__ == "__main__":
    try:
        draw_dashboard()
    except KeyboardInterrupt:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("Dashboard closed.")