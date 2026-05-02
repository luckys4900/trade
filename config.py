"""
Hyperliquid BTC 5分足自動売買システム設定ファイル
"""

# 取引所設定
EXCHANGE_CONFIG = {
    'name': 'Hyperliquid',
    'taker_fee': 0.00045,  # 0.045%
    'maker_fee': 0.00015,  # 0.015% (リベート考慮)
    'symbol': 'BTC/USD',
    'timeframe': '5m'
}

# バックテスト設定
BACKTEST_CONFIG = {
    'initial_capital': 100,  # 100 USDT
    'leverage': 5,  # 最大5倍レバレッジ
    'start_date': '2023-01-01',
    'end_date': '2024-12-31',
    'slippage': 0.0002,  # 0.02%
    'data_dir': './data/raw/'
}

# 戦略設定
STRATEGY_CONFIG = {
    'micro_breakout': {
        'risk_per_trade': 0.015,  # 1.5%リスク
        'bb_period': 20,
        'bb_std': 2.0,
        'atr_period': 14,
        'volume_multiplier': 1.5,
        'profit_target_atr': 2.0,
        'stop_loss_atr': 1.0
    },
    'mean_reversion': {
        'rsi_period': 9,
        'rsi_oversold': 25,
        'rsi_overbought': 75,
        'bb_period': 15,
        'bb_std': 2.5
    },
    'ema_ribbon': {
        'ema_fast': 5,
        'ema_mid1': 10,
        'ema_mid2': 20,
        'ema_slow': 50,
        'volume_spike_multiplier': 2.0,
        'stop_loss_pct': 0.008,
        'take_profit_pct': 0.020
    },
    'triple_top_breakout': {
        'pivot_length': 7,
        'price_tolerance_pct': 1.5,
        'min_high_count': 3,
        'bb_period': 20,
        'bb_std': 1.8,
        'atr_period': 14,
        'sl_atr_mult': 2.5,
        'tp_atr_mult': 4.0,
        'max_hold_bars': 15,
        'volume_mult': 2.5,
        'risk_per_trade': 0.02,
        'pivot_memory_bars': 70
    }
}

# 評価基準
EVALUATION_METRICS = {
    'min_annual_return': 0.8,  # 80%以上の年間リターン
    'min_sharpe_ratio': 1.3,  # 1.3以上のシャープレシオ
    'max_drawdown': 0.25,     # 25%以下の最大ドローダウン
    'min_win_rate': 0.58,     # 58%以上の勝率
    'min_trades_per_month': 100,  # 月間100トレード以上
    'min_profit_factor': 1.6,    # 1.6以上のプロフィットファクター
    'min_avg_trade': 0.004     # 0.4%以上の平均トレードリターン
}

# グリッド取引設定（LLMトレンド検出で最適化）
GRID_CONFIG = {
    'grid_levels': 5,           # グリッド本数（保守的: 5）
    'grid_spacing_pct': 0.05,   # 各レベル間隔 5.0%（広くする）
    'atr_multiplier': 3.0,      # 動的レンジ = ATR × 3
    'leverage': 1,              # レバレッジ（保守的に1倍）
    'risk_pct_per_level': 0.01, # 1レベルあたり資金の1%
    'max_open_orders': 5,       # 最大同時オープン注文数
    'timeframe': '1h',          # 1時間足
    'symbol': 'BTC',
    'atr_period': 14,           # ATR計算期間
    'check_interval': 60,       # チェック間隔（秒）
    'min_profit_pct': 0.50,     # 最小利益率 0.50%（手数料考慮）
    'maker_fee': 0.00015,       # メーカー手数料 0.015%
    'use_trend_detection': True,  # LLMトレンド検出を有効化
    'skip_in_strong_trend': True, # 強いトレンド時はグリッドを停止
}

# LLM設定（センチメント分析用）
LLM_CONFIG = {
    'primary_model': 'gpt-oss:120b-cloud',   # Cloudモデル優先
    'fallback_model': 'qwen3:8b',            # ローカルフォールバック
    'ollama_url': 'http://localhost:11434/api/generate',
    'timeout': 30,
    'use_sentiment': True,   # センチメント分析有効/無効
    'strong_trend_threshold': 0.7,  # 強いトレンド判定閾値
    'extreme_sentiment_threshold': 0.8,  # 極端なセンチメント判定閾値
}