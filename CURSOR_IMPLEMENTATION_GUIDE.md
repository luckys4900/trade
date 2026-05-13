# Cursor IDE実装ガイド
## Clarity Act Pair Trading Strategy v3.0

**目的**: このガイドに従い、Cursor IDEで段階的にシステムを実装できます。

---

## 📋 前提条件

- Python 3.8以上がインストールされている
- Cursor IDE が起動可能
- 作業ディレクトリ: `/Users/user/Desktop/trade/data`

---

## 🚀 実装フロー（4-5日）

### Day 1: 環境準備 (2-3時間)

```bash
# 1. ライブラリインストール
pip install -r ../requirements.txt

# 2. Congress.gov API Key取得（不要、公開API）
# ウェブサイト: https://api.congress.gov/

# 3. config.yaml生成
python clarity_act_core.py  # Initializes default config
```

**Cursor実装項目:**
- [ ] `requirements.txt` インストール確認
- [ ] `clarity_act_core.py` 基本動作テスト
- [ ] `config.yaml` 生成確認

---

### Day 2-3: コア実装 (6-8時間)

#### 実装順序:

**1. DynamicTimelineManager (1-2時間)**
```python
# ファイル: clarity_act_core.py
# 実装内容:
# - daily_check(): Congress.gov API呼び出し
# - calculate_optimal_params(): Duration計算
# - get_entry_trigger_status(): 投票日確定判定

# テスト:
python -c "from clarity_act_core import DynamicTimelineManager; 
dtm = DynamicTimelineManager(); 
print(dtm.daily_check())"
```

**2. RatioCalculator (1-2時間)**
```python
# ファイル: clarity_act_core.py
# 実装内容:
# - calculate_ratio(): BTC/ETH比率計算
# - calculate_ma(): 移動平均計算
# - detect_uptrend(): 上昇トレンド検出

# テスト:
python -c "from clarity_act_core import RatioCalculator;
rc = RatioCalculator();
rc.add_price_data(65000, 3500);
print(rc.calculate_ma())"
```

**3. SignalGenerator (1-2時間)**
```python
# ファイル: clarity_act_core.py
# 実装内容:
# - entry_signal(): エントリシグナル生成
# - exit_signal(): イグジットシグナル生成

# テスト:
python -c "from clarity_act_core import SignalGenerator;
sg = SignalGenerator();
print(sg.entry_signal(65000, 3500, 18.5))"
```

**4. ConfigurationManager (1-2時間)**
```python
# ファイル: clarity_act_core.py
# 実装内容:
# - load_config(): YAML読み込み
# - update_params(): パラメータ更新
# - save_config(): YAML保存

# テスト:
python -c "from clarity_act_core import ConfigurationManager;
cm = ConfigurationManager();
cm.update_params({'ma_window': 14})"
```

**5. 統合テスト (1-2時間)**
```bash
python daily_workflow.py --test
```

---

### Day 4: 統合と委員会投票監視 (4-5時間)

**1. VoteResultAnalyzer統合 (1-2時間)**
```python
# ファイル: committee_vote_monitor.py
# 実装内容:
# - CongressGovMonitor: Congress.gov監視
# - PolymarketMonitor: Polymarket監視
# - VoteResultAnalyzer: 投票結果判定

# テスト:
python committee_vote_monitor.py
```

**2. Daily Workflow統合 (1-2時間)**
```python
# ファイル: daily_workflow.py
# 実装内容:
# - DailyWorkflow: 日次自動実行
# - WorkflowCoordinator: オーケストレーション

# テスト:
python daily_workflow.py
```

**3. リアルタイム監視ダッシュボード (1-2時間)**
```bash
# Optional: Web-based dashboard for monitoring
# Tool: Streamlit, Flask, or simple JSON log viewer
```

---

### Day 5: 最終検証と本番準備 (2-3時間)

```bash
# 1. ユニットテスト実行
pytest tests/test_clarity_act.py -v

# 2. エンドツーエンドテスト
python daily_workflow.py --e2e-test

# 3. ログ確認
tail -f clarity_act_workflow.log

# 4. 設定確認
cat config.yaml
```

---

## 📚 主要ファイル説明

| ファイル | 役割 | 優先度 |
|---------|------|--------|
| `clarity_act_core.py` | コアロジック実装 | 🔴 Critical |
| `committee_vote_monitor.py` | 投票監視 | 🟡 High |
| `daily_workflow.py` | 日次自動実行 | 🟡 High |
| `config.yaml` | 設定管理 | 🟢 Medium |
| `trade_log.json` | トレード記録 | 🟢 Medium |

---

## ⚙️ 設定項目 (config.yaml)

```yaml
strategy: clarity_act_pair_trading
version: 3.0

parameters:
  ma_window: 10              # 移動平均ウィンドウ
  stop_loss_percent: -2.5    # ストップロス
  position_fraction: 0.50    # ポジションサイズ分率
  kelly_fraction: 0.55       # Kelly Criterion

monitoring:
  congress_check_frequency: daily      # 1回/日
  polymarket_check_frequency: hourly   # 1回/時間
```

---

## 🔍 デバッグ・トラブルシューティング

### Issue: Congress.gov API接続エラー

```python
# 対策: API URLを確認
# https://api.congress.gov/v3/bill/119/hr/3633

import requests
response = requests.get("https://api.congress.gov/v3/bill/119/hr/3633?format=json")
print(response.status_code)
```

### Issue: Polymarket オッズ取得失敗

```python
# 対策: Polymarket API が使用不可の場合、webスクレイピングに切り替え
# from bs4 import BeautifulSoup
# response = requests.get("https://polymarket.com/")
```

### Issue: パラメータが自動更新されない

```python
# チェックリスト:
# 1. daily_check() が実行されているか確認
# 2. Congress.govから投票日が返されているか確認
# 3. calculate_optimal_params() が正しくDurationを計算しているか確認
# 4. config.yaml が書き込み可能か確認
```

---

## ✅ 実装チェックリスト

- [ ] Day 1: 環境準備完了
- [ ] DynamicTimelineManager 実装完了
- [ ] RatioCalculator 実装完了
- [ ] SignalGenerator 実装完了
- [ ] ConfigurationManager 実装完了
- [ ] CommitteeVoteMonitor 実装完了
- [ ] DailyWorkflow 実装完了
- [ ] ユニットテスト 全パス
- [ ] エンドツーエンドテスト パス
- [ ] 本番環境チェック 完了

---

## 🎯 次のステップ

実装完了後:

1. **ライブトレード開始**: 5月14日委員会投票結果待機
2. **パラメータ監視**: 上院本会議投票日が確定したら自動調整
3. **事後分析**: 7月4日署名後、バックテスト vs 実績を比較

---

**質問・フィードバック**: Cursor内のスムーズな実装のため、不明な点はここに記載してください。

**実装開始**: 2026-05-14 (Now!)
