---
diataxis: explanation
---

# pipelinekit documentation

pipelinekit v0.1.0 is a small Claude Code config kit. It contains guard hooks, permission rules, global git hooks, six skills, a short `CLAUDE.md` template, and an installer that copies them into `~/.claude`.

<div data-snippet="search-widget"></div>

## What it is now

Up to 0.0.1, pipelinekit was a multi-agent pipeline kit with its own orchestrator, review panel, persona agents and memory stack. Current Claude Code covers most of that natively with plan mode, the Workflow tool, `/code-review`, `/security-review`, `/simplify`, the Explore and Plan agents, auto-memory, worktree isolation, `/loop` and `/schedule`. v0.1.0 keeps only what Claude Code does not ship.

> The hooks and skills are still being reviewed and may change in later releases. The hooks are guardrails that catch common mistakes. They are not a security boundary.

## Pages

| Page | Read it when |
|------|--------------|
| [Installation](installation.html) | You are setting up the kit on a new machine, devcontainer or VM |
| [Components](components.html) | You want to know what each permission rule, hook, git hook, skill and MCP server does |
| [Upgrading from 0.0.1](upgrading.html) | You installed the old pipeline kit and want to move to 0.1.0 |

The full list of changes is in [CHANGELOG.md](https://github.com/Bruce188/pipelinekit/blob/main/CHANGELOG.md).

## Rebuilding these pages

These HTML pages are generated from the markdown in `docs-source/`. To render every page and the search index:

```bash
python3 claude/skills/docs-writer/render.py
```
