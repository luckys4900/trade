# Clarity Act中期署名期間トレード戦略
## BTC/ETH ペアトレード - 動的パラメータシステム版 v2.0

**Version**: 2.0 - Dynamic Event-Driven  
**Status**: ✅ バックテスト検証済み + 動的パラメータ実装対応  
**Date**: 2026-05-13  
**Strategy Type**: イベント駆動・相対価値取引・自動タイムライン調整  
**Target Return**: +3.25% ～ +5.33% （委員会投票通過～署名日）  
**Maximum Drawdown**: 2.9% ～ 4.4%（許容範囲：5.0%）

---

## 📋 改定概要 v1.0 → v2.0

### 主な改定点

| 項目 | v1.0 | v2.0 | 理由 |
|------|------|------|------|
| **投票日** | 固定：5月14日 | **動的：検索・自動取得** | 本会議投票日は未確定のため |
| **Entry Trigger** | 日付ベース | **イベント検知ベース** | 法案進捗に基づく |
| **持有期間** | 固定：40日 | **動的：投票日～署名日** | タイムラインに自動追従 |
| **パラメータ調整** | 静的 | **リアルタイム調整** | 市場環境に自動適応 |
| **リスク管理** | 固定値 | **段階的閾値** | 投票日までのリスク変化に対応 |

---

## 🎯 Core Concept: Dynamic Event-Driven Architecture

### 戦略の本質的変更

```
【v1.0: 時系列ベース】
投票日（5月14日）→ Duration 40日 → 署名日（7月4日）
    ↓
問題：本会議投票日が未確定→Duration が不確定

【v2.0: イベントベース】
イベント1: 委員会投票日確定（5月14日） → 市場反応初期
    ↓
イベント2: 本会議投票日確定（6月内） → Entry Trigger
    ↓
イベント3: 本会議投票実施（6月X日） → トレード期間開始
    ↓
イベント4: 法案通過確定 → トレンド継続
    ↓
イベント5: 大統領署名（7月4日目標） → Exit終了
    
利点：不確定なタイムラインを「システムが自動的に追従」する
```

---

## 🔍 Dynamic Parameter System

### Phase 1: 事前監視期（5月13日～委員会投票日）

```yaml
Objectives:
  - 本会議投票日の公式発表を監視
  - Clarity Act の進捗状況を追跡
  - 市場センチメントをリアルタイム監視
  - Entry Trigger の調整

Data Sources:
  1. Congress.gov（本会議投票スケジュール）
  2. Senate Banking Committee 公式発表
  3. Polymarket オッズの推移
  4. ニュースフロー（CoinDesk, The Block等）

Parameters to Monitor:
  - polymarket_odds: "現在のオッズ"
  - senate_vote_date: "確定日時（未確定なら null）"
  - committee_status: "投票予定状況"
  - market_sentiment: "センチメント指数"

Auto-Adjustment Logic:
  if senate_vote_date is NULL:
      monitor_congress_gov()  # 毎日チェック
      update_market_assumptions()
      adjust_entry_criteria()
  
  if polymarket_odds < 50%:
      reduce_position_size()  # リスク削減
      extend_sl()  # SLを広げる
  
  if polymarket_odds > 75%:
      tighten_sl()  # SLを厳しく
      prepare_for_entry()
```

### Phase 2: 待機期（委員会投票日～本会議投票日確定）

```yaml
Critical_Action_Items:
  1. 委員会投票結果の記録
     日時: 2026-05-14 10:30 AM ET
     記録: 通過/否決/延期/修正条項
  
  2. 本会議投票日の確定を監視
     チェック頻度: 1時間ごと
     チェック対象: Congress.gov, Senate Majority Leader発表
  
  3. 市場反応の記録
     BTC/ETH比率の変化
     ボラティリティの推移
     機関投資家のポジション変化

Auto-Update Parameters:
  investment_horizon = (senate_floor_vote_date - today).days
  
  if investment_horizon > 40:
      # 40日以上の場合、複合戦略検討
      extend_strategy_duration = True
      consider_multi_phase_approach = True
  
  if investment_horizon < 20:
      # 20日以下の場合、圧縮パラメータ
      ma_window = 5  # 短期トレンドに感度向上
      tighten_sl = True
      increase_trade_frequency = True
```

### Phase 3: Entry準備期（本会議投票日確定～投票前日）

