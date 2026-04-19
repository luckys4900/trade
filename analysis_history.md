# Analysis History

This document keeps a structured record of all LLM analysis sessions performed on the BTC strategy code in this repository.

## Format

Each entry is a JSON‑style block that includes:

1. **id** – Auto‑incremented integer.
2. **timestamp** – ISO‑8601 UTC time of the session.
3. **prompt** – The user prompt or internal instruction given to the LLM.
4. **files_analyzed** – List of repository files that were examined during the session.
5. **summary** – A concise textual summary of the conclusions and detected issues.
6. **expected_value** – Preliminary expected value or risk‑return estimate, if applicable.
7. **notes** – Any follow‑up actions, questions for the next iteration, or links to relevant issues/todos.

---

```
{
  "id": 1,
  "timestamp": "2026-04-12T12:00:00Z",
  "prompt": "Analyze the OCPM strategy performance and suggest improvements.",
  "files_analyzed": ["qwen_unified_live.py", "config.json", "trade_state_unified.json"],
  "summary": "The strategy exhibits a high win rate but low average profit due to conservative SL/TP. Suggested adjustment: tighten OB threshold to 68.",
  "expected_value": "+0.65% per trade (estimated)",
  "notes": "Implement EL in config.json, re‑run backtest for 90 days."
}
```

Each new analysis session should be appended to this file, preserving the chronological order. The LLM can reference this history in subsequent prompts to avoid re‐analyzing unchanged files.

---

> **Important:** When creating new entries, always keep the JSON blocks well‑formatted and valid. This enables programmatic parsing by downstream tools or additional LLM runs.
