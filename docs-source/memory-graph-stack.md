# Memory + Graph Stack

pipelinekit ships four tools that together form the default memory and graph surface: **agentmemory**, **Understand-Anything**, **codegraph**, and **graphify**. Each tool answers a distinct question class; none is redundant with the others. This page documents what each tool does, how they compose during a session, the WSL2 RAM budget you should plan around, the embedding-provider fallback chain, and the first-run setup steps for a new project.

## What's in the stack

<div data-snippet="comparison-tabs"></div>

**agentmemory** is the canonical memory store for pipelinekit sessions. It replaces the legacy flat-file markdown store (`~/.claude/projects/<slug>/memory/*.md`) as the primary write and read surface. Upstream: [https://github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory). In pipelinekit, agentmemory is provisioned at install time by `scripts/install.sh` and wired into every project's `.mcp.json` automatically. Claude writes memories through `memory_save` and retrieves them through `memory_recall` or `memory_smart_search`; Ebbinghaus-curve recency weighting is handled by the MCP server, not by Claude. The question agentmemory answers is: "what have I learned across sessions about this project and this user?"

**Understand-Anything** is the interactive UI plugin for tool and memory inspection. It is NOT an MCP server — it is installed as a plugin via the harness plugin marketplace at `scripts/install.sh` provisioning time. Upstream: [https://github.com/Lum1104/Understand-Anything](https://github.com/Lum1104/Understand-Anything). In pipelinekit, Understand-Anything provides a visual annotation surface where you can inspect tool calls, memory entries, and graph outputs without parsing raw JSON. The question Understand-Anything answers is: "show me a visual annotation of what the stack is doing and what it knows."

**codegraph** is the symbolic code graph MCP. It builds and serves a persistent graph of function definitions, call sites, and import edges from your project source, stored in `.codegraph/codegraph.db` per project. Upstream: [https://github.com/colbymchenry/codegraph](https://github.com/colbymchenry/codegraph). In pipelinekit, codegraph is provisioned per project via the `/codegraph-init` slash command (which handles the 50k-file pre-flight gate and launches the daemon). The question codegraph answers is: "where does this symbol live, and who calls it?"

**graphify** is the knowledge graph MCP. It extracts named entities (people, tools, concepts, plans, decisions) and their relationships from project artifacts — markdown, code, docs — and stores the result in `.graphify/` per project. Upstream: [https://github.com/safishamsi/graphify](https://github.com/safishamsi/graphify). In pipelinekit, graphify is provisioned per project via `/graphify-init` (same 50k-file gate and daemon pattern). The question graphify answers is: "what entities and relationships are relevant to this concept, and how do they connect?"

> See also the **Claude Code Environment Defaults** section of `claude/CLAUDE.md.template` for the env-var pin (`CLAUDE_CODE_DISABLE_1M_CONTEXT=1`) that interacts with prompt-cache behavior at the 200K boundary.

## How they compose

The four tools form a layered retrieval stack. When Claude needs to reason about a project at session start, the retrieval chain moves from cheapest to richest: agentmemory supplies the cross-session learned context first (fast, already indexed, Ebbinghaus-ranked by recency), then codegraph fills in the structural code surface (where symbols live, what calls what), then graphify adds the semantic relationship layer (how concepts and decisions connect), and Understand-Anything sits above all three as the human-readable inspection surface.

Each layer answers a different question class. Memory answers "what have I learned?", codegraph answers "where does this live?", graphify answers "what is related to this?", and Understand-Anything answers "show me a view I can read and annotate." This decomposition avoids conflating retrieval concerns: you don't want a code-graph query polluted by semantic prose, and you don't want a memory recall to return raw AST edges.

The composition becomes most visible during a pipeline analyze phase. The `/analyze` skill first issues `memory_smart_search` to pull prior project context from agentmemory, then queries codegraph for the file-system and symbol layout of the modules under analysis, then queries graphify for entity relationships between the subsystems named in the charter. By the time the analysis prompt is assembled, it carries three orthogonal slices of project knowledge — learned history, structural code shape, and concept topology — without any one tool having to approximate the others.

Outside the pipeline, the stack works on-demand: if you ask "who calls `execute_order` and what decisions led to its current signature?", the assistant routes the first part to codegraph (call graph traversal) and the second to graphify (entity extraction over commit messages and design docs). Understand-Anything lets you inspect both results side by side with inline annotations. The round-trip from question to annotated visual is a single session turn.

The stack is additive by design. You can disable any single tool (see `PIPELINE_DISABLE_*` env vars below) without breaking the others. Sessions that disable codegraph degrade gracefully to grep-based symbol lookup; sessions that disable graphify omit the entity-relationship layer but retain full memory and code-graph coverage. This means you can tune the stack to your host's RAM budget without restructuring the workflow. On a 4 GB WSL2 allocation, running only agentmemory (the lightest daemon) and disabling codegraph and graphify keeps cumulative RSS well under 300 MB while preserving cross-session learned context — the highest-value retrieval tier for most day-to-day sessions.

Understand-Anything is the one tool in the stack that runs zero background memory: it is a plugin, not a daemon, and its RSS footprint is zero between activations. This makes it free to keep enabled at all times regardless of host memory constraints. Use it whenever you want a human-readable annotated view of tool outputs — especially useful when debugging why a memory recall returned unexpected results, or when validating that graphify extracted the right entity set from a new design document.

## WSL2 RAM budget

The three MCP daemons (agentmemory, codegraph, graphify) run as persistent background processes. Each daemon holds an in-process sqlite database plus an embedding cache. Sustained RSS per daemon is roughly 150–200 MB (measured on the pipelinekit 200-file fixture in `claude/hooks/tests/test_wsl2_multi_daemon_ram_budget.sh`; the test asserts a hard ceiling of 900 000 KB ≈ 879 MB across all three daemons combined — your repo's working-set will vary).

| Component | Sustained RSS | Notes |
|-----------|---------------|-------|
| agentmemory daemon | ~150–200 MB | per-project sqlite + embedding cache (Voyage / OpenAI / local-ONNX-quant) |
| codegraph daemon | ~150–200 MB | `.codegraph/codegraph.db` per project |
| graphify daemon | ~150–200 MB | `.graphify/` per project |
| **Cumulative ceiling** | **~800 MB** | Default `PIPELINE_MAX_MCP_RSS_MB=800` cap |

The ~800 MB ceiling corresponds to the default `PIPELINE_MAX_MCP_RSS_MB=800` enforced by the F6 cap-warning hook at `claude/hooks/mcp-rss-cap.sh`. Override it per-session by exporting the env var before launching the harness.

If you are on a WSL2 host with a tight memory limit, you can selectively disable individual daemons without touching the others:

- `PIPELINE_DISABLE_AGENTMEMORY=1` — skip agentmemory MCP launch; session falls back to flat-file memory reads.
- `PIPELINE_DISABLE_CODEGRAPH=1` — skip codegraph daemon; symbol-graph queries degrade to grep-based fallback.
- `PIPELINE_DISABLE_GRAPHIFY=1` — skip graphify daemon; entity-graph queries are omitted entirely.

All three env vars are honored by the F6 hook at `claude/hooks/mcp-rss-cap.sh`.

## Embedding-provider matrix

agentmemory uses embedding vectors for semantic retrieval. The embedding provider is selected at daemon launch via a fallback chain inspecting env vars in this order:

| Env var | Provider | Quality | Cost |
|---------|----------|---------|------|
| `VOYAGE_API_KEY` (set) | Voyage `voyage-3` | Best | $$ |
| `OPENAI_API_KEY` (set, no Voyage) | OpenAI `text-embedding-3-small` | Good | $ |
| (neither set) | local-onnx-quant | Acceptable | Free |

The resolution chain lives in `scripts/install.sh § provision_agentmemory_mcp` (lines 488–494). When neither key is present, agentmemory falls back to a quantized local ONNX model bundled at install time. Retrieval quality is acceptable for most projects at this tier but noticeably weaker on large multi-module codebases where cross-session recall relies on nuanced semantic distance. The warning `agentmemory: no VOYAGE_API_KEY or OPENAI_API_KEY found — falling back to local-onnx-quant` fires at daemon startup on this fallback path. Setting either key in your `.env` and re-running `scripts/install.sh` upgrades the provider without re-running `/codegraph-init` or `/graphify-init`.

## First-run setup per project

<div data-snippet="terminal-simulator"></div>

The four tools have different per-project setup requirements:

1. **agentmemory** — no per-project setup. The daemon is auto-provisioned by `scripts/install.sh` at install time and wired into the global MCP configuration. Every new project inherits it automatically.

2. **Understand-Anything** — no per-project setup. It is installed as a harness plugin at `scripts/install.sh` provisioning time and is available globally from the first session.

3. **codegraph** — run `/codegraph-init` once per project. The command runs a pre-flight gate that refuses initialization on repositories with more than 50 000 files (to prevent runaway indexing on monorepos). If your project is legitimately above that threshold, pass `--force` to bypass the gate. After `/codegraph-init` completes, the codegraph daemon starts automatically and remains persistent; subsequent sessions reconnect to the existing `.codegraph/codegraph.db`.

4. **graphify** — run `/graphify-init` once per project. The same 50 000-file pre-flight gate applies, and the same `--force` override is available. After initialization, the graphify daemon runs persistently against `.graphify/` in the project root.

**Important: DO NOT run `agentmemory connect`.** The upstream `agentmemory connect` command writes `SessionStart`, `SessionStop`, and `PostToolUse` hooks into the harness hook configuration. These hooks collide with pipelinekit's own `claude/hooks/memory-journal.sh` and `claude/hooks/session-start-context.sh`, and they recreate the `vmmemWSL` RSS spike vector that PR #117 removed. agentmemory in pipelinekit is wired exclusively via `.mcp.json` (provisioned by `scripts/install.sh`) — the upstream `connect` command is NOT used and must not be run.

## Troubleshooting

To identify which daemon is consuming excess memory, list the running daemon PIDs and inspect their RSS:

```bash
ps -ef | grep -E '(agentmemory|codegraph|graphify)' | awk '{print $1,$2,$NF}'
```

Then for each PID of interest:

```bash
pmap -x <PID> | tail -1
```

The final line from `pmap -x` shows total RSS in KB. If a single daemon exceeds 200–250 MB sustained, something is holding the embedding cache open beyond its normal working set — most commonly a background consolidation job left running. Kill the daemon and let the MCP server restart it on the next tool call.

To disable a daemon immediately:

```bash
export PIPELINE_DISABLE_AGENTMEMORY=1   # or CODEGRAPH / GRAPHIFY
# restart the harness session
```

The F6 hook at `claude/hooks/mcp-rss-cap.sh` checks all three env vars at hook-fire time and skips the RSS threshold warning for any disabled daemon.

<details>
<summary>What if `mcp-rss-cap.sh` keeps warning even after I export `PIPELINE_DISABLE_*`?</summary>

The hook reads env vars at the moment the hook fires. If you exported the var in the current shell but did not restart the harness session (which spawns a fresh child process), the hook's environment may not have inherited the export. Restart the session after exporting.

If warnings persist after a session restart, check that you exported the var in the shell that launches `claude` (not a sibling terminal). The hook log is at `~/.claude/hook-logs/mcp-rss-cap.log` — look for the most recent `[rss-cap]` lines to see which daemon triggered the warning and what RSS value was observed.

The canonical RAM-budget assertion is `claude/hooks/tests/test_wsl2_multi_daemon_ram_budget.sh`, which fires in CI against the pipelinekit 200-file fixture and hard-asserts the 900 000 KB ceiling. If your observed RSS exceeds this threshold on the same fixture, open an issue with the `pmap -x` output for each daemon.

</details>

## See also

- [memory-migration-notes.html](memory-migration-notes.html) — F8 migration mechanics: flat-file to agentmemory, migration script usage, dual-write opt-in, rollback window.
- [installation.html](installation.html) — install pipelinekit locally, via Codespaces, devcontainer, or cloud bootstrap.
- [mcp-lsp-setup.html](mcp-lsp-setup.html) — symbol-level Go-to-Definition via the serena MCP (companion code-navigation stack).
