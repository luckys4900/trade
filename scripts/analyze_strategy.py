#!/usr/bin/env python3
"""
Automatic strategy analysis harness – uses any LLM provider (OpenAI, Claude, OpenRouter, GLM5.1, etc.).

Features
========
* Detects changed files in the current commit.
* If the same file set has already been analysed, the run is skipped (unless ``--force`` is passed).
* Supports a *fallback* input file that can contain back‑test output – useful for a second LLM round.
* Sends the strategy context and optional back‑test info to the chosen LLM and expects a JSON response with the keys:
  ``summary`` | ``expected_value`` | ``status`` | ``notes``.
* Writes the result to ``analysis_history.md`` and optionally commits it.

Usage
-----
    python scripts/analyze_strategy.py [--commit] [--force] [--analysis_file path/to/file]

Environment Variables
---------------------
``LLM_MODEL``           : one of ``openai``, ``claude``, ``openrouter``, ``glm5.1``.
``OPENAI_API_KEY``      : required if ``LLM_MODEL=openai``.
``CLAUDE_API_KEY``      : required if ``LLM_MODEL=claude``.
``OPENROUTER_API_KEY``  : required if ``LLM_MODEL=openrouter``.
``GLM5_KEY``            : required if ``LLM_MODEL=glm5.1``.
"""

import os
import sys
import json
import subprocess
import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO_ROOT = Path("C:\\Users\\user\\Desktop\\cursor\\trade")
CLAUDE_FILE = REPO_ROOT / "claude.md"
HISTORY_FILE = REPO_ROOT / "analysis_history.md"
CHANGED_PATTERNS = ("*.py", "*.json", "*.md", "*.yml", "*.yaml")
EXPECTED_VALUE_THRESHOLD = 0.0  # change to tighten

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def git_changed_files() -> set[Path]:
    """Return a set of files changed in the last commit (absolute paths)."""
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", "HEAD~1"], cwd=REPO_ROOT)
        files = {Path(p.decode().strip()) for p in out.splitlines() if p}
    except subprocess.CalledProcessError:  # fresh repo
        files = set()
        for pattern in CHANGED_PATTERNS:
            files.update(REPO_ROOT.glob(pattern))
    return {f for f in files if f.exists()}


def read_file(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def last_id() -> int:
    if not HISTORY_FILE.exists():
        return 0
    for line in reversed(HISTORY_FILE.read_text(encoding="utf-8").splitlines()):
        if line.strip().startswith("{"):
            try:
                data = json.loads(line)
                return data.get("id", 0)
            except Exception:
                continue
    return 0


def prev_analysis_for(fset: set[Path]):
    if not HISTORY_FILE.exists():
        return None
    entries = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("{"):
            try:
                entry = json.loads(line)
                if set(Path(p) for p in entry.get("files_analyzed", [])) == fset:
                    entries.append(entry)
            except Exception:
                continue
    return max(entries, key=lambda e: e.get("id", 0)) if entries else None


def construct_prompt(fset: set[Path], base_content: str, backtest_content: str, entry_id: int) -> str:
    changed = "\n".join([f"- {f}" for f in fset]) or "*No files changed*"
    full = f"""
You are a seasoned crypto‑strategy analyst.  Here is the baseline strategy
definition section from the project:

---
{base_content}
---

The following files were changed in the latest commit:
{changed}

{backtest_content}

Please analyse the impact of these changes and produce a JSON object with
exactly the following keys:

1. summary   – short paragraph describing the effect.
2. expected_value – numerical expected value in percent per trade
   (e.g. '+0.45%' or '-0.12%').
3. status    – 'implemented' if the change meets the minimal expected value,
   'rejected' if it should not be implemented, or 'skipped' if no analysis needed.
4. notes     – any follow‑up actions.

Do **not** return any additional keys.
"""
    return full

# ---------------------------------------------------------------------------
# LLM Provider abstractions
# ---------------------------------------------------------------------------
import json
import requests

# Determine provider
LLM_MODEL = os.getenv("LLM_MODEL", "openrouter").lower()

# Map provider to call function

def call_openai(prompt: str, *args, **kwargs) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o",  # or read from env
        messages=[{"role":"user", "content":prompt}],
        temperature=0.2,
        max_tokens=1024,
    )
    content = resp.choices[0].message.content.strip()
    return json.loads(content)


