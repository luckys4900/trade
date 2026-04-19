# Qwen Unified Auto-Trader - Agent Instructions

## Project Overview
Hyperliquid mainnet BTC auto-trader with 3 strategies: OCPM (trend pullback), Range MR (mean reversion), RSI Swing v6.

## Critical Rules
- **MAINNET CONNECTION** — real money is at risk. Always verify syntax before running.
- **Never commit `.env`** — contains `HL_PRIVATE_KEY` and `HL_WALLET_ADDRESS`.
- **Batch files**: use English names only (Japanese names cause encoding errors). Use `Qwen_Status_Check.bat`, not Japanese variants.
- **VBS scripts**: always use full Python path: `C:\Users\user\AppData\Local\Programs\Python\Python310\pythonw.exe`
- **Prevent duplicate launches**: startup batch must check for existing `pythonw.exe` before launching.

## Workflow
1. Read `PROJECT_STATUS.md` first — contains current state, params, and change history.
2. Make changes as requested.
3. Update `PROJECT_STATUS.md` after every change (status + changelog).

## Key Files
| File | Purpose |
|------|---------|
| `qwen_unified_live.py` | Main trading bot (reads `.env` for API keys) |
| `config.json` | Trading params (RSI, SL/TP, leverage, equity) |
| `.env` | API credentials (HL_WALLET_ADDRESS, HL_PRIVATE_KEY) |
| `trade_state_unified.json` | Live position state (updated by bot) |
| `logs/unified_live_*.log` | Latest bot logs |
| `Qwen_本番自動売買_起動.bat` | Launch script (with duplicate prevention) |
| `Qwen_Status_Check.bat` | Status check (process + log + state) |

## Startup / Shutdown
- **Start**: Double-click `Qwen_本番自動売買_起動.bat` (auto-starts via VBS in background)
- **Stop**: `taskkill /F /IM pythonw.exe` + `taskkill /F /IM wscript.exe`
- **Auto-start**: `Qwen_AutoTrader.lnk` in Windows Startup folder
- **Status check**: `Qwen_Status_Check.bat`

## Status Check Commands
```powershell
Get-Process | Where-Object { $_.ProcessName -like "*pythonw*" }
Get-Content logs\unified_live_*.log -Tail 30
Get-Content trade_state_unified.json
```

## Strategy Params (from config.json)
- Symbol: BTC, Timeframe: 4h, Leverage: 1
- RSI(14): OS=30, OB=70
- SL: 1.5x ATR, TP: 3.0x ATR
- Equity: $211.19, Risk: 2%, Check interval: 60s

## Windows Batch File Rules (CRITICAL)
This project runs on **Windows only**. All batch files (`.bat`) MUST follow Windows CMD syntax:

| 禁止（Linux構文） | 正しい（Windows構文） | 用途 |
|---|---|---|
| `>/dev/null` | `>nul` | 標準出力抑制 |
| `2>/dev/null` | `2>nul` | エラー出力抑制 |
| `>/dev/null 2>&1` | `>nul 2>&1` | 両方抑制 |
| `python3` | `python` | Windowsではpythonコマンドを使用 |
| `timeout /t 2 >/dev/null` | `timeout /t 2 /nobreak >nul` | タイマー（ユーザー入力スキップ付き） |

- バッチファイル作成・修正時は、必ず上記ルールに従うこと
- 修正後は `Select-String` で `/dev/null` や `python3` が残存していないか確認すること

## Known Gotchas
1. Alert monitor (`qwen_ocpm_signal_monitor.py`) is notification-only. Actual trading is done by `qwen_unified_live.py`.
2. `eth_account` module error → run `pip install eth_account hyperliquid-python-sdk`
3. Old `HL_Trader_Autostart.bat` has been removed from Startup. Only `Qwen_AutoTrader.lnk` remains.
