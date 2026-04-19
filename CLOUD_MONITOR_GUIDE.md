# Cloud Bot Monitor - 使用ガイド

**目的:** クラウドで実行中のボットをPCから監視する

---

## 🚀 セットアップ（初回のみ）

### ステップ 1: Google Cloud 認証情報を設定

```bash
# Google Cloud SDK をインストール（未インストールの場合）
# https://cloud.google.com/sdk/docs/install

# Google Cloud に認証
gcloud auth login

# プロジェクトを設定
gcloud config set project YOUR_PROJECT_ID
```

### ステップ 2: 環境変数を設定

**Windows (PowerShell)**
```powershell
$env:GOOGLE_CLOUD_PROJECT = "your-project-id"
```

**Windows (コマンドプロンプト)**
```cmd
set GOOGLE_CLOUD_PROJECT=your-project-id
```

**Mac/Linux**
```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
```

---

## 📊 ダッシュボード表示

### 基本的な使用方法

```bash
cd C:\Users\user\Desktop\cursor\trade\

# 最新のログを表示（過去2時間）
python cloud_monitor.py

# 過去24時間のログを表示
python cloud_monitor.py --minutes 1440

# 詳細統計を表示
python cloud_monitor.py --stats
```

---

## 📈 ダッシュボード出力例

```
================================================================================
CLOUD BOT MONITOR DASHBOARD
================================================================================

【ステータス】
  🟢 実行モード: LIVE
  ⏰ 最終実行: 2026-03-18 05:07:12

【現在の市場情報】
  💰 価格: $74,425.00
  📊 RSI: 54.6 🟢 正常
  💵 残高: 199.12 USDC

【最新シグナル】
  ⏸️ シグナルなし（待機中）

【エントリー履歴（直近5件）】
  • 2026-03-18 02:15:30 - SHORT ENTRY
  • 2026-03-18 02:16:00 - PROFIT TARGET
  • 2026-03-18 03:45:20 - SHORT ENTRY
  • 2026-03-18 03:46:15 - STOP LOSS

【エラー/警告（直近3件）】
  ⚠️ 2026-03-18 01:00:00
     API connection timeout (retrying)

【実行統計】
  総実行回数: 24 回
  エントリー数: 5 件
  エラー数: 1 件

================================================================================
```

---

## 🔍 オプション一覧

```bash
# 過去N分間のログを表示
python cloud_monitor.py --minutes 60

# 最大ログ数を指定
python cloud_monitor.py --limit 200

# プロジェクトIDを直接指定
python cloud_monitor.py --project-id your-project-id

# 統計情報を表示
python cloud_monitor.py --stats

# 複合オプション
python cloud_monitor.py --minutes 1440 --stats --limit 500
```

---

## 📋 ダッシュボードの見方

| 項目 | 意味 | アイコン |
|------|------|---------|
| **ステータス** | LIVE = リアルトレード, PAPER = シミュレーション | 🟢/🟡 |
| **価格** | 現在のBTC価格 | 💰 |
| **RSI** | Relative Strength Index（過買い判定） | 📊 |
| **残高** | アカウント残高 | 💵 |
| **シグナル** | 最新のトレードシグナル | 🔵/🟢/🔴 |
| **エントリー履歴** | 最近のトレード一覧 | - |
| **エラー** | 警告やエラーログ | ⚠️/❌ |

---

## 🎯 リアルタイム監視スクリプト

毎分自動更新する監視スクリプト：

```bash
# PowerShell
$projectId = "your-project-id"
while ($true) {
    Clear-Host
    python cloud_monitor.py --project-id $projectId --stats
    Start-Sleep -Seconds 60
}

# Bash
while true; do
    clear
    python cloud_monitor.py --stats
    sleep 60
done
```

---

## 🔧 トラブルシューティング

### エラー: "Google Cloud Project ID not set"

```bash
# 環境変数を設定してから実行
export GOOGLE_CLOUD_PROJECT=your-project-id
python cloud_monitor.py
```

### エラー: "No logs found"

```bash
# 以下を確認
1. Cloud Logging が有効化されているか
   gcloud services enable logging.googleapis.com

2. ボットが実行されているか
   gcloud run services list --region us-central1

3. ログに遅延があるか（最大数分かかる場合あり）
```

### エラー: "Permission denied"

```bash
# 認証を再実行
gcloud auth login

# プロジェクトを確認
gcloud config list
```

---

## 📊 実行結果の保存

ログをファイルに保存：

```bash
# テキストファイルに保存
python cloud_monitor.py --stats > cloud_logs_$(date +%Y%m%d_%H%M%S).txt

# ブラウザで視覚化（Cloud Console）
# https://console.cloud.google.com/logs
```

---

## 🎯 自動監視スケジュール

毎日朝9時に監視結果をメール：

```python
# schedule_monitor.py
import schedule
import subprocess
import smtplib
from email.mime.text import MIMEText

def send_report():
    result = subprocess.run(
        ['python', 'cloud_monitor.py', '--stats'],
        capture_output=True,
        text=True
    )

    # メール送信（実装省略）

schedule.every().day.at("09:00").do(send_report)

while True:
    schedule.run_pending()
```

---

## ✅ チェックリスト

- [ ] Google Cloud SDK インストール
- [ ] gcloud auth login 実行
- [ ] GOOGLE_CLOUD_PROJECT 環境変数を設定
- [ ] python cloud_monitor.py を実行
- [ ] ダッシュボードが表示されることを確認
- [ ] --stats オプションで詳細統計を確認

---

**これであなたのクラウドボットを PC から24/7監視できます！** 📊🚀
