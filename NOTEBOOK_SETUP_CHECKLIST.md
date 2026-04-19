# Notebook Setup Checklist

## 1. ソフト導入

- `Cursor` をインストール
- `Python 3.10.x` をインストール
- `python --version` が通ることを確認
- `pip --version` が通ることを確認

## 2. プロジェクト配置

- `trade` フォルダをノートPCへコピー
- `.env` を安全に配置
- 必要なら `trade_state_unified.json` と `logs/` を移す

## 3. Cursor 起動

- ノートPCで `Cursor` を開く
- `trade` フォルダを開く
- 新しいチャットを開始
- `CURSOR_NOTEBOOK_HANDOFF_PROMPT.md` の内容を貼り付ける

## 4. Python 依存導入

まずは次を実行:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install python-dotenv eth-account torch pytest
```

`TA-Lib` で詰まる場合は、その場で Cursor エージェントに解決させること。

## 5. 動作確認

最低限、以下を確認:

```powershell
python -m pytest test_contrarian_integration.py
python -m py_compile SYSTEM\qwen_unified_live.py SYSTEM\kronos_predictor.py SYSTEM\dashboard.py
```

## 6. 起動確認

運用起動前に確認:

- `.env` が正しい
- `trade_state_unified.json` が壊れていない
- 重複 `pythonw.exe` がない

起動候補:

- `Qwen_本番自動売買_起動.bat`
- `MASTER_LAUNCHER.bat`

## 7. 電源設定

- スリープ: `なし`
- 休止状態: `なし`
- 画面を閉じてもスリープしない
- 電源接続で運用
- Windows Update の自動再起動に注意

## 8. 運用確認

- `Qwen_Status_Check.bat` で状態確認
- `logs/unified_live_*.log` を確認
- `logs/kronos_predictor_live.log` を確認
- `trade_state_unified.json` を確認
- `logs/account_state.json` を確認

## 9. 最初のゴール

ノートPC側で次が確認できれば移行成功:

- Python 環境OK
- 依存導入OK
- テストOK
- 起動OK
- 4系統が動作
- スリープ対策OK
