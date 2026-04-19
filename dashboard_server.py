# -*- coding: utf-8 -*-
"""
Simple HTTP server for the Qwen dashboard.
- Serves static files (dashboard.html, CSS, JS) from the project root.
- Provides /api/status JSON endpoint used by the UI.
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

PROJECT_ROOT = pathlib.Path(__file__).parent
LOG_DIR = PROJECT_ROOT / "logs"
STATE_FILE = PROJECT_ROOT / "trade_state_unified.json"


def get_pythonw_count():
    """Return the number of running pythonw.exe processes (Windows)."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pythonw.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
        # The first two lines are header/footer; count remaining non‑empty lines.
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        if len(lines) <= 2:
            return 0
        return len(lines) - 2
    except Exception:
        return 0


def get_latest_log():
    """Return a list of the last 30 lines of the newest unified_live_*.log file.
    If no log exists, return an empty list.
    """
    try:
        logs = list(LOG_DIR.glob("unified_live_*.log"))
        if not logs:
            return []
        # Newest by modification time
        latest = max(logs, key=lambda p: p.stat().st_mtime)
        with latest.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        # Return last 30 stripped lines
        return [ln.rstrip("\n") for ln in lines[-30:]]
    except Exception:
        return []


def load_state():
    """Load trade_state_unified.json and return the dict, or empty dict if missing."""
    try:
        if STATE_FILE.exists():
            with STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def build_status_json():
    """Collect all monitoring data and return a JSON‑serialisable dict."""
    state = load_state()
    positions = []
    # Expect keys: ocpm, mr, rsi_swing, contrarian (lower‑case in state file)
    for name in ["ocpm", "mr", "rsi_swing", "contrarian"]:
        s = state.get(name, {})
        if s.get("in_pos"):
            positions.append(
                {
                    "strategy": name.upper() if name != "rsi_swing" else "RSISwing",
                    "side": s.get("side", ""),
                    "entry": s.get("entry_px", 0.0),
                    "sl": s.get("stop", 0.0),
                    "tp": s.get("tp", 0.0),
                    "size": s.get("size", 0.0),
                }
            )
    return {
        "bot_running": get_pythonw_count() > 0,
        "process_count": get_pythonw_count(),
        "log": get_latest_log(),
        "state": state,
        "positions": positions,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/status"):
            data = build_status_json()
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # Fall back to normal static file handling (relative to PROJECT_ROOT)
        # Change the directory context once per request for safety.
        self.directory = str(PROJECT_ROOT)
        super().do_GET()


def run_server(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"Dashboard server listening on http://localhost:{port}/dashboard.html")
    httpd.serve_forever()


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        sys.exit(0)
