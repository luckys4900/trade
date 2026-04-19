import pathlib

BASE_DIR = pathlib.Path(__file__).parent
CACHE_DIR = BASE_DIR / "data" / "cache"
REPORT_DIR = BASE_DIR / "report"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DATA = {
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "timeframe": "4h",
    "start_date": "2019-01-01",
    "end_date": "2024-12-31",
    "exchange": "binance",
}

COINTEGRATION = {
    "rolling_window": 120,
    "p_value_strong": 0.01,
    "p_value_moderate": 0.05,
    "min_required_window": 120,
}

KALMAN = {
    "delta": 1e-4,
    "observation_noise": 1e-3,
}

SIGNAL = {
    "z_score_thresholds": [1.5, 2.0, 2.5],
    "lookback_windows": [60, 90, 120],
    "take_profit_z": [0.0, 0.5],
    "stop_loss_z": [3.5, 4.0, 4.5],
}

RISK = {
    "capital": 100000,
    "risk_per_trade": 0.02,
    "max_position_pct": 0.20,
    "fee_rate": 0.0005,
    "slippage_pct": 0.0002,
}

WALK_FORWARD = {
    "n_splits": 6,
    "is_ratio": 0.7,
    "min_trades_is": 30,
    "min_trades_oos": 15,
}
