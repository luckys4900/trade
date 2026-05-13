# Clarity Act Pair Trading v3.0 - Deployment Guide

本番環境へのデプロイメント手順および本番PC設定ガイド

## 目次

1. [前提条件](#前提条件)
2. [ローカル開発環境](#ローカル開発環境)
3. [本番PC初期セットアップ](#本番pc初期セットアップ)
4. [デプロイメント手順](#デプロイメント手順)
5. [ロールバック手順](#ロールバック手順)
6. [トラブルシューティング](#トラブルシューティング)
7. [モニタリング](#モニタリング)

---

## 前提条件

### ローカルマシン

- Git がインストール済み
- Python 3.9以上
- SSH キーペアが生成済み
- GitHub アカウントへのアクセス権限

### 本番PC

- Linux (Ubuntu 20.04 LTS 以上)
- Python 3.9以上
- SSH サーバーが起動中
- ディスク容量: 最低 1GB以上

### ネットワーク

- ローカルマシンから本番PC へのSSH接続可能
- インターネットへのアウトバウンド接続可能
- Hyperliquid API へのアクセス可能

---

## ローカル開発環境

### 1. リポジトリのクローン

```bash
git clone git@github.com:luckys4900/trade.git
cd trade
```

### 2. Python 仮想環境セットアップ

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# または
.\venv\Scripts\activate   # Windows
```

### 3. 依存関係インストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 環境設定

```bash
cp .env.example .env
# .env を編集して API キーを設定
vi .env
```

### 5. テスト実行

```bash
# ユニットテスト
pytest data/test_*.py -v

# バックテスト検証
python data/clarity_act_core.py --validate --backtest
```

---

## 本番PC初期セットアップ

### 1. 本番PC へのアクセス確認

```bash
# SSH 接続テスト
ssh user@production_host "echo 'Connection OK'"
```

### 2. 自動セットアップスクリプト実行

```bash
# ローカルマシンから本番PC にセットアップスクリプトをコピー
scp deploy_scripts/setup_production_pc.sh user@production_host:/tmp/

# 本番PC で実行
ssh user@production_host "bash /tmp/setup_production_pc.sh"
```

または、本番PC 上で直接実行:

```bash
# 本番PC にログイン
ssh user@production_host

# セットアップスクリプトをダウンロード
cd ~
git clone git@github.com:luckys4900/trade.git trade
cd trade
bash deploy_scripts/setup_production_pc.sh
```

### 3. 自動セットアップで実施される内容

```
✓ Python 仮想環境作成
✓ 依存関係インストール
✓ ディレクトリ構成作成
✓ .env ファイル作成
✓ cron ジョブ設定
✓ systemd サービス設定（オプション）
```

### 4. API キー設定

本番PC で `.env` ファイルを編集:

```bash
vi /home/user/trade/.env
```

以下を設定:

```
HYPERLIQUID_API_KEY=your_production_api_key
HYPERLIQUID_SECRET_KEY=your_production_secret_key
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address
```

### 5. 設定検証

```bash
# ヘルスチェック実行
bash /home/user/trade/deploy_scripts/health_check.sh

# ステータス確認
bash /home/user/trade/status.sh
```

---

## デプロイメント手順

### 方法1: 自動デプロイメントスクリプト使用

#### 1. デプロイ前チェック

```bash
cd /Users/user/Desktop/trade

# Git 状態確認
git status
git log --oneline -5

# テスト実行
pytest data/test_*.py -v

# バックテスト検証
python data/clarity_act_core.py --validate --backtest
```

#### 2. コミットとプッシュ

```bash
# 変更をステージング
git add .

# コミット
git commit -m "本番リリース: Clarity Act v3.0 実装完了"

# リモートにプッシュ
git push origin master
```

#### 3. バージョンタグ作成

```bash
# タグ作成
git tag -a v3.0.0-production-ready -m "Production Release v3.0.0"

# リモートにプッシュ
git push origin v3.0.0-production-ready
```

#### 4. デプロイメント実行

```bash
# .env ファイルに本番PC 情報を設定
vi .env

# デプロイスクリプト実行
bash deploy_scripts/deploy_to_production.sh

# ドライラン（実際には変更しない）
bash deploy_scripts/deploy_to_production.sh --dry-run

# バックアップスキップ（高速化）
bash deploy_scripts/deploy_to_production.sh --no-backup
```

#### 5. デプロイメント確認

```bash
# ログ確認
tail -f logs/deploy_*.log

# 本番PC でステータス確認
ssh user@production_host "bash ~/trade/status.sh"
```

### 方法2: Python 同期スクリプト使用

```bash
# 差分検出と同期
python deploy_scripts/sync_to_production.py \
    --project-root . \
    --backup-dir ./backups

# ドライラン
python deploy_scripts/sync_to_production.py \
    --project-root . \
    --dry-run
```

### 方法3: 手動 rsync

```bash
# バックアップ作成
rsync -avz \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='logs/' \
    user@production_host:~/trade/ \
    ./backups/remote_backup_$(date +%Y%m%d_%H%M%S)/

# ファイル同期
rsync -avz \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='logs/' \
    --exclude='__pycache__/' \
    ./ \
    user@production_host:~/trade/
```

---

## ロールバック手順

### 自動ロールバック

```bash
# 前回のバックアップからロールバック
bash deploy_scripts/deploy_to_production.sh \
    --rollback ./backups/remote_backup_20260514_120000/
```

### 手動ロールバック

```bash
# 本番PC で実行
ssh user@production_host

# バックアップからリストア
rsync -avz \
    ~/trade_backup_20260514_120000/ \
    ~/trade/

# サービス再起動
bash ~/trade/stop.sh
bash ~/trade/startup.sh
```

### ロールバック確認

```bash
# サービスが正常に起動しているか確認
bash ~/trade/status.sh

# ログでエラーをチェック
tail -f ~/trade/logs/main_bot.log
```

---

## トラブルシューティング

### 接続エラー

**エラー**: `ssh: Could not resolve hostname`

**対処**:

```bash
# ホスト名を確認
ping production_host

# SSH キーが正しく設定されているか確認
ssh-keygen -l -f ~/.ssh/id_rsa.pub

# SSH 接続テスト
ssh -vvv user@production_host "echo 'test'"
```

### デプロイメント失敗

**エラー**: `rsync: command not found`

**対処**:

```bash
# 本番PC に rsync をインストール
ssh user@production_host "sudo apt-get install -y rsync"

# または、手動でファイルをコピー
scp -r ./ user@production_host:~/trade/
```

### API キーエラー

**エラー**: `HYPERLIQUID_API_KEY not configured`

**対処**:

```bash
# 本番PC で .env を確認
ssh user@production_host "grep HYPERLIQUID ~/.env"

# API キーを設定
ssh user@production_host "vi ~/.env"

# サービスを再起動
ssh user@production_host "bash ~/trade/stop.sh && bash ~/trade/startup.sh"
```

### プロセスが起動しない

**エラー**: `ModuleNotFoundError: No module named 'hyperliquid'`

**対処**:

```bash
# 本番PC で依存関係を再インストール
ssh user@production_host \
    "cd ~/trade && source venv/bin/activate && pip install -r requirements.txt"

# サービスを再起動
ssh user@production_host "bash ~/trade/stop.sh && bash ~/trade/startup.sh"
```

### ディスク容量不足

**エラー**: `No space left on device`

**対処**:

```bash
# ディスク使用量を確認
ssh user@production_host "df -h"

# ログをクリーンアップ
ssh user@production_host "cd ~/trade && find logs -name '*.log' -mtime +30 -delete"

# 古いバックアップを削除
ssh user@production_host "find ~/trade_backup_* -mtime +30 -delete"
```

---

## モニタリング

### ヘルスチェック

```bash
# 本番PC でヘルスチェック実行
ssh user@production_host "bash ~/trade/deploy_scripts/health_check.sh"
```

### ログ確認

```bash
# リアルタイムログ監視
ssh user@production_host "tail -f ~/trade/logs/main_bot.log"

# エラーログを抽出
ssh user@production_host "grep ERROR ~/trade/logs/*.log | tail -20"
```

### cron ジョブ確認

```bash
# 本番PC で cron ジョブを確認
ssh user@production_host "crontab -l | grep trade"

# cron ログを確認
ssh user@production_host "grep CRON /var/log/syslog | tail -20"
```

### パフォーマンス確認

```bash
# リソース使用量を確認
ssh user@production_host "top -b -n 1"

# ディスク使用量を確認
ssh user@production_host "du -sh ~/trade/*"

# メモリ使用量を確認
ssh user@production_host "free -h"
```

---

## 本番運用スケジュール

### 日次チェック

- [ ] ヘルスチェックが PASS
- [ ] エラーログが 10件以下
- [ ] ディスク容量が 80% 未満

### 週次メンテナンス

- [ ] ログの圧縮・アーカイブ
- [ ] 古いバックアップの削除
- [ ] 依存関係のアップデート確認

### 月次レビュー

- [ ] 本番リリースノート作成
- [ ] セキュリティアップデート確認
- [ ] パフォーマンス分析

---

## セキュリティチェックリスト

- [ ] API キーは .env に保存（Git に含まない）
- [ ] SSH キーは安全に保管
- [ ] .env ファイルのパーミッションは 600
- [ ] 本番PC のファイアウォール設定確認
- [ ] SSH ポートは標準ポート以外に変更（推奨）
- [ ] 定期的なバックアップを実施

---

## 参考リンク

- [Hyperliquid API ドキュメント](https://docs.hyperliquid.xyz)
- [GitHub Actions ドキュメント](https://docs.github.com/en/actions)
- [rsync 使用ガイド](https://man7.org/linux/man-pages/man1/rsync.1.html)

---

**最終更新**: 2026-05-14
**バージョン**: Clarity Act v3.0
