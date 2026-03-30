# UI色定義
COLOR_READY = "#5cb85c"    # 緑 (0-1%)
COLOR_WARN = "#f0ad4e"     # 黄 (1-5%)
COLOR_FAR = "#d9534f"      # 赤 (5%+)
COLOR_BUY_LEVEL = "#4a90e2"    # 買いレベル：青
COLOR_SELL_LEVEL = "#e94b3c"   # 売りレベル：赤
COLOR_CURRENT_PRICE = "#2c3e50"  # 現在価格：黒
COLOR_GRID_FILL = "#ecf0f1"    # グリッド背景

# UI設定
UPDATE_INTERVAL = 60       # 秒（1分ごと）
CHART_HEIGHT = 500         # ピクセル
CHART_CANDLES = 100        # 表示ローソク足数
RSI_PERIOD = 14
ATR_PERIOD = 14

# ゲージ判定閾値
READY_THRESHOLD = 1.0      # % (0-1%)
WARN_THRESHOLD = 5.0       # % (1-5%)

# API設定
API_TIMEOUT = 10           # 秒
MAX_RETRIES = 3
