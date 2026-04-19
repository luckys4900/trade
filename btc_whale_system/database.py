import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class WhaleDatabase:
    def __init__(self, db_path: str = "data/whales_db.sqlite"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS whales (
                    id INTEGER PRIMARY KEY,
                    address TEXT UNIQUE,
                    balance_btc REAL,
                    first_seen_ts INTEGER,
                    tx_count INTEGER,
                    discovered_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roi_results (
                    id INTEGER PRIMARY KEY,
                    address TEXT,
                    inflow_date TEXT,
                    inflow_price_usd REAL,
                    current_price_usd REAL,
                    roi_pct REAL,
                    annualized_roi_pct REAL,
                    holding_days INTEGER,
                    calculated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY,
                    address TEXT,
                    strategy TEXT,
                    entry_date TEXT,
                    exit_date TEXT,
                    roi_pct REAL,
                    annualized_roi_pct REAL,
                    tested_at TEXT
                )
            """)
            conn.commit()

    def save_whales(self, whales: List[Dict]):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().isoformat()
            for whale in whales:
                conn.execute("""
                    INSERT OR REPLACE INTO whales 
                    (address, balance_btc, first_seen_ts, tx_count, discovered_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    whale['address'],
                    whale['balance_btc'],
                    whale['first_seen_ts'],
                    whale.get('tx_count', 0),
                    now,
                    now
                ))
            conn.commit()

    def load_all_whales(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM whales ORDER BY balance_btc DESC").fetchall()
            return [dict(row) for row in rows]

    def save_roi_result(self, roi_data: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO roi_results 
                (address, inflow_date, inflow_price_usd, current_price_usd, roi_pct, annualized_roi_pct, holding_days, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                roi_data['address'],
                roi_data.get('inflow_date'),
                roi_data.get('inflow_price_usd'),
                roi_data.get('current_price_usd'),
                roi_data['roi_pct'],
                roi_data['annualized_roi_pct'],
                roi_data['holding_days'],
                datetime.now().isoformat()
            ))
            conn.commit()

    def save_backtest_result(self, backtest_data: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO backtest_results
                (address, strategy, entry_date, exit_date, roi_pct, annualized_roi_pct, tested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                backtest_data['address'],
                backtest_data['strategy'],
                backtest_data['entry_date'],
                backtest_data['exit_date'],
                backtest_data['roi_pct'],
                backtest_data['annualized_roi_pct'],
                datetime.now().isoformat()
            ))
            conn.commit()

    def export_daily_snapshot(self, filename: str = None) -> str:
        if not filename:
            filename = f"data/whales_daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        whales = self.load_all_whales()
        snapshot = {
            "generated_at": datetime.now().isoformat(),
            "whale_count": len(whales),
            "whales": whales
        }
        
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        
        return filename
