#!/usr/bin/env python3
"""
Generate a concise Markdown summary of all LLM analysis entries.

The output file `analysis_summary.md` contains a table with the following columns:

1. **ID** – Entry number.
2. **Timestamp** – UTC time of the analysis.
3. **Summary** – First sentence of the analysis summary.
4. **Expected Value** – Numeric expected value (e.g. "+0.65% per trade").
5. **Status** – If present in the original entry; otherwise "N/A".

This table can be imported into a knowledge base or linked from other report files.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path("C:\\Users\\user\\Desktop\\cursor\\trade")
HISTORY_FILE = REPO_ROOT / "analysis_history.md"
SUMMARY_FILE = REPO_ROOT / "analysis_summary.md"

# Regex to extract JSON blocks inside triple backticks ```` ```{json} ... ``` ````
JSON_BLOCK_RE = re.compile(r"```\s*\{.*?\}\s*```", re.S)

# Extract JSON objects
entries = []
for block in JSON_BLOCK_RE.findall(HISTORY_FILE.read_text("utf-8")):
    try:
        data = json.loads(block.strip("`\n"))
        entries.append(data)
    except Exception:
        continue

# Build markdown table
lines = []
lines.append("# LLM Analysis Summary\n")
lines.append("| ID | Timestamp | Summary | Expected Value | Status |")
lines.append("| --- | --------- | ------- | -------------- | ------ |")
for entry in sorted(entries, key=lambda e: e.get("id", 0)):
    id_ = entry.get("id", "?")
    ts = entry.get("timestamp", "?")
    sm = entry.get("summary", "").strip()
    # first sentence only
    sm_first = sm.split(". ")[0] if sm else ""
    ev = entry.get("expected_value", "").split(" ")[0] if entry.get("expected_value") else ""
    status = entry.get("status", "N/A")
    lines.append(f"| {id_} | {ts} | {sm_first} | {ev} | {status} |")

# Write file
SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"Generated summary to {SUMMARY_FILE}")
