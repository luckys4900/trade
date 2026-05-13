# Clarity Act Pair Trading v3.0 - Production Checklist

本番環境運用前チェックリスト、定期メンテナンススケジュール、緊急対応手順

## 目次

1. [本番運用前チェックリスト](#本番運用前チェックリスト)
2. [日次チェック](#日次チェック)
3. [週次メンテナンス](#週次メンテナンス)
4. [月次レビュー](#月次レビュー)
5. [緊急対応手順](#緊急対応手順)
6. [インシデント記録](#インシデント記録)

---

## 本番運用前チェックリスト

本番環境への初回デプロイ前に、以下のすべてのチェックが完了していることを確認してください。

### システム構成

- [ ] 本番PC のホスト名が確定している
- [ ] SSH キーペアが生成され、公開キーが本番PC に登録されている
- [ ] ファイアウォール設定が確認済み
- [ ] Python 3.9以上がインストール済み
- [ ] ディスク容量が最低1GB以上確保されている
- [ ] メモリが最低512MB以上確保されている

### Git リポジトリ設定

- [ ] リモート `origin` が正しく設定されている (`git@github.com:luckys4900/trade.git`)
- [ ] ローカルと リモートの差分がない
- [ ] すべてのコミットが リモートにプッシュされている
- [ ] バージョンタグが作成されている（例: `v3.0.0-production-ready`）

### 環境設定

- [ ] `.env.example` が存在する
- [ ] `.env` は `.gitignore` に含まれている
- [ ] ローカルの `.env` に開発環境の API キーが設定されている
- [ ] 本番PC の `.env` に本番環境の API キーが設定されている

### Hyperliquid API 設定

- [ ] API キーが正しく設定されている
- [ ] Secret キーが正しく設定されている
- [ ] ウォレットアドレスが正しく設定されている
- [ ] テスト API コールが成功している
  ```bash
  python -c "import requests; print(requests.get('https://api.hyperliquid.xyz/info').status_code)"
  ```

### Congress.gov API 設定

- [ ] Congress.gov API にアクセス可能である
- [ ] インターネット接続が安定している

### データベースと ストレージ

- [ ] ログディレクトリ (`logs/`) が作成されている
- [ ] データディレクトリ (`data/`) が作成されている
- [ ] バックアップディレクトリ (`backups/`) が作成されている
- [ ] ディスク容量が十分確保されている

### テストと検証

- [ ] ユニットテストがすべてパスしている
  ```bash
  pytest data/test_*.py -v
  ```
- [ ] バックテストが成功している
  ```bash
  python data/clarity_act_core.py --validate --backtest
  ```
- [ ] ヘルスチェックが PASS している
  ```bash
  bash deploy_scripts/health_check.sh
  ```
- [ ] ペーパートレードが正常に実行されている（24時間以上）

### セキュリティ確認

- [ ] `.env` ファイルが本番PC で `chmod 600` に設定されている
- [ ] SSH キーが安全に保管されている（SSH エージェント推奨）
- [ ] API キーが外部に漏洩していない
- [ ] Git コミット履歴に API キーが含まれていない
  ```bash
  git log --all --full-history -- .env | grep -i api
  ```
- [ ] セキュリティスキャンがすべてパスしている
  ```bash
  bandit -r . -f json
  ```

### デプロイメント検証

- [ ] デプロイメントスクリプトが本番PC で実行可能である
- [ ] デプロイ前に `--dry-run` で動作確認を実施した
  ```bash
  bash deploy_scripts/deploy_to_production.sh --dry-run
  ```
- [ ] バックアップ作成スクリプトが正常に動作している
- [ ] ロールバック手順が確認済みである

### 運用ドキュメント整備

- [ ] `DEPLOYMENT.md` が最新の状態である
- [ ] この `PRODUCTION_CHECKLIST.md` が整備されている
- [ ] トラブルシューティングガイドが存在する
- [ ] 緊急連絡先が記録されている
- [ ] アクセス情報（ホスト、ユーザー、ポート等）がセキュアに保管されている

### 監視とアラート設定

- [ ] cron ジョブが正しく設定されている
  ```bash
  crontab -l
  ```
- [ ] ヘルスチェックスクリプトが定期実行されている（6時間ごと推奨）
- [ ] エラーログが監視されている
- [ ] Slack アラート（設定済みの場合）が機能している
- [ ] メール通知（設定済みの場合）が機能している

### ビジネス承認

- [ ] チームリーダーの承認が得られている
- [ ] 本番リリース予定日が決定している
- [ ] インシデント対応スケジュールが決定している
- [ ] 緊急時の連絡体制が整備されている

---

## 日次チェック

毎日実施するべき確認項目（推奨: 朝と夜の2回）

```bash
# 本番PC にログイン
ssh user@production_host

# ステータス確認
bash ~/trade/status.sh

# ヘルスチェック実行
bash ~/trade/deploy_scripts/health_check.sh

# ログでエラーを確認
grep ERROR ~/trade/logs/*.log | tail -20
```

### チェック項目

- [ ] Main Bot (qwen_unified_live.py) が実行中か
  ```bash
  pgrep -f "qwen_unified_live.py"
  ```

- [ ] Whale Monitor が実行中か
  ```bash
  pgrep -f "whale_monitor.py"
  ```

- [ ] Macro Filter が実行中か
  ```bash
  pgrep -f "macro_filter.py"
  ```

- [ ] エラー件数が10件以下か
  ```bash
  grep ERROR ~/trade/logs/main_bot.log | wc -l
  ```

- [ ] ディスク使用量が80%以下か
  ```bash
  df / | tail -1 | awk '{print $5}'
  ```

- [ ] ログファイルが最近更新されているか（30分以内）
  ```bash
  stat -c %Y ~/trade/logs/main_bot.log
  ```

- [ ] API 接続が成功しているか
  ```bash
  python3 -c "import requests; print('OK' if requests.get('https://api.hyperliquid.xyz/info').status_code == 200 else 'FAIL')"
  ```

### アラート条件

以下の条件のいずれかに該当した場合は、即座に対応が必要です：

- [ ] プロセスが停止している
- [ ] エラー件数が20件以上
- [ ] ディスク使用量が95%以上
- [ ] ログ更新が1時間以上ない
- [ ] API 接続が失敗している

---

## 週次メンテナンス

毎週1回（推奨: 月曜日朝）実施するメンテナンス

```bash
# 本番PC にログイン
ssh user@production_host
cd ~/trade
```

### ログの整理

```bash
# ログの圧縮
gzip logs/*.log.* 2>/dev/null || true

# 30日以上前のログを削除
find logs -name '*.log*' -mtime +30 -delete

# ログディレクトリのサイズを確認
du -sh logs/
```

- [ ] ログファイルが圧縮されている
- [ ] 古いログが削除されている
- [ ] ログディレクトリのサイズが確認済み

### バックアップの確認

```bash
# ローカルバックアップのリスト表示
ls -lh ~/trade_backup_* | tail -5

# 最新バックアップのサイズを確認
du -sh ~/trade_backup_$(ls -t ~/trade_backup_* | head -1)
```

- [ ] 最新バックアップが存在する
- [ ] バックアップのサイズが記録されている
- [ ] バックアップ日時が確認済み

### 依存関係のアップデート確認

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# アップデート可能なパッケージを確認
pip list --outdated

# セキュリティアップデートのチェック
pip install -U pip-audit && pip-audit
```

- [ ] セキュリティアップデートが確認済み
- [ ] アップデートの必要性が判断されている
- [ ] 必要に応じてアップデートが実施されている（テスト後）

### ディスク容量の確認

```bash
# ディスク使用量の詳細
du -sh ~/trade/*

# 不要なファイルをクリーンアップ
rm -rf ~/trade/__pycache__
find ~/trade -name '*.pyc' -delete
find ~/trade -name '__pycache__' -type d -delete
```

- [ ] ディスク使用量が記録されている
- [ ] 不要なファイルが削除されている
- [ ] ディスク容量が20%以上確保されている

### cron ジョブの確認

```bash
# cron ジョブの実行ログを確認
grep CRON /var/log/syslog | grep trade | tail -20

# cron ジョブの設定を確認
crontab -l
```

- [ ] cron ジョブが定期実行されている
- [ ] エラーが記録されていない

---

## 月次レビュー

毎月1回（推奨: 月初）実施する総合レビュー

### パフォーマンス分析

```bash
# ログからパフォーマンス統計を抽出
python3 << 'EOF'
import json
from pathlib import Path
from datetime import datetime, timedelta

logs_dir = Path("logs")
one_month_ago = datetime.now() - timedelta(days=30)

# ログファイルを解析
errors = 0
warnings = 0
for log_file in logs_dir.glob("*.log"):
    if log_file.stat().st_mtime > one_month_ago.timestamp():
        with open(log_file) as f:
            for line in f:
                if "ERROR" in line:
                    errors += 1
                elif "WARNING" in line:
                    warnings += 1

print(f"Errors (30日): {errors}")
print(f"Warnings (30日): {warnings}")
print(f"Average per day: {errors/30:.1f} errors/day")
EOF
```

- [ ] エラー件数が分析されている
- [ ] パフォーマンス指標が記録されている
- [ ] トレンドが確認されている

### セキュリティアップデート確認

```bash
# システムアップデートを確認
sudo apt update
sudo apt list --upgradable

# セキュリティパッチのチェック
sudo unattended-upgrade -d
```

- [ ] OS のセキュリティアップデートが確認済み
- [ ] Python パッケージのセキュリティアップデートが確認済み
- [ ] 必要に応じてアップデートが計画されている

### 本番リリースノート作成

```bash
# 前月のコミットを確認
git log --since="1 month ago" --oneline | wc -l

# リリースノートを作成
cat > releases/RELEASE_$(date +%Y%m).md << 'EOF'
# Release Notes - $(date +%B %Y)

## Summary
- Total commits: X
- Major updates: X
- Bug fixes: X
- Security updates: X

## Highlights
- Feature A
- Feature B
- Bug fix C

## Breaking Changes
- None

## Upgrade Instructions
1. Pull latest code
2. Run tests
3. Deploy to staging
4. Deploy to production
EOF
```

- [ ] リリースノートが作成されている
- [ ] 主要な変更が記録されている
- [ ] アップグレード手順が確認されている

### バックアップポリシーレビュー

```bash
# バックアップ保持期間を確認
find ~/trade_backup_* -type d -printf '%T@ %p\n' | sort -n | tail -10

# バックアップの復旧テストを実施（オプション）
# ステージング環境でバックアップから復旧してテスト
```

- [ ] バックアップが定期的に実施されている
- [ ] バックアップの保持期間が適切である
- [ ] 復旧テストが実施されている（オプション）

### ユーザーフィードバック収集

- [ ] チームからのフィードバックを収集
- [ ] 問題報告がないか確認
- [ ] 改善提案を記録
- [ ] 次月の対応計画を作成

---

## 緊急対応手順

本番環境で障害が発生した場合の対応手順

### インシデント検出

**状況**: Main Bot が停止している

```bash
# 症状確認
pgrep -f "qwen_unified_live.py" || echo "NOT RUNNING"

# ログを確認
tail -50 ~/trade/logs/main_bot.log

# エラー詳細を抽出
grep ERROR ~/trade/logs/main_bot.log | tail -20
```

**対応フロー**:

1. [ ] インシデントの発生を確認
2. [ ] 原因を特定
3. [ ] 簡易対応を実施（以下参照）
4. [ ] 本格対応を計画

### Level 1 - 簡易対応（5分以内）

```bash
# プロセスを再起動
bash ~/trade/stop.sh
sleep 5
bash ~/trade/startup.sh

# 起動確認
bash ~/trade/status.sh

# ログで復旧を確認
tail -20 ~/trade/logs/main_bot.log
```

- [ ] プロセスが再起動された
- [ ] 起動に成功している
- [ ] ログで正常に動作している

### Level 2 - 軽度トラブル（15分以内）

**症状**: API 接続エラー、設定エラー

```bash
# API 接続をテスト
python3 << 'EOF'
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("HYPERLIQUID_API_KEY")
print(f"API Key configured: {bool(api_key)}")

import requests
try:
    r = requests.get("https://api.hyperliquid.xyz/info", timeout=5)
    print(f"API Response: {r.status_code}")
except Exception as e:
    print(f"API Error: {e}")
EOF

# 設定を再確認
grep -E "^HYPERLIQUID|^TRADING_ENV" ~/.env

# サービスを再起動
bash ~/trade/stop.sh
source ~/trade/venv/bin/activate
bash ~/trade/startup.sh
```

- [ ] API 接続が確認されている
- [ ] 設定が正しく設定されている
- [ ] サービスが再起動されている

### Level 3 - 重度障害（30分以内）

**症状**: デプロイメント後の大規模障害、データベース破損

```bash
# 即座にロールバック
bash ~/trade/deploy_scripts/deploy_to_production.sh \
    --rollback ./backups/remote_backup_YYYYMMDD_HHMMSS/

# または手動ロールバック
rsync -avz ~/trade_backup_latest/ ~/trade/

# サービスを再起動
bash ~/trade/stop.sh
bash ~/trade/startup.sh

# 復旧確認
bash ~/trade/status.sh
bash ~/trade/deploy_scripts/health_check.sh
```

- [ ] ロールバックが実行された
- [ ] サービスが復旧している
- [ ] ヘルスチェックが PASS している

### Level 4 - 致命的障害（即座）

**症状**: ファイルシステム破損、本番PC クラッシュ

```bash
# 本番PC の状態確認
ssh user@production_host "df -h && free -h && top -b -n 1 | head -20"

# ディスク容量が満杯の場合
ssh user@production_host "rm -rf ~/trade/logs/* && du -sh ~/trade/*"

# メモリ不足の場合
ssh user@production_host "killall -9 python3 ; sleep 5 ; bash ~/trade/startup.sh"

# 完全にクラッシュしている場合
# → 本番PC を再起動（システム管理者に連絡）
ssh user@production_host "sudo reboot"

# 再起動後の復旧
ssh user@production_host "bash ~/trade/startup.sh"
```

- [ ] 問題の原因を特定している
- [ ] システム管理者に報告している
- [ ] 復旧計画を立てている

### インシデント報告

```bash
# インシデントレポートを作成
cat > incident_report_$(date +%Y%m%d_%H%M%S).md << 'EOF'
# Incident Report

**Date**: $(date)
**Severity**: [Critical/High/Medium/Low]
**Status**: [Ongoing/Resolved]

## Summary
[3行での説明]

## Timeline
- HH:MM - [事象]
- HH:MM - [対応]
- HH:MM - [復旧]

## Root Cause
[原因分析]

## Impact
- Service downtime: X minutes
- Affected users: X
- Data loss: None/Details

## Resolution
[実施した対応]

## Prevention
[今後の予防策]

## Post-Mortem
[改善点]

EOF
```

- [ ] インシデントレポートが作成されている
- [ ] チーム内で共有されている
- [ ] 改善策が検討されている

---

## インシデント記録

本番環境で発生したインシデントの記録

### テンプレート

```markdown
### [日付] - [インシデント名]

**発生時刻**: YYYY-MM-DD HH:MM:SS
**検出時刻**: YYYY-MM-DD HH:MM:SS
**復旧時刻**: YYYY-MM-DD HH:MM:SS
**ダウンタイム**: X分

**原因**: 

**対応**: 

**予防策**: 

**担当者**: 
```

### 記録例

```markdown
### 2026-05-14 - Main Bot クラッシュ

**発生時刻**: 2026-05-14 09:00:00
**検出時刻**: 2026-05-14 09:05:00
**復旧時刻**: 2026-05-14 09:12:00
**ダウンタイム**: 12分

**原因**: メモリリーク（依存パッケージのバグ）

**対応**: 
1. プロセスを再起動
2. ログを確認してメモリリークを特定
3. パッケージをアップグレード

**予防策**: 
- 定期的なメモリ監視を追加
- パッケージの自動アップデートスキャン
- ユニットテストの強化

**担当者**: DevOps Team
```

---

## 関連ドキュメント

- `DEPLOYMENT.md` - デプロイメント手順
- `README.md` - プロジェクト概要
- `.github/workflows/` - CI/CD パイプライン

---

**最終更新**: 2026-05-14
**バージョン**: Clarity Act v3.0
