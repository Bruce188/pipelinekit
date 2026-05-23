<!-- richness-exempt: codebase reference page — flat table, no interactive surface fits -->

# Codebase Map

The pipelinekit repository top-level layout — one line per directory, one line per significant root file. Cross-linked from the root [CLAUDE.md](../CLAUDE.md).

## Top-Level Directories

| Path | Purpose | Committed? |
|------|---------|------------|
| `claude/` | Workflow toolkit source — skills, agents, hooks, commands, rules, lib, config, memory. | Yes |
| `claude/skills/` | 42 skills authored as `SKILL.md` + supporting files (`tdd`, `pipeline`, `docs-writer`, `review`, `simplify`, ...). | Yes |
| `claude/agents/` | 25 subagent persona definitions (`code-reviewer.md`, `tdd-test-writer.md`, `security-auditor.md`, ...). | Yes |
| `claude/hooks/` | Bash + python pre/post hooks (`validate-commit-msg.sh`, `block-stage-sensitive.sh`, `strip-ai-attribution.sh`, ...). | Yes |
| `claude/commands/` | Slash-command stubs (`/persona`, `/deploy-target`, ...). | Yes |
| `claude/lib/` | Shared helper libraries (`pipeline/`, `sandbox/`, `worker-provider/`). | Yes |
| `claude/rules/` | Operational rules (`workflow.md`, `agents-worktrees.md`). | Yes |
| `claude/model-overlays/` | Per-model behavioural overlays. | Yes |
| `claude/host-adapters/` | Host-shell adapters (`claude.sh`, `codex.sh`, `cursor.sh`, `gemini.sh`). | Yes |
| `claude/config/` | Data files for hooks (e.g., `never-stage.txt`). | Yes |
| `claude/memory/` | Memory index (`MEMORY.md`) for project memory layer. | Yes |
| `claude/tresor-resources/` | Vendored prompt templates and reference standards. | Yes |
| `scripts/` | `install.sh`, sandbox helpers, cloud bootstrap, repo-wide smoke / verification scripts. | Yes |
| `docs-source/` | Markdown sources for `documentation/*.html`. Rendered via `python3 claude/skills/docs-writer/render.py`. | Yes |
| `documentation/` | Rendered HTML application documentation. Reader-facing pages. | Yes (HTML only) |
| `docs/` | Workflow metadata (`analysis-v*`, `plan-v*`, `progress.md`, `pipeline-state.md`, `review-v*`, ...). | NO — never committed (gitignored / hook-blocked) |
| `tests/` | Repo-wide smoke + integration tests. | Yes |
| `lancedb/` | Local RAG index storage. | NO — runtime state |

## Root Files

| File | Purpose | Committed? |
|------|---------|------------|
| `CLAUDE.md` | Project-root context file. Loaded by every Claude Code session in this repo. Additive to `~/.claude/CLAUDE.md`. | Yes |
| `README.md` | Top-level repo README (user-facing install + feature summary). | Yes |
| `LICENSE` | MIT license. | Yes |
| `.gitignore` | Standard git ignore rules. | Yes |
| `.mcp.json` | MCP server configuration (LSP-backed serena recommendation; see `documentation/mcp-lsp-setup.html`). | Yes |
| `.mcp.json.template` | MCP server config template (copy to `.mcp.json` to opt in). | Yes (template only) |
| `.worktreeinclude.template` | Worktree env-handoff template (copy to `.worktreeinclude` per repo). | Yes (template only) |
| `.devcontainer/` | Devcontainer config for Codespaces / VSCode dev containers. | Yes |
| `.env` | Local environment variables (secrets). | NO — gitignored |

## Workflow vs Application Documentation

- `docs/` — workflow metadata: analyses, plans, prompts, reviews, progress, pipeline state. Pattern: `docs/<type>-v<N>.md`. Pipeline-managed; NEVER committed. Enforced by `claude/hooks/block-stage-sensitive.sh` reading `claude/config/never-stage.txt`.
- `documentation/` — application documentation: reader-facing HTML pages. Committed. Source lives in `docs-source/*.md`; HTML is rendered via `python3 claude/skills/docs-writer/render.py <input.md> <output.html>`.

## Where New Work Lands

See root [CLAUDE.md § Working Surface](../CLAUDE.md#working-surface) for the canonical edit-surface list.

## Skills, Agents, Hooks — quick pointers

- Full skills catalog: [skills.html](skills.html).
- Full agents catalog: [agents.html](agents.html).
- Hook authoring conventions: forthcoming `claude/hooks/CLAUDE.md`.
