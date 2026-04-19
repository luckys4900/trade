# Dockerfile for BTC Short Trading Bot on Google Cloud Run

FROM python:3.10-slim

# 作業ディレクトリ設定
WORKDIR /app

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ボットを実行
CMD ["python", "short_trading_bot_cloud.py"]
