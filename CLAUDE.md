# pipelinekit

Claude Code workflow toolkit: skills + agents + hooks + autonomous `/pipeline` orchestrator.

> Additive to `~/.claude/CLAUDE.md` (user-global) — never overrides. Project-specific rules only.

## Codebase Map

| Path | Purpose |
|------|---------|
| `claude/` | Workflow toolkit source — skills, agents, hooks, commands, rules, lib |
| `claude/skills/` | 42 skills as `SKILL.md` + support files (`tdd`, `pipeline`, ...) |
| `claude/skills/INDEX.md` | Auto-generated skill catalogue with one-liners. |
| `claude/skills/codegraph-init/` | Pre-flight + serve init for codegraph MCP (symbolic code graph). |
| `claude/skills/graphify-init/` | Pre-flight + serve init for graphify MCP (knowledge graph). |
| `claude/agents/` | 24 subagent personas (`code-reviewer.md`, `tdd-test-writer.md`, ...) |
| `claude/agents/INDEX.md` | Auto-generated agent catalogue with one-liners. |
| `claude/hooks/` | Bash + python hooks (`validate-commit-msg.sh`, `block-stage-sensitive.sh`, ...) |
| `claude/commands/` | Slash-command stubs (`/persona`, `/deploy-target`, ...) |
| `claude/lib/` | Shared helpers (`pipeline/`, `sandbox/`, `worker-provider/`) |
| `claude/rules/` | Operational rules (`workflow.md`, `agents-worktrees.md`) |
| `claude/model-overlays/` | Per-model behavioural overlays |
| `claude/host-adapters/` | Host-shell adapters (claude / codex / cursor / gemini) |
| `claude/config/` | `never-stage.txt` and other config data |
| `claude/memory/` | Memory index (`MEMORY.md`) |
| `claude/tresor-resources/` | Vendored prompt templates / standards |
| `claude/CLAUDE.md.template` | User-global template emitted by `scripts/install.sh` |
| `scripts/` | `install.sh`, sandbox helpers, cloud bootstrap, smoke scripts |
| `docs-source/` | Markdown sources for `documentation/*.html` |
| `documentation/` | Rendered HTML docs (committed) |
| `docs/` | Workflow metadata (`analysis-v*`, `plan-v*`, `progress.md`, ...) — NEVER committed |
| `tests/` | Repo-wide smoke / integration tests |
| `.github/workflows/` | GitHub Actions workflows — currently `ci.yml` (lint / selftests / install-smoke) |
| `lancedb/` | Local RAG index storage |

Full map: [documentation/codebase-map.html](documentation/codebase-map.html)
Default MCP stack: [documentation/memory-graph-stack.html](documentation/memory-graph-stack.html) (agentmemory + Understand-Anything + codegraph + graphify).

## Caveman Mode (default-on, wenyan-ultra)

每回應緊守三區劃分 — 文言為敘述肌理，英文為精確面。漂移即違約。

| Zone | Content | Language |
|------|---------|----------|
| **Zone 1** | code, paths, commits, commands, env vars, security-sensitive identifiers | English verbatim |
| **Zone 2** | narrative, reasoning, transitions, explanations | 文言 — drop articles, filler, hedging |
| **Zone 3** | status fragments, headers, terse bullets, tool-call preambles | ultra English |

**Operational contracts:**

- **Subagent propagation** — `Agent` dispatch prompts MUST prepend `<caveman-inherited level="wenyan-ultra">…</caveman-inherited>` per `~/.claude/snippets/caveman-subagent.md`. Bundled and worktree agents both inherit. Missing inheritance tag → drift cascade.
- **SessionStart marker** — `claude/hooks/session-start-caveman.sh` touches `~/.claude/.caveman-active` on every session boot + PostCompact. Marker absence (and `CAVEMAN_OFF=1` env) silently disables enforcement.
- **PreToolUse gate** — `claude/hooks/agent-caveman-gate.sh` rewrites onward `Agent` prompts at dispatch time when `caveman-active` marker present.
- **Toggle** — `/caveman lite | full | ultra | wenyan | off`. Default at install: `wenyan-ultra`.
- **Skill body** — `claude/skills/caveman-mode/SKILL.md` (full doctrine, exemplars, anti-patterns).

**Cross-reference:** user-global `~/.claude/CLAUDE.md` Core Principle 5 carries authoritative doctrine; this section is its project mirror. Edit there for global change, here for project-specific carve-outs only.

## Lean Conventions

- **Caveman mode** — see § Caveman Mode above. wenyan-ultra default, three-zone split, subagent inheritance contract.
- **Conventional commits only**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `style:`, `build:`, `ci:`. No emojis. Enforced by `claude/hooks/validate-commit-msg.sh`.
- **No AI attribution** — zero Claude / LLM refs in commits, PRs, code, docs. No `Co-Authored-By`, no "Generated with".
- **Never-stage list**: `claude/config/never-stage.txt`. Hook `claude/hooks/block-stage-sensitive.sh` refuses matched paths.
- **Base-branch detection**: canonical snippet at `~/.claude/rules/workflow.md` § Base Branch Detection.
- **Verification first** — after every change run build + tests; restart app if applicable. Do not mark done without passing verification.
- **Plan trust** — when plan gives exact files/lines/code, skip exploration, implement directly.
- **Commit only when asked** — wait for explicit confirmation. Exception: worktree agents auto-commit `wip:` before reporting done.
- **Subagent-first** — non-trivial work dispatches via `Agent`. Inline exception: ≤ 3 tool calls, interactive Q&A, or explicit opt-out phrase (`no subagents`, `do it inline`, etc.). See `~/.claude/rules/agents-worktrees.md § Subagent Defaults`.

## Subdirectory Init

Subdir `CLAUDE.md` overrides root w/ dir-specific rules. Harness loads on entry:

- `claude/skills/CLAUDE.md` — skill authoring (frontmatter, `paths:` scoping, `allowed-tools`, snippets).
- `claude/agents/CLAUDE.md` — agent authoring (tool allowlist, model, `<task-notification>` XML, prompt shape).
- `claude/hooks/CLAUDE.md` — hook authoring (stdin/stdout JSON, exit codes, python3 vs bash, denial-tracker).

Self-contained — no x-ref to root needed.

## Working Surface

New work lands here:

- `claude/skills/<name>/SKILL.md` — new skills (+ support files alongside).
- `claude/agents/<name>.md` — new agents (single-file md with YAML frontmatter).
- `claude/hooks/<name>.{sh,py}` — new hooks (+ helper modules alongside).
- `claude/commands/<name>.md` — slash-command stubs.
- `claude/rules/<name>.md` — operational rules.
- `docs-source/<page>.md` — public docs (rendered to `documentation/<page>.html`).
- `tests/` and `claude/skills/*/tests/` — tests.

Never edit by hand:

- `documentation/*.html` — auto-rendered from `docs-source/*.md` via `python3 claude/skills/docs-writer/render.py`. Hand-edits overwritten next render.
- `docs/*` — workflow metadata from pipeline phases (never committed; managed by skills, not humans).
