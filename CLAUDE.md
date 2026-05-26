# pipelinekit

Claude Code workflow toolkit: skills + agents + hooks + autonomous `/pipeline` orchestrator.

> Additive to `~/.claude/CLAUDE.md` (user-global) — never overrides. Project-specific rules only.

## Codebase Map

| Path | Purpose |
|------|---------|
| `claude/` | Workflow toolkit source — skills, agents, hooks, commands, rules, lib |
| `claude/skills/` | 42 skills authored as `SKILL.md` + supporting files (`tdd`, `pipeline`, `docs-writer`, ...) |
| `claude/skills/INDEX.md` | Auto-generated text catalogue of all skills with one-line descriptions. |
| `claude/skills/codegraph-init/` | Pre-flight + serve init for the codegraph MCP (symbolic code graph). |
| `claude/skills/graphify-init/` | Pre-flight + serve init for the graphify MCP (knowledge graph). |
| `claude/agents/` | 24 subagent personas (`code-reviewer.md`, `tdd-test-writer.md`, ...) |
| `claude/agents/INDEX.md` | Auto-generated text catalogue of all callable agents with one-line descriptions. |
| `claude/hooks/` | Bash + python pre/post hooks (`validate-commit-msg.sh`, `block-stage-sensitive.sh`, ...) |
| `claude/commands/` | Slash-command stubs (`/persona`, `/deploy-target`, ...) |
| `claude/lib/` | Shared helper libraries (`pipeline/`, `sandbox/`, `worker-provider/`) |
| `claude/rules/` | Operational rules (`workflow.md`, `agents-worktrees.md`) |
| `claude/model-overlays/` | Per-model behavioural overlays |
| `claude/host-adapters/` | Host-shell adapters (claude / codex / cursor / gemini) |
| `claude/config/` | `never-stage.txt` and other config data files |
| `claude/memory/` | Memory index (`MEMORY.md`) |
| `claude/tresor-resources/` | Vendored prompt templates / standards |
| `claude/CLAUDE.md.template` | User-global CLAUDE.md template emitted by `scripts/install.sh` |
| `scripts/` | `install.sh`, sandbox helpers, cloud bootstrap, smoke scripts |
| `docs-source/` | Markdown sources for `documentation/*.html` (rendered via docs-writer) |
| `documentation/` | Rendered HTML application docs (committed) |
| `docs/` | Workflow metadata (`analysis-v*`, `plan-v*`, `progress.md`, ...) — NEVER committed |
| `tests/` | Repo-wide smoke / integration tests |
| `lancedb/` | Local RAG index storage |

Full map: [documentation/codebase-map.html](documentation/codebase-map.html)
Default MCP stack: [documentation/memory-graph-stack.html](documentation/memory-graph-stack.html) (agentmemory + Understand-Anything + codegraph + graphify).

## Lean Conventions

- **Caveman mode** active by default (wenyan-ultra). Drop articles, filler, hedging. Code, commits, and security-critical text stay normal English. Toggle: `/caveman lite|full|ultra` or "stop caveman".
- **Conventional commits only**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `style:`, `build:`, `ci:`. No emojis. Enforced by `claude/hooks/validate-commit-msg.sh`.
- **No AI attribution** — zero Claude / LLM references in commits, PRs, code, or docs. No `Co-Authored-By`, no "Generated with".
- **Never-stage list** lives at `claude/config/never-stage.txt`. The hook `claude/hooks/block-stage-sensitive.sh` reads it and refuses staging of any matched path.
- **Base-branch detection** uses the canonical snippet documented in `~/.claude/rules/workflow.md` § Base Branch Detection. All workflow skills reference that single source.
- **Verification first** — after every code change, run build + tests and restart the app if applicable. Do not mark a task "done" without passing verification.
- **Plan trust** — when a plan specifies exact files, line numbers, and code changes, skip exploration and implement directly.
- **Commit only when asked** — wait for explicit user confirmation before creating commits, except in worktree agents which auto-commit `wip:` messages before reporting done.

## Subdirectory Init

Subdir `CLAUDE.md` overrides root w/ dir-specific rules. Harness loads on entry into matching tree:

- `claude/skills/CLAUDE.md` — skill authoring conventions (frontmatter shape, `paths:` scoping, `allowed-tools` precision, snippet contracts).
- `claude/agents/CLAUDE.md` — agent authoring conventions (tool allowlist, model selection, `<task-notification>` XML, prompt body shape).
- `claude/hooks/CLAUDE.md` — hook authoring conventions (stdin / stdout JSON contract, exit-code semantics, python3 vs bash, denial-tracker integration).

Each self-contained — no x-ref to root needed.

## Working Surface

Canonical edit surface (new work lands here):

- `claude/skills/<name>/SKILL.md` — new skills (plus supporting files in the same directory).
- `claude/agents/<name>.md` — new agents (single-file markdown with YAML frontmatter).
- `claude/hooks/<name>.{sh,py}` — new hooks (plus any helper modules in the same directory).
- `claude/commands/<name>.md` — new slash-command stubs.
- `claude/rules/<name>.md` — new operational rules.
- `docs-source/<page>.md` — new public-facing documentation pages (rendered to `documentation/<page>.html`).
- `tests/` and `claude/skills/*/tests/` — new tests.

Never edit by hand:

- `documentation/*.html` — auto-rendered from `docs-source/*.md` via `python3 claude/skills/docs-writer/render.py`. Hand-edits are overwritten on the next render.
- `docs/*` — workflow metadata produced by pipeline phases (never committed; managed by skills, not humans).
