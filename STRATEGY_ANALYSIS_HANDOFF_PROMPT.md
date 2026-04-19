# Strategy Analysis Handoff Prompt

別LLMでこのプロジェクトの戦略分析を再開するときは、最初に次を必ず読んでください。

- `memory/MEMORY.md`
- `memory/strategy_ev_analysis_2026-04-15.md`
- `PROJECT_STATUS.md`
- `SYSTEM/qwen_unified_live.py`
- `test_contrarian_integration.py`

前提:
- プロジェクトは BTC 中心の自動売買
- 現時点で live には `Contrarian mid-volatility gate` と `OCPM hard regime only` が反映済み
- 古いターミナル要約より、フレッシュに回したバックテスト結果を優先する
- 「戦略を増やして回数を増やす」より、「悪い局面を削って期待値を上げる」方針を優先する

最初にやること:
1. 既に試した改善案と未実装案を整理
2. すでに live に入っている条件を整理
3. 重複提案を避ける
4. 次に検証すべき改善案を、期待値 / PF / DD / trade frequency の観点で優先順位付けする

分析で重視すること:
- BTC 4h を主軸とする
- expectancy, PF, MDD, trade count, trades per month を明示する
- fresh backtest evidence を優先する
- 価格系の類似戦略追加より、regime / funding / OI / basis / session bias のような異なる歪みを優先する

今回までの重要な結論:
- `Contrarian` は無条件運用より `mid-volatility gate` の方が改善
- `Contrarian + trend` は悪化
- `Legacy` は exit quality と regime filtering の改善余地が大きい
- `hard_ocpm_only` は trade frequency と quality のバランスが最も良かった

この前提を理解してから、新しい分析を開始してください。