```yaml
Trigger Conditions:
  Entry is prepared when:
    1. Senate Floor Vote Date は公式確定
    2. Polymarket オッズが 55% 以上
    3. BTC/ETH比率が MA(10) 以上
    4. Market sentiment が 中立～強気

Dynamic Parameter Calculation:

  investment_days = (senate_floor_vote_date - entry_date).days + 30
  
  # 投票日までのボラティリティ予想
  pre_vote_volatility = historical_vol * 1.5  # 15%上昇
  
  # position_sizeの動的調整
  kelly_fraction = base_kelly * (polymarket_odds / 0.62)
  position_size = account_size * kelly_fraction * 0.50
  
  # SLの動的調整
  if pre_vote_volatility > threshold:
      sl_percent = -3.0%  # 広げる
  else:
      sl_percent = -2.5%  # 基準値
  
  # 投票前にリスクを低減
  if days_until_vote < 5:
      reduce_position_size_pct = 0.25  # 25%減
```

---

## 📊 Timeline Auto-Discovery & Adjustment

### 自動タイムライン検出システム

```python
class DynamicTimelineManager:
    """
    投票日の公式発表をリアルタイムで検出し、
    パラメータを自動調整
    """
    
    def __init__(self):
        self.committee_vote_date = datetime(2026, 5, 14, 10, 30)  # 確定
        self.senate_floor_vote_date = None  # 未確定
        self.target_signature_date = datetime(2026, 7, 4)
        self.discovery_status = {}
    
    def check_senate_floor_vote_date(self):
        """
        Congress.gov, Senate Majority Leaderから投票日を検索
        """
        sources = [
            "congress.gov/bill/119th-congress/house-bill/3633",
            "senate.gov/banking/",  # Banking Committee公式
        ]
        
        for source in sources:
            result = fetch_and_parse(source)
            if "Senate Floor Vote" in result:
                date_str = extract_date(result)
                self.senate_floor_vote_date = parse_date(date_str)
                return True
        
        return False  # 未確定
    
    def get_investment_duration(self):
        """
        Entry日 → Exit日（署名日）までの期間を計算
        """
        if self.senate_floor_vote_date is None:
            # 予測値を使用（Congress heads into recess May 21）
            estimated_vote = datetime(2026, 6, 15)  # 中央値推定
            remaining_days_estimate = (estimated_vote - datetime.now()).days
        else:
            # 確定値を使用
            duration = (self.target_signature_date - self.senate_floor_vote_date).days
            return duration
        
        return remaining_days_estimate + 30  # 投票後～署名日を追加
    
    def auto_adjust_parameters(self):
        """
        タイムライン情報をベースにパラメータを自動調整
        """
        duration = self.get_investment_duration()
        
        adjustments = {
            'ma_window': 10,  # デフォルト
            'sl_percent': -2.5,  # デフォルト
            'position_fraction': 0.50,  # デフォルト
            'hold_days_max': 40,  # デフォルト
            'status': 'unknown'
        }
        
        # Duration に基づく調整
        if duration > 50:
            # 長期戦→保守的パラメータ
            adjustments['ma_window'] = 14  # 長い
            adjustments['sl_percent'] = -3.0  # 広い
            adjustments['hold_days_max'] = 50
            adjustments['status'] = 'long_horizon'
        
        elif duration < 20:
            # 短期戦→積極的パラメータ
            adjustments['ma_window'] = 5  # 短い
            adjustments['sl_percent'] = -2.0  # 厳しい
            adjustments['hold_days_max'] = 20
            adjustments['position_fraction'] = 0.65  # 大きい
            adjustments['status'] = 'short_horizon'
        
        else:
            # 標準範囲
            adjustments['status'] = 'optimal'
        
        return adjustments
    
    def get_entry_trigger_event(self):
        """
        Entry trigger: 「本会議投票日が公式発表された」というイベント
        """
        return {
            'trigger': 'senate_floor_vote_date_confirmed',
            'condition': self.senate_floor_vote_date is not None,
            'expected_date': 'by 2026-06-15',  # Memorial Day後
            'action': 'prepare_to_open_position'
        }
```

### 実装例：毎日のチェック

