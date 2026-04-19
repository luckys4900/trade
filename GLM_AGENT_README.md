# GLMマスター → サブエージェント並列実行システム

## 概要
GLMマスターAIがタスクを分析し、OllamaとOpenRouterのサブエージェントに並列で割り当てるシステム。

## 構成
- **GLMマスター**: タスク分割と結果統合
- **Ollamaエージェント**: 高速なローカル処理（構文チェック・コード生成）
- **OpenRouterエージェント**: 高品質なクラウド処理（アルゴリズム分析・コードレビュー）

## 実行方法

### 1. 環境設定
```bash
# 必要なライブラリをインストール
pip install openai-swarm

# Ollamaのインストール
# https://ollama.com/ からダウンロード
```

### 2. 設定ファイル
`.env`ファイルを作成：
```env
OPENROUTER_API_KEY=your_openrouter_key
GLM_API_KEY=your_glm_key
```

### 3. 実行
```bash
python glm_master_swarm.py
```

## 使用例
```python
from glm_master_swarm import GLMAgentSwarm

swarm = GLMAgentSwarm()

# マスターAIでタスク割り当て
result = swarm.run_master_agent("Pythonのバブルソートを作成し最適化してください")

# 並列実行
parallel_results = asyncio.run(swarm.execute_parallel_tasks("Pythonのバブルソートを作成し最適化してください"))
```

## 各エージェントの役割

### GLMマスター
- タスクの分割戦略を決定
- 各サブエージェントの結果を統合
- 最終的な回答を生成

### Ollamaエージェント
- 高速な構文チェック
- サンプルコード生成
- シンプルなデータ処理

### OpenRouterエージェント  
- 複雑なアルゴリズム分析
- 高品質なコードレビュー
- パフォーマンス最適化提案

## カスタマイズ
- サブエージェントの追加/削除
- モデルの変更（Ollama: llama3.1, OpenRouter: claude-3.5-sonnet）
- タスク割り当てルールの調整

## 出力例
```
=== GLMマスターAIによる並列処理開始 ===
リクエスト: Pythonのバブルソートを作成し最適化してください

1. GLMマスターによるタスク割り当て...
マスター結果: タスクを4つのサブエージェントに割り当てました

2. サブエージェントによる並列実行...

=== 各サブエージェントの結果 ===
[ollama_analyzer]:
構文チェック完了。バブルソートの基本実装が正しいことを確認。

[ollama_coder]:
```python
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
```

[openrouter_analyst]:
アルゴリズム分析完了。O(n²)の時間複雑度。最適化可能点: 早期終了の導入。

[openrouter_reviewer]:
改善提案: 早期終了とswappedフラグの導入により効率化可能です。
```

## 注意事項
- APIキーは.envファイルに設定
- Ollamaは事前にインストールが必要
- OpenRouterの利用にはAPIキーが必要
- 並列実行はasyncioを使用