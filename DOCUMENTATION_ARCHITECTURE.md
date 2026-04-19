# Documentation Architecture - Multi-Environment Integration

Complete mapping of how documentation serves all development environments.

## Document Function Matrix

| Doc | Purpose | CLI | IDE | LLM | Read When |
|-----|---------|-----|-----|-----|-----------|
| CLAUDE.md | Status, architecture | Auto | Auto | Manual | Session start |
| DEVELOPMENT_PROCESS.md | 5-stage workflow | Ref | Ref | Include | Before task |
| CONTEXT_MANAGEMENT.md | Budget rules | Ref | IDE | Manual | When >50% |
| TOOLING.md | Tool decisions | Ref | Chat | Include | New tool |
| GIT_WORKFLOW.md | Worktree usage | Copy | Terminal | Include | Parallel work |
| MULTI_ENVIRONMENT_GUIDE.md | Cross-tool | Ref | Ref | Ref | Switch tools |
| AGENTS.md | Multi-agent | Optional | Optional | Primary | External LLM |

## File Organization

All tools read from:
1. CLAUDE.md (project status - auto-loaded)
2. .cursorrules (IDE enforcement)
3. DEVELOPMENT_PROCESS.md (unified workflow)
4. CONTEXT_MANAGEMENT.md (budget rules)
5. TOOLING.md (tool selection)
6. MULTI_ENVIRONMENT_GUIDE.md (cross-tool guide)

## Reading Sequence

New Session:
1. CLAUDE.md (2 min) - understand status
2. DEVELOPMENT_PROCESS.md (3 min) - understand workflow
3. Task-specific doc (5 min)
4. Start work

Adding Feature:
1. Brainstorm → Plan → Implement → Review → Merge
2. Then: /clear (reset context)

Switching Tools:
1. Save: git commit
2. Read: MULTI_ENVIRONMENT_GUIDE.md
3. Continue: same docs, same process

## Summary

All three environments (CLI, IDE, LLM) use same core documents:
- CLAUDE.md (status)
- DEVELOPMENT_PROCESS.md (workflow)
- Tool-specific: .cursorrules (IDE), AGENTS.md (LLM)

Ensures consistent process and efficient context usage.
