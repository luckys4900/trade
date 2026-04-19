# Whale-Following Strategy 実装ガイド

## 概要

期待値が実測可能な**マルチレイヤー・コピートレード戦略**の完全実装。  
既存の RSI×EMA×ATR 戦略（Win Rate 60%, PF 2.09）は維持しながら、Whale コンセンサス信号をサイズ multiplier として統合。

---

## 実装構成

```
【サイドカー プロセス】              【メインボット】
┌─────────────────────┐             ┌───────────────────────┐
│  whale_monitor.py   │──whale──┐   │                       │
│  (15分毎)           │       signal├─▶ qwen_unified_live.py │
│                     │        JSON  │                       │
└─────────────────────┘             │ ・RSI signal生成        │
                                    │ ・whale/macro読み込み  │
┌─────────────────────┐             │ ・size multiplier計算  │
│  macro_filter.py    │──macro─┐   │ ・エントリー実行       │
│  (60分毎)           │       state├─▶                       │
│                     │        JSON  │                       │
└─────────────────────┘             └───────────────────────┘
                                              │
                                     trade_alignment_log.json
                                     (EV validation)
```

---

## ファイル一覧

### 新規作成（6つ）

| ファイル | 役割 | 更新頻度 |
|---------|------|---------|
| `whale_wallets.json` | ウォレット設定 + スコアリング閾値 | 週1回 |
| `economic_calendar.csv` | HIGH impact イベント | 月1回 |
| `whale_monitor.py` | ウォレット監視エンジン | 常時実行（15分毎） |
| `macro_filter.py` | ボラ＆カレンダーフィルター | 常時実行（60分毎） |
| `fetch_leaderboard_wallets.py` | ウォレット設定ツール | 1回だけ実行 |
| `WHALE_SETUP_GUIDE.md` | セットアップマニュアル | - |

### 既存修正

| ファイル | 変更 |
|---------|------|
| `qwen_unified_live.py` | バグ修正 + Config 10フィールド + 4メソッド + 3entry修正 |

---

## 初回セットアップ（5分）

### 1. ウォレットを取得・設定

```bash
python fetch_leaderboard_wallets.py
```

詳細: [WHALE_SETUP_GUIDE.md](WHALE_SETUP_GUIDE.md)

Hyperliquid Leaderboard から TOP 6-10 ウォレットを対話的に設定します。

### 2. 経済カレンダーを確認

`economic_calendar.csv` の HIGH impact イベントが最新か確認。

### 3. 単体テスト

```bash
# Whale Monitor テスト
python whale_monitor.py --once

# Macro Filter テスト
python macro_filter.py --once

# ファイルが生成されたか確認
ls -la whale_signal.json macro_state.json
```

---

## 本運用（常時実行）

### ターミナル 1: Whale Monitor

```bash
python whale_monitor.py
# 15分毎に whale_signal.json を更新
# Sortino > 0.5 のウォレットを自動抽出
# コンセンサス投票で direction/strength を決定
```

ログ: `logs/whale_monitor_*.log`

### ターミナル 2: Macro Filter

```bash
python macro_filter.py
# 60分毎に macro_state.json を更新
# ATR比からボラティリティ regime を判定
# 経済カレンダーから caution_mode を決定
```

ログ: `logs/macro_filter_*.log`

### ターミナル 3: メインボット

```bash
python qwen_unified_live.py
# 60秒毎にシグナルをチェック
# whale_signal.json & macro_state.json を読み込み
# size multiplier を計算してエントリー
# trade_alignment_log.json に記録
```

ログ: `logs/unified_live_*.log`

---

## 期待値の実測化

### 自動測定メカニズム

1. **ウォレットスコア**: 90日間の fills から Sortino 計算（週1回更新）
2. **コンセンサス強度**: `strength = (n_wallets / n_ranked) × (avg_Sortino / cap)`
3. **エントリー記録**: 全エントリーを `trade_alignment_log.json` に記録（whale_aligned: True/False）

### EV 検証（30日後）

```bash
# aligned トレード vs unaligned トレードの EV 比較
python validate_whale_alpha.py

# 出力例
# Group        | Trades | WR   | Avg Win | Avg Loss | EV
# Whale Aligned|   15   | 67%  | +2.1%   | -1.2%    | +0.98%
# No Whale     |   12   | 55%  | +1.8%   | -1.4%    | +0.37%
# Whale Conflict|   5   | 40%  | +1.5%   | -1.6%    | -0.36%
#
# ✓ Whale alignment adds +0.61% EV per trade
```

**判定ゲート**: `aligned_ev - unaligned_ev > 0.3%` なら継続、そうでなければ `whale_enabled = False`

---

## パラメータ解説

### `whale_wallets.json`