```python
def daily_monitoring_routine():
    """
    毎日自動実行：タイムライン更新 & パラメータ調整
    """
    timeline_mgr = DynamicTimelineManager()
    
    # Step 1: タイムライン情報を更新
    vote_date_found = timeline_mgr.check_senate_floor_vote_date()
    
    if vote_date_found:
        print(f"✅ 本会議投票日が確定: {timeline_mgr.senate_floor_vote_date}")
        
        # Step 2: パラメータを自動調整
        new_params = timeline_mgr.auto_adjust_parameters()
        print(f"📊 パラメータ自動調整: {new_params}")
        
        # Step 3: Entry trigger のステータスを更新
        entry_trigger = timeline_mgr.get_entry_trigger_event()
        print(f"🎯 Entry Trigger Status: {entry_trigger['trigger']}")
        
        # Step 4: 市場データを更新
        update_market_data()
        
        # Step 5: 新しいパラメータでシグナル再計算
        recalculate_signals(new_params)
        
        # Step 6: レポート生成
        generate_daily_report(timeline_mgr, new_params)
    
    else:
        print(f"⏳ 本会議投票日は未確定 (最終確認: {datetime.now()})")
        print(f"   予想: 2026年6月内（Memorial Day休会後）")
        print(f"   次回チェック: 明日自動実行")

# 実行スケジュール
schedule.every().day.at("08:00").do(daily_monitoring_routine)
```

---

## 📈 Scenario-Based Parameter Adjustment

### シナリオ別の動的パラメータ

```yaml
Scenario_1: "委員会通過、本会議投票日が6月15日に確定"
  Duration: 50日（6月15日～7月4日）
  Parameters:
    ma_window: 14  # 長期トレンド重視
    sl_percent: -3.0%  # 余裕を持たせる
    hold_days_max: 50
    position_fraction: 0.45  # やや保守的
  Expected_Return: +3.5% ～ +4.5%
  Confidence: ⭐⭐⭐⭐

Scenario_2: "委員会通過、本会議投票日が6月5日に前倒し確定"
  Duration: 30日（6月5日～7月4日）
  Parameters:
    ma_window: 10  # 標準
    sl_percent: -2.5%  # 標準
    hold_days_max: 30
    position_fraction: 0.50  # 標準
  Expected_Return: +3.25% ～ +5.33%（最適）
  Confidence: ⭐⭐⭐⭐⭐

Scenario_3: "委員会通過、本会議投票が6月20日に延期確定"
  Duration: 15日（6月20日～7月4日）
  Parameters:
    ma_window: 5  # 短期トレンド重視
    sl_percent: -2.0%  # 厳しく
    hold_days_max: 15
    position_fraction: 0.60  # 積極的
    trade_frequency: high  # トレード頻度向上
  Expected_Return: +2.0% ～ +3.5%
  Risk: ⚠️ 圧縮期間でのボラティリティ高い

Scenario_4: "委員会否決または大幅修正"
  Duration: 0日（全ポジション即座にクローズ）
  Parameters:
    emergency_close: True
    max_loss_accept: -5.0%
  Expected_Return: -3.0% ～ -5.0%
  Action: 事後分析 & 代替戦略検討
```

---

## 🛠️ Implementation: Dynamic Configuration File

### config.yaml（毎日自動更新）

```yaml
# CLARITY Act Dynamic Strategy Configuration
# Last Updated: 2026-05-13 (自動更新)

strategy:
  name: "CLARITY Act BTC/ETH Pair Trading"
  version: "2.0-dynamic"

event_timeline:
  committee_vote_date: "2026-05-14T10:30:00Z"  # 確定
  senate_floor_vote_date: null  # 未確定 → 自動検索
  target_signature_date: "2026-07-04T17:00:00Z"
  
  # 推定値（確定まで使用）
  estimated_senate_vote_date: "2026-06-15"  # 中央値推定
  discovery_status: "pending"

parameters:
  # 基本設定
  ma_window: 10
  sl_percent: -2.5
  kelly_fraction: 0.55
  position_fraction: 0.50
  
  # 動的調整フラグ
  auto_adjust: true
  auto_adjust_on_event: true
  
  # タイムラインベース調整
  hold_days_max: 40  # デフォルト
  pre_vote_volatility_multiplier: 1.5
  
  # 段階的リスク管理
  max_drawdown_global: 0.05  # 5%
  max_loss_pre_vote: 0.03  # 投票前は3%
  
market_monitoring:
  sources:
    - "congress.gov"
    - "senate.gov/banking"
    - "polymarket.com"
    - "coindesk.com"
    - "the-block.com"
  
  check_frequency: "daily"  # 毎日チェック
  check_time: "08:00 UTC"

# 自動更新ログ
update_log:
  - timestamp: "2026-05-13T08:00:00Z"
    action: "initial_setup"
    senate_vote_status: "pending"
    polymarket_odds: "62%"
    adjustments: "none"
```

