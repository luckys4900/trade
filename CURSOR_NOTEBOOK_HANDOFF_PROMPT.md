# Cursor Notebook Handoff Prompt

ノートPC側の `Cursor` で新しいチャットを開いたら、最初に以下をそのまま貼ってください。

```text
このノートPCで `trade` プロジェクトを運用できる状態までセットアップを継続して。

最初に次のファイルを読んで状況を把握してほしい:
- `LAPTOP_MIGRATION_HANDOFF.md`
- `PROJECT_STATUS.md`
- `NOTEBOOK_SETUP_CHECKLIST.md`
- `AGENTS.md`
- `CLAUDE.md`

前提:
- Windows ノートPC
- Cursor と Python は導入済み
- このフォルダはノートPC上にコピー済み
- `.env` は手元で配置する
- 目標は、このノートPCで本プロジェクトを安全に起動・確認できる状態にすること

やってほしいこと:
1. Python / pip / 依存の確認
2. 必要パッケージの導入
3. テスト実行
4. 起動バッチと常駐前提の確認
5. スリープや運用上の注意点の確認
6. 最後に、このノートPCでの起動手順を簡潔にまとめる

注意:
- `.env` は絶対にコミットしない
- Mainnet なので安全側で確認する
- 既存状態ファイルや実ポジションとの不整合を起こさないようにする
```
