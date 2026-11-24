---
diataxis: reference
---

# Components

This page lists what pipelinekit v0.1.0 installs and what each part does.

> The hooks and skills are still being reviewed, so details may change in later releases. The hooks are guardrails that catch common mistakes. They are not a security boundary, and they do not replace review.

## Overview

The kit has six layers. Hover a chip for a one-line summary, or use the buttons to focus on one layer.

<div data-snippet="architecture-diagram">
<script type="application/json">
{"layers": [
  {"name": "Settings rules", "color": "#ef4444", "count": "settings.json",
   "chips": [{"label": "permissions.deny", "tip": "No reading or editing secrets, keys or credentials"},
             {"label": "permissions.ask", "tip": "Prompt before editing Claude config or destructive git"},
             {"label": "attribution off", "tip": "No co-author trailer or PR footer"}]},
  {"name": "Claude Code hooks", "color": "#f59e0b", "count": "4 scripts",
   "chips": [{"label": "bash-guard.py", "tip": "PreToolUse Bash: git, docker, fetch and SQL rules"},
             {"label": "block-bare-repo-markers.py", "tip": "PreToolUse Edit/Write"},
             {"label": "post-edit-format.sh", "tip": "PostToolUse Edit/Write: prettier"},
             {"label": "session-check.py", "tip": "SessionStart: quick self-check, silent when healthy"}]},
  {"name": "Git hooks", "color": "#3b82f6", "count": "global core.hooksPath",
   "chips": [{"label": "commit-msg", "tip": "Conventional commits, no attribution or emoji"},
             {"label": "pre-commit", "tip": "gitleaks on staged changes, file size limit"},
             {"label": "pre-merge-commit", "tip": "File size limit on merges made without conflicts"},
             {"label": "pre-push", "tip": "No pushes to main or master"}]},
  {"name": "Skills", "color": "#10b981", "count": "9 skills",
   "chips": [{"label": "dotnet-conventions"}, {"label": "deploy"}, {"label": "exchange-api-keys"},
             {"label": "docs-writer"},
             {"label": "frontend-design", "tip": "Visual design guidance, from anthropics/skills (Apache-2.0)"},
             {"label": "mobile"},
             {"label": "kit", "tip": "Self-check, run as /kit"},
             {"label": "ship", "tip": "Test, fix and merge your own pull request"},
             {"label": "judge-loop", "tip": "Plan, build and judge a change until it reaches 10"}]},
  {"name": "Agents", "color": "#ec4899", "count": "3 agents",
   "chips": [{"label": "kit-planner", "tip": "Model: opus"},
             {"label": "kit-builder", "tip": "Model: opus"},
             {"label": "kit-judge", "tip": "Model: fable"}]},
  {"name": "MCP", "color": "#8b5cf6",
   "chips": [{"label": "serena", "tip": "Installed by default at a pinned commit"},
             {"label": "context7", "tip": "Optional, per project"}]}]}
</script>
</div>

## Pages

| Page | What it covers |
|------|----------------|
| [Hooks and rule ids](hooks.html) | The permission rules, the guard hooks, the never-stage list, the git hooks, the file size limit, and the rule ids and event log |
| [Skills and agents](skills.html) | The skills, what they run without asking, the three agents, and the plan, build, judge loop |
| [Self-check](self-check.html) | What `/kit` checks, the check when a session starts, and `/kit update` |
| [Shipping a pull request](shipping.html) | How Claude tests and merges its own pull requests, and the gates of `ship.py merge` |

## CLAUDE.md template

`claude/CLAUDE.md.template` is 81 lines of English with no imported rule files. The installer fills in `${USER_NAME}`, `${USER_EMAIL}` and `${CLAUDE_HOME}` and writes the result to `~/.claude/CLAUDE.md`. It covers:

- your identity;
- git rules: commit only when asked, conventional commits, no AI attribution, no workflow jargon in commit text, the never-stage list, `.git/info/exclude` for Claude-specific ignores, and no direct pushes to `main`;
- the `docs/` (local, never committed) and `documentation/` (committed) split;
- a base-branch detection snippet;
- serena for symbol navigation, Grep/Glob for text;
- the file size limit: at most 1,500 lines and 50,000 bytes for a hand-written file, and new code that would take a file past it goes in a new file;
- decisions that are yours to make, asked as interactive questions: two to four options, each with its upside and downside, the recommended one first;
- design: load `frontend-design` before building or reshaping anything a person looks at; the project's own design system or brand comes first, then the host's rules for the output, then the skill; the `dataviz` skill, when the session has it, decides chart form; `docs-writer` pages keep the template's CSS variables; skip it for work with no visual output and for small fixes inside an existing design;
- plan, build, judge: a change that is more than a small fix is planned, built and judged with the `judge-loop` skill, to 10 out of 10 in at most five rounds each; the three switch lines; and how every agent it starts reads files and answers (only the form when given a JSON form, else at most 15 lines);
- GitHub habits with `gh`: issues with acceptance criteria before work, `<type>/<issue#>-<slug>` branches, draft PRs on a branch up to date with its base, finishing its own PRs with the `ship` skill, reading CI logs, releases when you ask;
- the deploy CLIs.

## MCP servers

| Server | Installed by default | Notes |
|--------|----------------------|-------|
| serena | Yes, unless you pass `--no-serena` | Symbol-level code navigation. Installed with `uv` from a pinned commit and registered at user scope in `~/.claude.json`. A project `.mcp.json` entry takes precedence |
| context7 | No | Library and framework docs. Copy its entry from `.mcp.json.template` into a project's `.mcp.json` |

## What is not included

Plan mode, the Workflow tool, `/code-review`, `/security-review`, `/simplify`, the Explore and Plan agents, auto-memory, worktree isolation, `/loop` and `/schedule` are all built into Claude Code. pipelinekit no longer provides its own versions. See [Upgrading from 0.0.1](upgrading.html#what-was-removed) for how the old components map to these built-ins.

The judge loop is not the old pipeline back. It is one helper, three agents, a rule and a merge gate, and the kit keeps it because Claude Code ships no judge on a second model that scores a plan or a build, within a round budget, until it reaches 10.
