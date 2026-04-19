# -*- coding: utf-8 -*-
"""
Hyperliquid BTC perp: L2 book + public trades logger (minimal).

Uses hyperliquid-python-sdk WebSocket (Info.subscribe + callback).

Output (default): rotating Parquet chunks under data/raw/hl_btc_l2_chunks/
  part_{n:06d}.parquet  (zstd) — safe append without corrupting a single file.

Optional: --jsonl data/raw/hl_btc_l2.jsonl (line-delimited JSON, append-friendly).

Install:
  pip install hyperliquid-python-sdk pandas pyarrow numpy

Run (mainnet, real connection):
  python hl_l2_logger.py --duration-sec 3600
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class HLL2Logger:
    def __init__(
        self,
        out_dir: Path,
        jsonl_path: Optional[Path],
        flush_interval_sec: float,
        flush_max_rows: int,
        use_testnet: bool,
    ) -> None:
        self.out_dir = out_dir
        self.jsonl_path = jsonl_path
        self.flush_interval_sec = flush_interval_sec
        self.flush_max_rows = flush_max_rows
        self._stop = threading.Event()
        self._buf: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._part = 0
        self.out_dir.mkdir(parents=True, exist_ok=True)

        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        base = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL
        self.info = Info(base_url=base, skip_ws=False)

    def _append_row(self, row: Dict[str, Any]) -> None:
        with self._lock:
            self._buf.append(row)
            if len(self._buf) >= self.flush_max_rows:
                self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if not self._buf:
            return
        df = pd.DataFrame(self._buf)
        path = self.out_dir / f"part_{self._part:06d}.parquet"
        df.to_parquet(path, compression="zstd", index=False)
        logger.info("wrote %s rows -> %s", len(df), path)
        self._part += 1
        if self.jsonl_path is not None:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                for r in self._buf:
                    f.write(json.dumps(r, default=str) + "\n")
        self._buf.clear()

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def on_l2(self, msg: Dict[str, Any]) -> None:
        try:
            if msg.get("channel") != "l2Book":
                return
            data = msg["data"]
            recv_ts = time.time()
            ex_ts = int(data.get("time", 0))
            bids = data.get("levels", [[], []])[0]
            asks = data.get("levels", [[], []])[1]
            self._append_row(
                {
                    "kind": "l2Book",
                    "recv_ts": recv_ts,
                    "ex_ts": ex_ts,
                    "coin": data.get("coin", ""),
                    "bids_json": json.dumps(bids),
                    "asks_json": json.dumps(asks),
                }
            )
        except Exception as exc:
            logger.exception("on_l2 error: %s", exc)

    def on_trades(self, msg: Dict[str, Any]) -> None:
        try:
            if msg.get("channel") != "trades":
                return
            recv_ts = time.time()
            for t in msg.get("data", []):
                self._append_row(
                    {
                        "kind": "trade",
                        "recv_ts": recv_ts,
                        "ex_ts": int(t.get("time", 0)),
                        "coin": t.get("coin", ""),
                        "px": str(t.get("px", "0")),
                        "sz": float(t.get("sz", 0) or 0),
                        "side": t.get("side", ""),
                        "hash": str(t.get("hash", "")),
                    }
                )
        except Exception as exc:
            logger.exception("on_trades error: %s", exc)

    def _flush_loop(self) -> None:
        while not self._stop.wait(self.flush_interval_sec):
            self.flush()

    def run(self, duration_sec: Optional[float]) -> None:
        self.info.subscribe({"type": "l2Book", "coin": "BTC"}, self.on_l2)
        self.info.subscribe({"type": "trades", "coin": "BTC"}, self.on_trades)
        logger.info("Subscribed l2Book + trades (BTC). Writing to %s", self.out_dir.resolve())

        flusher = threading.Thread(target=self._flush_loop, daemon=True)
        flusher.start()

        def handle_sig(*_args: Any) -> None:
            logger.info("shutdown signal")
            self._stop.set()

        signal.signal(signal.SIGINT, handle_sig)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, handle_sig)

        t0 = time.time()
        try:
            while not self._stop.is_set():
                if duration_sec is not None and (time.time() - t0) >= duration_sec:
                    logger.info("duration reached, stopping")
                    break
                time.sleep(0.25)
        finally:
            self._stop.set()
            self.flush()
            try:
                self.info.disconnect_websocket()
            except Exception as exc:
                logger.warning("disconnect: %s", exc)


def main() -> None:
    p = argparse.ArgumentParser(description="Hyperliquid L2 + trades logger (BTC)")
    p.add_argument("--out-dir", type=Path, default=Path("data/raw/hl_btc_l2_chunks"))
    p.add_argument("--jsonl", type=Path, default=None, help="Optional JSONL mirror path")
    p.add_argument("--flush-sec", type=float, default=30.0)
    p.add_argument("--flush-max-rows", type=int, default=50_000)
    p.add_argument("--duration-sec", type=float, default=None, help="Stop after N seconds (omit = run until Ctrl+C)")
    p.add_argument("--testnet", action="store_true")
    args = p.parse_args()

    log = HLL2Logger(
        out_dir=args.out_dir,
        jsonl_path=args.jsonl,
        flush_interval_sec=args.flush_sec,
        flush_max_rows=args.flush_max_rows,
        use_testnet=args.testnet,
    )
    log.run(duration_sec=args.duration_sec)


if __name__ == "__main__":
    main()
