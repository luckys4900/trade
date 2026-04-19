# 日本株（JPX）バックテスト・ツールキット

このツールキットは、J-Quants APIを利用して日本株のデータを取得し、RSIモメンタム戦略のバックテストを行うためのものです。

## セットアップ

1. **J-Quants APIへの登録**
   - [J-Quants公式サイト](https://j-quants.com/jp/)から無料プランに登録してください。
   - `.env` ファイルに、登録したメールアドレスとパスワードを設定してください。
     ```
     JQUANTS_MAIL_ADDRESS=your_email@example.com
     JQUANTS_PASSWORD=your_password
     ```

2. **必要ライブラリのインストール**
   ```bash
   pip install jquants-api-client backtesting
   ```

## 使い方

### バックテストの実行

デフォルト設定（トヨタ 7203, 2023-2024）で実行する場合：
```bash
python run_jpx_backtest.py
```

特定の銘柄や期間を指定する場合：
```bash
python run_jpx_backtest.py --code 9101 --start 2024-01-01 --end 2024-12-31
```
※ `9101` は日本郵船の例です。

### 構成ファイル

- `jquants_data_loader.py`: J-Quants APIからデータを取得。認証情報がない場合は合成データを生成。
- `jpx_strategy.py`: 東証の取引時間を考慮したRSI戦略ロジック。
- `run_jpx_backtest.py`: 全体を統合する実行スクリプト。

## 戦略の詳細

`jpx_strategy.py` に実装されている `JPXRSISwing` 戦略は以下の特徴を持ちます：
- **トレンドフィルタ**: Close > EMA(50) のときのみロング。
- **逆張りエントリー**: RSI(14) が 30 以下から上抜けたときにエントリー。
- **資金管理**: 1トレードあたりのリスクを資金の1%に限定。100株単位での発注をシミュレート。
- **ボラティリティ対応**: ATR(14) をベースとした損切り（1.5倍）と利確（3.0倍）を設定。
