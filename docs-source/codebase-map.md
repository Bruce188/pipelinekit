<!--
diataxis: reference
-->
# Codebase Map

The pipelinekit repository top-level layout — one line per directory, one line per significant root file. Cross-linked from the root [CLAUDE.md](../CLAUDE.md).

The directory tree below renders that layout spatially: solid `var(--accent)` nodes are committed, dashed `var(--fg-subtle)` nodes (`docs/`, `lancedb/`) are never committed.

<svg viewBox="0 0 700 560" role="img" aria-label="Directory tree of the pipelinekit top-level repository layout" style="width:100%;height:auto;font-family:var(--mono);">
  <title>pipelinekit top-level directory tree</title>
  <g stroke="var(--border)" stroke-width="1.5" fill="none">
    <line x1="40" y1="56" x2="40" y2="492"></line>
    <line x1="40" y1="92" x2="64" y2="92"></line>
    <line x1="40" y1="320" x2="64" y2="320"></line>
    <line x1="40" y1="352" x2="64" y2="352"></line>
    <line x1="40" y1="384" x2="64" y2="384"></line>
    <line x1="40" y1="416" x2="64" y2="416"></line>
    <line x1="40" y1="448" x2="64" y2="448"></line>
    <line x1="40" y1="480" x2="64" y2="480"></line>
    <line x1="120" y1="104" x2="120" y2="288"></line>
    <line x1="120" y1="124" x2="144" y2="124"></line>
    <line x1="120" y1="148" x2="144" y2="148"></line>
    <line x1="120" y1="172" x2="144" y2="172"></line>
    <line x1="120" y1="196" x2="144" y2="196"></line>
    <line x1="120" y1="220" x2="144" y2="220"></line>
    <line x1="120" y1="244" x2="144" y2="244"></line>
    <line x1="120" y1="268" x2="144" y2="268"></line>
    <line x1="120" y1="288" x2="144" y2="288"></line>
  </g>
  <text x="20" y="40" fill="var(--fg)" font-size="15" font-weight="600">pipelinekit/</text>
  <text x="68" y="96" fill="var(--accent)" font-size="14" font-weight="600">claude/</text>
  <g font-size="12.5" fill="var(--accent)">
    <text x="148" y="128">skills/</text>
    <text x="148" y="152">agents/</text>
    <text x="148" y="176">hooks/</text>
    <text x="148" y="200">commands/</text>
    <text x="148" y="224">lib/</text>
    <text x="148" y="248">rules/</text>
    <text x="148" y="272">config/</text>
    <text x="148" y="292">memory/</text>
  </g>
  <text x="240" y="292" fill="var(--fg-subtle)" font-size="11">…model-overlays/ host-adapters/ tresor-resources/</text>
  <g font-size="14" fill="var(--accent)">
    <text x="68" y="324">scripts/</text>
    <text x="68" y="356">docs-source/</text>
    <text x="68" y="388">documentation/</text>
    <text x="68" y="452">tests/</text>
  </g>
  <text x="68" y="420" fill="var(--fg-subtle)" font-size="14">docs/</text>
  <line x1="68" y1="424" x2="104" y2="424" stroke="var(--fg-subtle)" stroke-width="1.2" stroke-dasharray="4 3"></line>
  <text x="68" y="484" fill="var(--fg-subtle)" font-size="14">lancedb/</text>
  <line x1="68" y1="488" x2="120" y2="488" stroke="var(--fg-subtle)" stroke-width="1.2" stroke-dasharray="4 3"></line>
  <g font-size="12">
    <rect x="360" y="510" width="14" height="12" fill="var(--accent)" rx="2"></rect>
    <text x="380" y="520" fill="var(--fg-muted)" font-family="var(--sans)">committed</text>
    <line x1="500" y1="516" x2="528" y2="516" stroke="var(--fg-subtle)" stroke-width="1.5" stroke-dasharray="4 3"></line>
    <text x="534" y="520" fill="var(--fg-muted)" font-family="var(--sans)">never committed</text>
  </g>
</svg>

<details>
<summary>Why <code>docs/</code> and <code>lancedb/</code> are never committed (click to expand)</summary>

The two dashed nodes in the tree above are runtime / workflow state, deliberately kept out of version control:

- **`docs/`** holds pipeline workflow metadata — `analysis-v*.md`, `plan-v*.md`, `progress.md`, `pipeline-state.md`, `review-v*.md`. It is pipeline-managed and never staged. Enforcement is two-layer: a `.gitignore` rule plus `claude/hooks/block-stage-sensitive.sh`, which reads the patterns in `claude/config/never-stage.txt` and refuses any `git add` that matches.
- **`lancedb/`** is the on-disk index for the local-RAG MCP. It is regenerated from source on demand, so committing it would only bloat history with machine-specific binary state.

Every other node renders solid `var(--accent)` because it is part of the committed toolkit surface.

</details>

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

## Default MCP stack

pipelinekit ships four memory + graph tools enabled by default after `scripts/install.sh` provisioning: **agentmemory** (canonical memory store via MCP), **Understand-Anything** (interactive UI plugin), **codegraph** (symbolic code graph via MCP), **graphify** (knowledge graph via MCP). All four are configured per project via `/codegraph-init` and `/graphify-init` slash commands (agentmemory + Understand-Anything need no per-project setup). Cumulative RSS ceiling is governed by the F6 `claude/hooks/mcp-rss-cap.sh` cap (default `PIPELINE_MAX_MCP_RSS_MB=800`); F7's `claude/hooks/tests/test_wsl2_multi_daemon_ram_budget.sh` enforces the same in CI. See [memory-graph-stack.html](memory-graph-stack.html) for the full integration shape, RAM budget, embedding-provider matrix, and troubleshooting flow.

## Where New Work Lands

See root [CLAUDE.md § Working Surface](../CLAUDE.md#working-surface) for the canonical edit-surface list.

## Skills, Agents, Hooks — quick pointers

- Full skills catalog: [skills.html](skills.html).
- Full agents catalog: [agents.html](agents.html).
- Hook authoring conventions: forthcoming `claude/hooks/CLAUDE.md`.
