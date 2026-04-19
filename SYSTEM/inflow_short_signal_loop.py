# -*- coding: utf-8 -*-
"""Run inflow_short_signal_builder.py every N seconds (background with pythonw)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

INTERVAL_SEC = int(os.environ.get("INFLOW_SIG_INTERVAL_SEC", "600"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "SYSTEM", "inflow_short_signal_builder.py")


def main() -> None:
    while True:
        subprocess.run([sys.executable, BUILDER], cwd=ROOT, check=False)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