```json
{
  "scoring_config": {
    "lookback_days": 90,           // 過去90日のデータで評価
    "min_trades": 10,              // 最低10トレード以上
    "min_sortino": 0.5,            // Sortino > 0.5 でランク入り
    "min_win_rate": 0.45,          // 勝率 > 45% で有効
    "sortino_normalization_cap": 3.0,  // 異常値の cap
    "rescore_interval_hours": 168  // 週1回（168h）再スコア
  },
  "consensus_config": {
    "min_agreeing_wallets": 3,     // 最低3ウォレットの合意で signal
    "min_ranked_wallets": 3,       // ランク入り最低3ウォレット必要
    "signal_ttl_minutes": 30       // Signal の TTL（30分以上は stale）
  }
}
```

### `qwen_unified_live.py` Config

```python
# Size Multiplier
whale_align_multiplier_max: 1.5      # aligned 時の最大倍数
whale_conflict_multiplier: 0.6       # conflict 時の倍数
macro_caution_multiplier: 0.5        # caution_mode 時の倍数

# TTL（Time To Live）
whale_signal_max_age_minutes: 30     # 30分以上古い → None
macro_state_max_age_minutes: 120     # 120分以上古い → None
```

---

## 安全機構

### フォールバック

| 障害 | 動作 |
|------|------|
| whale_monitor.py クラッシュ | 30分TTL切れ → multiplier=1.0 → 既存戦略のまま |
| macro_filter.py クラッシュ | 120分TTL切れ → macro_state=None → フィルター無効 |
| EXTREME regime 検出 | multiplier=0.0 → エントリースキップ |
| JSON パースエラー | multiplier=1.0 → ログ警告のみ |

### 既存戦略の保護

```python
# Win Rate 60%, PF 2.09, Sharpe 5.13 は一切変わらず

# もし whale signal が効果なし（30日後に判明）
whale_enabled: False  # → 無効化可能

# 復帰も簡単
whale_enabled: True   # → 再度有効化
```

---

## トラブルシューティング

### whale_signal.json が生成されない

```bash
# 1. whale_monitor.py が実行中か確認
ps aux | grep whale_monitor

# 2. ウォレットアドレスが有効か確認
python fetch_leaderboard_wallets.py --show

# 3. ウォレットに十分な fills があるか確認
python whale_monitor.py --once  # ログで確認
```

### macro_state.json が生成されない

```bash
# 1. ネットワーク接続を確認
python -c "import requests; print(requests.get('https://api.hyperliquid.xyz/info').status_code)"

# 2. economic_calendar.csv の形式を確認
head economic_calendar.csv

# 3. キャンドルデータ取得を確認
python macro_filter.py --once
```

### メインボットがエントリーしない（whale multiplier が理由の場合）

```bash
# 1. ログで whale_mult=0.0 を確認
grep "EXTREME macro regime" logs/unified_live_*.log

# 2. macro_state.json の regime を確認
cat macro_state.json | grep regime

# 3. 必要に応じて caution_window を短縮
# economic_calendar.csv の HIGH impact イベントを削除
```

---

## 日次チェックリスト

- [ ] 両サイドカー（whale_monitor, macro_filter）が実行中か確認
- [ ] `whale_signal.json` の timestamp が 30分以内か確認
- [ ] `macro_state.json` の timestamp が 120分以内か確認
- [ ] メインボットのログに whale_mult が記録されているか確認
- [ ] `trade_alignment_log.json` が増えているか確認

---

## 週次チェックリスト

- [ ] `trade_alignment_log.json` で 10+ トレード記録されているか確認
- [ ] `whale_ranking_cache.json` が再スコア対象か確認（168h毎）
- [ ] `economic_calendar.csv` を翌週分まで更新
- [ ] ウォレット Sortino < 0.5 で自動除外されているか確認

---

## 月次チェックリスト

- [ ] `economic_calendar.csv` を翌月分に更新
- [ ] Leaderboard をチェックし、ウォレット群の入れ替えを検討
- [ ] `validate_whale_alpha.py` を実行、EV 検証を実施
- [ ] aligned_ev vs unaligned_ev の比較結果を記録

---

## ログ場所

```
logs/
  ├── whale_monitor_20260410_*.log    # ウォレット監視ログ
  ├── macro_filter_20260410_*.log     # マクロフィルターログ
  ├── unified_live_20260410_*.log     # メインボットログ
  └── fetch_leaderboard_*.log         # ウォレット設定ログ
```

---

## 参考資料

- [Whale Setup ガイド](WHALE_SETUP_GUIDE.md)
- [実装計画](../plans/cosmic-weaving-karp.md)
- Hyperliquid API: https://api-docs.hyperliquid.xyz/
- Hyperliquid Leaderboard: https://app.hyperliquid.xyz/leaderboard

---

## 重要な注意事項

⚠️ **本運用前に 7 日間のパイロット運用を推奨**

- 小ロット（1-2% risk）で動作確認
- whale_signal の品質を実データで検証
- `trade_alignment_log.json` で EV 向上を確認

✓ 検証後、本運用スケール（1-2% → 2-3% risk）に移行

---

## サポート

問題が発生した場合：

1. ログファイルを確認 (`logs/*.log`)
2. [トラブルシューティング](#トラブルシューティング)を参照
3. 必要に応じて `whale_enabled: False` で無効化

---

**作成日**: 2026-04-10  
**最終更新**: 2026-04-10  
**バージョン**: 1.0