def call_claude(prompt: str, *args, **kwargs) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    resp = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_output_tokens=1024,
        temperature=0.2,
        messages=[{"role":"user", "content":prompt}],
    )
    return json.loads(resp.content[0].text)


def call_openrouter(prompt: str, *args, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    resp = requests.post("https://api.openrouter.ai/v1/chat", json=data, headers=headers)
    resp.raise_for_status()
    return resp.json()


def call_glm5(prompt: str, *args, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {os.getenv('GLM5_KEY')}"}
    data = {
        "model": "glm5.1",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    resp = requests.post("https://api.glm5.com/v1/chat", json=data, headers=headers)
    resp.raise_for_status()
    return resp.json()

CALLERS = {
    "openai": call_openai,
    "claude": call_claude,
    "openrouter": call_openrouter,
    "glm5.1": call_glm5,
}

# ---------------------------------------------------------------------------
# History utilities
# ---------------------------------------------------------------------------

def append_history(entry: dict):
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, indent=2))
        f.write("\n\n")

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def main(force: bool = False, commit: bool = False, analysis_file: str | None = None):
    changed_files = git_changed_files()
    if not changed_files:
        print("No changed files detected; nothing to analyse.")
        return

    old_entry = prev_analysis_for(changed_files)
    if old_entry and not force:
        print(f"Skipping analysis: same file set was previously analysed (ID {old_entry.get('id')}).")
        skipped_entry = {
            "id": last_id() + 1,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "prompt": "NA – Skipped duplicate analysis.",
            "files_analyzed": [p.as_posix() for p in changed_files],
            "summary": f"Skipped – duplicate of ID {old_entry.get('id')}.",
            "expected_value": old_entry.get("expected_value", ""),
            "status": "skipped",
            "notes": f"See analysis ID {old_entry.get('id')} for details.",
            "skipped_from_id": old_entry.get("id"),
        }
        append_history(skipped_entry)
        if commit:
            subprocess.check_call(["git", "add", str(HISTORY_FILE)], cwd=REPO_ROOT)
            subprocess.check_call(["git", "commit", "-m", f"Add skipped analysis copy (ID {skipped_entry.get('id')})"], cwd=REPO_ROOT)
        return

    base_content = read_file(CLAUDE_FILE)
    backtest_content = ""
    if analysis_file:
        backtest_content = f"\n\n--- Backtest Results ---\n\n{read_file(Path(analysis_file))}"

    entry_id = last_id() + 1
    prompt = construct_prompt(changed_files, base_content, backtest_content, entry_id)

    print("Invoking LLM…")
    if LLM_MODEL not in CALLERS:
        raise ValueError(f"Unsupported LLM_MODEL: {LLM_MODEL}")
    result = CALLERS[LLM_MODEL](prompt)

    for key in ("summary", "expected_value", "status", "notes"):
        if key not in result:
            raise ValueError(f"LLM output missing key: {key}")

    analysis = {
        "id": entry_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "prompt": prompt.split("\nTask:")[0],
        "files_analyzed": [p.as_posix() for p in changed_files],
        "summary": result["summary"],
        "expected_value": result["expected_value"],
        "status": result["status"],
        "notes": result["notes"],
    }
    append_history(analysis)
    print(f"Analysis entry {entry_id} appended to {HISTORY_FILE}")

    if commit:
        subprocess.check_call(["git", "add", str(HISTORY_FILE)], cwd=REPO_ROOT)
        subprocess.check_call(["git", "commit", "-m", f"Update analysis history entry {entry_id}"], cwd=REPO_ROOT)


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    commit_flag = "--commit" in sys.argv
    analysis_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--analysis_file" and i + 1 < len(sys.argv):
            analysis_file = sys.argv[i + 1]
    main(force=force_flag, commit=commit_flag, analysis_file=analysis_file)
