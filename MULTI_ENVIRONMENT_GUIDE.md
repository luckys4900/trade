# Multi-Environment Unified Development Guide

**Objective**: Ensure consistent process and context management across all development environments.

---

## Environment Overview

Three primary development environments, one unified process:

1. **Claude Code CLI** (Terminal)
2. **Cursor IDE** (Editor with Claude)
3. **External LLMs** (Gemini, Copilot, etc.)

All read from shared files:
- CLAUDE.md (project status)
- DEVELOPMENT_PROCESS.md (workflow)
- CONTEXT_MANAGEMENT.md (budget rules)
- TOOLING.md (tool selection)
- GIT_WORKFLOW.md (git practices)

---

## 1. Claude Code CLI (Terminal)

### Setup
```bash
cat CLAUDE.md                    # Review status
claude --install-status-line     # Enable monitoring
claude                           # Start session
```

### Usage: Brainstorm → Plan → Implement → Review → Merge

```
/brainstorm              # Validate requirements
/plan                    # Implementation strategy
Implement                # Code changes (or subagents)
/review-pr              # Quality check
git commit              # Save changes
/clear                  # Reset context
```

### Context Monitoring
```
Status Line: ~/trade · opus-4 · 1M ctx · 45% ■■■■░░
                                        ↑ Monitor
Safe:        0-50%  ✓
Caution:     50-70% ⚠
Danger:      70-85% 🔴 → /clear
Critical:    85%+   🚨 → /clear immediately
```

---

## 2. Cursor IDE (Editor)

### Setup
```
Cursor → Settings → Claude Extension → Install
Settings → Verify .cursorrules loaded
→ "Rules loaded: X rules from .cursorrules"
```

### Usage: Cmd+K Chat with Context

**Good**: Ask specific questions referencing CLAUDE.md

**Best**: Explicitly follow DEVELOPMENT_PROCESS.md stages

Example:
```
"Follow DEVELOPMENT_PROCESS.md:
1. Brainstorm: validate Range MR v2
2. Plan: which files change?
3. Then we'll implement"
```

### Key References
- CLAUDE.md (status)
- .cursorrules (IDE rules)
- DEVELOPMENT_PROCESS.md (workflow)
- CONTEXT_MANAGEMENT.md (token budget)

---

## 3. External LLMs (Gemini, etc.)

### Before Asking

```bash
# Collect context
cat AGENTS.md                    # Multi-agent instructions
cat CLAUDE.md                    # Project status
cat DEVELOPMENT_PROCESS.md       # Workflow rules
```

### Prompt Structure

```
**Project Context**
[From CLAUDE.md]

**Mandatory Process** (from DEVELOPMENT_PROCESS.md)
1. Brainstorm → validate
2. Plan → document
3. Implement → code
4. Review → quality
5. Merge → integrate

**Task**: [Specific request]

**Constraints**:
- CLAUDE.md < 500 lines (frozen)
- One task per session
- Follow AGENTS.md for delegation
- No modifications to: qwen_unified_live.py, whale_monitor.py
```

---

## Switching Between Environments

### CLI → IDE
```bash
# CLI work done
git commit -m "feat: ..."
/clear

# Switch to IDE
→ Cursor auto-loads CLAUDE.md
→ .cursorrules enforces process
→ Fresh context
```

### IDE → CLI
```
Cursor work done
→ git commit

Terminal:
  git pull
  claude
  → CLAUDE.md loaded
  → Continue work
```

### Any → External LLM
```
Save: git commit
Provide: AGENTS.md + CLAUDE.md + task definition
Follow: DEVELOPMENT_PROCESS.md workflow
Integrate: results back to repo
```

---

## Unified Checklist

### Before Starting
- [ ] CLAUDE.md read
- [ ] Git clean (no uncommitted)
- [ ] Task singular & bounded
- [ ] Process clear: Brainstorm → Plan → Implement → Review

### During Work
- [ ] Monitor context (CLI: status line, IDE: estimate, LLM: careful)
- [ ] Follow DEVELOPMENT_PROCESS.md stages
- [ ] Reference correct docs
- [ ] No frozen files modified without plan

### After Completion
- [ ] Tests pass
- [ ] CLAUDE.md updated (if needed)
- [ ] git commit
- [ ] /clear or end session
- [ ] New session for next task

---

## Document Hierarchy: Always Read in Order

```
1. CLAUDE.md (5 min)
   ↓ Understand project status

2. DEVELOPMENT_PROCESS.md (10 min)
   ↓ Understand workflow

3. Task-specific doc
   ↓ TOOLING.md, GIT_WORKFLOW.md, etc.

4. Start work
```

---

## Context Budget Across Environments

**Claude Code CLI**
```
Start:      1.2K (CLAUDE.md)
Task:       +5-10K
Review:     +3K
Available:  Usually 200K+ ✓
```

**Cursor IDE**
```
Setup:      ~5K
Question:   +2-5K
Rules:      ~500
Available:  Usually 150K+ ✓
```

**External LLM**
```
Docs:       +5-10K
Prompt:     +2-5K
Response:   ~5K
Available:  Varies, plan ahead
```

---

## Troubleshooting

### Different behavior CLI vs IDE?
→ Check: Cursor Settings → .cursorrules loaded?
→ Fix: Reload window (Cmd+R)

### External LLM ignores process?
→ Add DEVELOPMENT_PROCESS.md to prompt explicitly
→ Say: "Follow these 5 stages exactly"

### Context overflow?
→ CLI: /clear → new session
→ IDE: close tab → new chat
→ LLM: end → new conversation

### Git conflicts?
→ Use: git worktree add ./worktrees/feature
→ Work in isolation, no conflicts

---

## Quick Reference: Three Environments

| Aspect | CLI | IDE | External LLM |
|--------|-----|-----|--------------|
| **Config** | CLAUDE.md | .cursorrules | AGENTS.md |
| **Context Monitor** | Status line | Time estimate | Manual |
| **Process** | /brainstorm /plan | Cmd+K refs | Explicit steps |
| **Reset** | /clear | New chat | New session |
| **Best For** | Long tasks | Quick edits | Complex analysis |

---

## Summary

**One process, three interfaces**:

1. Learn DEVELOPMENT_PROCESS.md once
2. Apply it in CLI, IDE, or external LLM
3. Monitor context religiously
4. Reset session after each task
5. Archive completed work

All environments share the same rules because they share the same project context.

