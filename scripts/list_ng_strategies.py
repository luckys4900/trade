#!/usr/bin/env python3
"""
Generate a Markdown list of all LLM analyses that were marked as *rejected*.

The file `ng_strategies.md` will contain a table with ID, timestamp, summary,
expected_value and notes.  This is useful for quick reference of strategies
that have been vetoed and should not be retried without a fresh justification.
"""

import json
from pathlib import Path

REPO_ROOT = Path("C:\\Users\\user\\Desktop\\cursor\\trade")
HISTORY_FILE = REPO_ROOT / "analysis_history.md"
OUTPUT_FILE = REPO_ROOT / "ng_strategies.md"

# Regular expression to extract JSON blocks from the markdown file
import re
BLOCK_RE = re.compile(r"```\s*\{.*?\}\s*```", re.S)

entries = []
for block in BLOCK_RE.findall(HISTORY_FILE.read_text("utf-8")):
    try:
        entries.append(json.loads(block.strip("`\n")))
    except Exception:
        continue

# Filter rejected entries
rejected = [e for e in entries if e.get("status") == "rejected"]

lines = []
lines.append("# Rejected Trade Strategies
\nBelow is a list of strategy analyses that the LLM marked as "rejected".\n")
lines.append("| ID | Timestamp | Summary | Expected Value | Notes |")
lines.append("| --- | --------- | ------- | -------------- | ----- |")
for e in rejected:
    id_ = e.get("id", "?")
    ts = e.get("timestamp", "?")
    sm = e.get("summary", "").replace("|", "\u007C")  # escape pipe
    ev = e.get("expected_value", "").split(" ")[0] if e.get("expected_value") else ""
    nb = e.get("notes", "").replace("|", "\u007C")
    lines.append(f"| {id_} | {ts} | {sm} | {ev} | {nb} |")

OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"Generated {OUTPUT_FILE}")
