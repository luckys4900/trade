#!/bin/bash
cd "C:/Users/user/Desktop/cursor/trade"

echo "Starting Whale Following System..."

# Kill any existing processes
pkill -f "whale_monitor\|macro_filter\|qwen_unified" 2>/dev/null || true
sleep 1

# Start whale monitor in background
python3 whale_monitor.py &
WHALE_PID=$!
echo "Whale Monitor PID: $WHALE_PID"

# Start macro filter in background
sleep 1
python3 macro_filter.py &
MACRO_PID=$!
echo "Macro Filter PID: $MACRO_PID"

# Start main trading bot in background
sleep 1
python3 qwen_unified_live.py &
MAIN_PID=$!
echo "Main Bot PID: $MAIN_PID"

sleep 5

# Check if processes are still running
echo ""
echo "=== System Status ==="
pgrep -f "whale_monitor" > /dev/null && echo "[OK] Whale Monitor" || echo "[FAIL] Whale Monitor"
pgrep -f "macro_filter" > /dev/null && echo "[OK] Macro Filter" || echo "[FAIL] Macro Filter"  
pgrep -f "qwen_unified" > /dev/null && echo "[OK] Main Trading Bot" || echo "[FAIL] Main Trading Bot"

echo ""
echo "System started. Press Ctrl+C to stop or check logs:"
echo "  - logs/whale_monitor_*.log"
echo "  - logs/macro_filter_*.log"
echo "  - logs/unified_live_*.log"

# Keep script running
wait
