#!/bin/bash
# Auto-run Multi-Agent Trading System with monitoring

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOG_DIR="$PROJECT_DIR/multi_agent_logs"
REPORT_FILE="$LOG_DIR/multi_agent_report.txt"

echo "========================================"
echo "Multi-Agent Trading System - Auto Run"
echo "========================================"
echo "Started: $(date)"

# Run system
cd "$PROJECT_DIR"
python3 multi_agent_system.py

# Display dashboard
echo ""
echo "Generating dashboard..."
python3 monitor_dashboard.py > "$REPORT_FILE"

# Append simulation
echo "" >> "$REPORT_FILE"
python3 simulate_monthly.py >> "$REPORT_FILE"

echo ""
echo "========================================"
echo "Completed: $(date)"
echo "Report: $REPORT_FILE"
echo "========================================"

# Show summary
tail -20 "$REPORT_FILE"