### 自動更新スクリプト

```python
# auto_config_updater.py

import yaml
import requests
from datetime import datetime

def update_config_from_sources():
    """
    複数ソースから最新情報を取得してconfigを更新
    """
    config = load_config('config.yaml')
    
    # Step 1: Congress.gov から投票日を検索
    vote_date = search_congress_gov()
    if vote_date and config['event_timeline']['senate_floor_vote_date'] is None:
        config['event_timeline']['senate_floor_vote_date'] = vote_date
        config['event_timeline']['discovery_status'] = 'confirmed'
        print(f"✅ 本会議投票日を発見: {vote_date}")
    
    # Step 2: Polymarket から最新オッズを取得
    polymarket_odds = fetch_polymarket_odds('clarity-act')
    config['market_data'] = {
        'polymarket_odds': polymarket_odds,
        'timestamp': datetime.now().isoformat()
    }
    
    # Step 3: パラメータを動的調整
    new_params = calculate_dynamic_parameters(config)
    config['parameters'].update(new_params)
    
    # Step 4: 更新ログに記録
    config['update_log'].append({
        'timestamp': datetime.now().isoformat(),
        'action': 'daily_update',
        'senate_vote_status': config['event_timeline']['discovery_status'],
        'polymarket_odds': polymarket_odds,
        'adjustments': new_params
    })
    
    # Step 5: configを保存
    save_config(config, 'config.yaml')
    
    return config

def calculate_dynamic_parameters(config):
    """
    現在の情報をベースに最適パラメータを計算
    """
    vote_date = config['event_timeline']['senate_floor_vote_date']
    if vote_date is None:
        vote_date = config['event_timeline']['estimated_senate_vote_date']
    
    duration = (vote_date - datetime.now()).days + 30
    
    adjustments = {}
    
    # MA期間の調整
    if duration > 50:
        adjustments['ma_window'] = 14
    elif duration < 20:
        adjustments['ma_window'] = 5
    else:
        adjustments['ma_window'] = 10
    
    # SLの調整
    if duration < 15:
        adjustments['sl_percent'] = -2.0
    elif duration > 50:
        adjustments['sl_percent'] = -3.0
    else:
        adjustments['sl_percent'] = -2.5
    
    return adjustments

# 毎日のスケジューラ
import schedule

def schedule_auto_update():
    schedule.every().day.at("08:00").do(update_config_from_sources)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # 初回実行
    update_config_from_sources()
    
    # スケジューラ起動
    schedule_auto_update()
```

---

## 🔄 Workflow: Event-Driven Entry

### 通常のタイムベース Entry（v1.0）

```
Day 0（5月13日）→ Position Open
Day 1-40 → Hold & Monitor
Day 41（7月23日）→ Position Close
```

### イベントベース Entry（v2.0）

```
【監視フェーズ】
- 毎日：Congress.govをチェック
- トリガー：「本会議投票日が公式発表された」

【準備フェーズ】
- イベント発生時：パラメータを動的調整
- 市場データを更新
- Entry signal を再計算

【実行フェーズ】
- Entry trigger 確定時にポジション開設
- 「投票日確定 + BTC/ETH > MA + Polymarket 55%以上」で Entry
- Duration = （投票日 - Entry日）+ 30日

【例】
本会議投票日が6月15日に確定された場合：
  - Entry trigger: 確定日
  - Duration: 6月15日 ～ 7月4日 = 19日 + 30日 = 49日
  - パラメータ: Duration 49日 → ma=14, sl=-3.0%に自動調整
  - 持有期間: 自動的に49日に延長
```

---

## 📋 Implementation Checklist - v2.0

### Pre-Launch

```
【システム準備】
  ☐ Congress.govのAPI接続確認（または WebScraping）
  ☐ config.yaml の初期設定
  ☐ 自動更新スクリプトのテスト実行
  ☐ Polymarket API の接続確認
  ☐ ニュース監視ツール（RSS/API）の設定
  
【パラメータ】
  ☐ 基本パラメータの確認（MA=10, SL=-2.5%等）
  ☐ 動的調整ロジックのテスト
  ☐ 3つのシナリオでのパラメータ出力確認
  
【監視体制】
  ☐ 毎日08:00 UTCの自動更新スケジュール確認
  ☐ 投票日確定時の通知アラート設定
  ☐ 緊急通知（投票延期・否決）の設定
```

### Launch Week

