import sqlite3, json, logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class TradeDatabase:
    def __init__(self, db_path='trades.db'):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.connection.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, pair TEXT NOT NULL, side TEXT NOT NULL, entry_time TEXT NOT NULL, entry_price REAL NOT NULL, exit_time TEXT, exit_price REAL, quantity REAL NOT NULL, pnl REAL, pnl_pct REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS parameters (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, config TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS session_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, event TEXT NOT NULL, message TEXT, details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS backtest_results (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, pair TEXT, total_trades INTEGER, win_rate REAL, sharpe_ratio REAL, max_drawdown REAL, total_return_pct REAL, results TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.connection.commit()

    def save_trade(self, trade_data: Dict) -> int:
        cursor = self.connection.cursor()
        cursor.execute('INSERT INTO trades (pair, side, entry_time, entry_price, exit_time, exit_price, quantity, pnl, pnl_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (trade_data.get('pair'), trade_data.get('side'), trade_data.get('entry_time'), trade_data.get('entry_price'), trade_data.get('exit_time'), trade_data.get('exit_price'), trade_data.get('quantity'), trade_data.get('pnl'), trade_data.get('pnl_pct')))
        self.connection.commit()
        return cursor.lastrowid

    def get_trade(self, trade_id: int) -> Optional[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_trades(self, limit: int = 1000) -> List[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM trades ORDER BY created_at DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_trades_by_pair(self, pair: str, limit: int = 100) -> List[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM trades WHERE pair = ? ORDER BY created_at DESC LIMIT ?', (pair, limit))
        return [dict(row) for row in cursor.fetchall()]

    def save_parameters(self, name: str, params: Dict) -> None:
        cursor = self.connection.cursor()
        config_json = json.dumps(params)
        cursor.execute('INSERT OR REPLACE INTO parameters (name, config, updated_at) VALUES (?, ?, ?)', (name, config_json, datetime.now().isoformat()))
        self.connection.commit()

    def get_parameters(self, name: str) -> Optional[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT config FROM parameters WHERE name = ?', (name,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def save_session_log(self, log_data: Dict) -> int:
        cursor = self.connection.cursor()
        details_json = json.dumps(log_data.get('details', {}))
        cursor.execute('INSERT INTO session_logs (timestamp, event, message, details) VALUES (?, ?, ?, ?)', (log_data.get('timestamp'), log_data.get('event'), log_data.get('message'), details_json))
        self.connection.commit()
        return cursor.lastrowid

    def get_session_logs(self, limit: int = 100) -> List[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM session_logs ORDER BY created_at DESC LIMIT ?', (limit,))
        logs = []
        for row in cursor.fetchall():
            log_dict = dict(row)
            if log_dict.get('details'):
                log_dict['details'] = json.loads(log_dict['details'])
            logs.append(log_dict)
        return logs

    def save_backtest_results(self, name: str, results: Dict) -> None:
        cursor = self.connection.cursor()
        results_json = json.dumps(results)
        cursor.execute('INSERT OR REPLACE INTO backtest_results (name, pair, total_trades, win_rate, sharpe_ratio, max_drawdown, total_return_pct, results) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (name, results.get('pair'), results.get('total_trades'), results.get('win_rate'), results.get('sharpe_ratio'), results.get('max_drawdown'), results.get('total_return_pct'), results_json))
        self.connection.commit()

    def get_backtest_results(self, name: str) -> Optional[Dict]:
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM backtest_results WHERE name = ?', (name,))
        row = cursor.fetchone()
        if row:
            result_dict = dict(row)
            if result_dict.get('results'):
                result_dict['details'] = json.loads(result_dict['results'])
            return result_dict
        return None

    def get_statistics(self) -> Dict:
        cursor = self.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM trades WHERE exit_price IS NOT NULL')
        total_trades = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl > 0')
        winning_trades = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl <= 0')
        losing_trades = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(SUM(pnl), 0) FROM trades')
        total_pnl = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(AVG(pnl), 0) FROM trades WHERE pnl > 0')
        avg_win = cursor.fetchone()[0]
        cursor.execute('SELECT COALESCE(AVG(pnl), 0) FROM trades WHERE pnl <= 0')
        avg_loss = cursor.fetchone()[0]
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        return {'total_trades': total_trades, 'winning_trades': winning_trades, 'losing_trades': losing_trades, 'win_rate': win_rate, 'total_pnl': total_pnl, 'avg_win': avg_win, 'avg_loss': avg_loss}

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
