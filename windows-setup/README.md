# memsearch Windows Auto-Setup

Macで設定したmemsearchを、Windows側でも自動同期・導入するためのセットアップ。

## 概要

```
[Mac] 設定完了 → git push → [GitHub]
                              ↓ (30分ごとにチェック)
[Windows] git pull → 変更検知 → 自動インストール → Windows通知
```

## ファイル構成

| ファイル | 説明 |
|---|---|
| `setup.bat` | memsearch本体のインストール + ONNX設定（トークン節約） |
| `sync-and-notify.ps1` | GitHub変更検知 + 自動同期 + Windows通知 |
| `register-task.bat` | タスクスケジューラへの登録（30分ごと実行） |

## Windows側での手順

### 1. 初回セットアップ

1. GitHubからリポジトリをクローン（またはpull）
2. `windows-setup\setup.bat` を**ダブルクリック**
   - Python 3.10+ がインストールされていること
   - memsearch + ONNX埋め込みが自動インストールされる
   - **トークン消費ゼロ**のローカルモデル設定が適用される

### 2. 自動同期の有効化

1. `windows-setup\register-task.bat` を**管理者として実行**
2. タスクスケジューラに `memsearch-AutoSync` が登録される
3. **30分ごと**にGitHubの変更をチェック
   - 新しいコミットがあれば自動 `git pull`
   - `.memsearch/memory/` に新しいファイルがあればインデックス再構築
   - Windows通知で同期完了を報告

### 3. 動作確認

```cmd
REM タスク状態確認
schtasks /query /tn "memsearch-AutoSync"

REM 同期ログ確認
type windows-setup\sync.log

REM 手動同期テスト
powershell -ExecutionPolicy Bypass -File windows-setup\sync-and-notify.ps1
```

## トークン節約設定

本セットアップでは以下の設定が自動適用されます:

| 設定 | 値 | 理由 |
|---|---|---|
| 埋め込みモデル | `ONNX bge-m3` | ローカルCPU完結、APIキー不要、**トークン消費ゼロ** |
| Milvusバックエンド | `Milvus Lite` | ローカル`.db`ファイル、ゼロコンフィグ |
| 要約モデル | OpenCode/Claude設定依存 | 軽量モデル（Haiku等）を推奨 |

## OpenCodeプラグイン設定（任意）

WindowsでOpenCodeを使用する場合（WSL2推奨）:

```json
// ~/.config/opencode/opencode.json に追加
{
  "plugin": ["@zilliz/memsearch-opencode"]
}
```

**注意**: OpenCodeプラグインはWindowsネイティブ非対応。WSL2環境で実行してください。

## Claude Codeプラグイン設定（推奨）

WindowsでClaude Codeを使用する場合:

```
/plugin marketplace add zilliztech/memsearch
/plugin install memsearch
```

## トラブルシューティング

### memsearchが見つからない
```cmd
python -m pip install "memsearch[onnx]"
```

### タスクが実行されない
- タスクスケジューラで `memsearch-AutoSync` の実行履歴を確認
- PowerShell実行ポリシー: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 通知が表示されない
- `windows-setup\sync.log` を確認
- `%TEMP%\memsearch-sync-notification.txt` にフォールバック通知が保存される

## Mac側での作業

Macで新しいプロジェクトを開始したら:
1. OpenCodeで会話（記憶が自動保存される）
2. `.memsearch/memory/` の変更を `git commit` + `git push`
3. Windows側が30分以内に自動検知・同期