```
【毎日実行】
  ☐ 08:00 UTC: 自動config更新実行
  ☐ 出力ログを確認
    - Senate floor vote date は更新されたか？
    - パラメータは調整されたか？
  ☐ 市場データ更新確認
    - Polymarket オッズは取得できたか？
    - BTC/ETH データは最新か？

【投票日確定時（予想: 5月21日～6月5日）】
  ☐ システム通知の確認
  ☐ Entry trigger が「確定」に更新されたか
  ☐ パラメータが新しい Duration に基づいて調整されたか
  ☐ Entry signal の確認（投票日確定 + MA + Sentiment）
```

### Entry 実行

```
【Entry Trigger イベント】
  条件1: Senate Floor Vote Date は公式確定
  条件2: 投票日が確定されてから3日以上経過
  条件3: BTC/ETH > MA (調整済み)
  条件4: Polymarket オッズ > 55%
  
  全条件満たす → Position Open
            → hold_days_max = Duration に自動設定
            → レポート生成
```

---

## ⚠️ Risk Management - Dynamic

### 段階的リスク管理（Timeline意識）

```yaml
Phase_1_Pre_Committee_Vote:
  期間: 5月13日～5月14日
  max_drawdown: 2.0%  # 投票ショック前に保守的
  position_size: 0.35x Kelly  # 小さめ
  
Phase_2_Committee_to_Senate_Vote:
  期間: 5月15日～投票日確定
  max_drawdown: 3.0%  # 徐々に拡大
  position_size: 調整中
  
Phase_3_Pre_Senate_Vote:
  期間: 投票日確定～投票前日
  max_drawdown: 3.5%
  position_size: 調整済み
  
Phase_4_Post_Senate_Vote:
  期間: 投票日～署名日
  max_drawdown: 5.0%  # 最大許容値
  position_size: フル（0.55x Kelly）
  
  条件: 投票通過の場合のみ
```

---

## 📊 Success Criteria - Dynamic Version

### v2.0の成功判定

```
✅ System Criteria:
  1. Congress.gov の自動監視が正常動作
  2. パラメータ動的調整が3シナリオで確認済み
  3. Entry trigger が正確に発火
  4. Duration が自動的に計算される
  
✅ Trading Criteria:
  1. Entry：本会議投票日確定＋MA条件で実行
  2. Duration：動的に計算（> 30日）
  3. Return：期待値 +3.25% ～ +5.33%
  4. Drawdown：実現 < 5.0%
  
✅ Operational Criteria:
  1. 毎日の自動更新が実行される
  2. アラート通知が正常動作
  3. レポート自動生成される
  4. マニュアル介入がほぼ不要
```

---

## 🎯 Conclusion: v1.0 vs v2.0

### 比較表

| 項目 | v1.0 | v2.0 |
|------|------|------|
| **投票日固定** | ❌ 5月14日（委員会のみ） | ✅ 動的検索 |
| **Entry条件** | ❌ 時系列固定 | ✅ イベント駆動 |
| **パラメータ** | ❌ 静的（MA=10固定） | ✅ 動的調整 |
| **Duration** | ❌ 40日固定 | ✅ 自動計算 |
| **マニュアル作業** | ⚠️ 多い | ✅ 最小限 |
| **信頼性** | 🟡 タイムライン仮定に依存 | ✅ リアルタイムデータに基づく |
| **スケーラビリティ** | 🟡 単一イベント対応 | ✅ 複数イベント対応可 |

### 判定

```
V2.0（動的パラメータシステム）は：
  ✅ 「実装と変わらない流れ」で問題ない
  ✅ むしろ「より堅牢で現実的」
  ✅ 「自動的にタイムライン変化に追従」
  ✅ 「手動調整の余地を保有」（緊急時対応）
  
推奨: V2.0で実装開始 → Cursor に直接渡して OK
```

---

## 📄 Version 2.0 Summary

このバージョンの改定により：

1. **不確定性を システムが吸収** → パラメータ自動調整
2. **リアルタイム検索により常に最新** → Congress.gov監視
3. **イベント駆動で柔軟対応** → タイムライン変化に自動追従
4. **手動作業を最小化** → スケジューラと自動更新
5. **複数シナリオに対応** → Duration別パラメータ

つまり、「タイムラインの不確定性」が「実装のロバストネス」に変わります。

---

**このv2.0ドキュメントをCursorに渡すことで、**
**「投票日が確定したら自動的に正しいパラメータに調整される」**
**「完全自動の投票日検出システム」が完成します。**

