---
description: Detailed workflow conventions — plan management, versioning, directory structure, context-aware clearing, base-branch detection. Loads only in projects with workflow structure.
paths:
  - "**/docs/**"
  - "**/.claude/**"
---

# Workflow Operational Details

> Detailed conventions for plan management, directory structure, RAG, and project startup.
> Core principles stay in ~/.claude/CLAUDE.md. This file covers operational details.

## Global Argument Convention

Pipeline skills accept optional `--` arguments that modify their behavior. Arguments are passed after the command (e.g., `/review --scope 2.3`).

| Argument | Available on | Behavior |
|----------|-------------|----------|
| `--scope` | `/review` | Target review to a task ID (`--scope 2.3`) or path (`--scope src/auth/`) |
| `--no-parallel` | `/implement-plan` | Force sequential execution, skip parallel detection |
| `--health` | `/review` | Run quick code-health assessment, include score in report |
| `--renew` | `/pipeline` | Regenerate feature file from deferred items + failed features, then process |
| `--force` | `/review` | Override review cycle cap (manual use only — never passed by pipeline) |
| `--teams` | `/review` | Enable Agent Teams mode — review agents communicate during execution (auto-enables `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` if not set) |
| `--max-usd` | `/pipeline` | Hard cap on cumulative USD across the run. Default: unlimited (flag omitted → no budget check). Halts at phase boundaries when next phase would exceed cap. |
| `--max-turns` | `/pipeline` | Hard cap on accumulated sub-agent turns. Default: unlimited. Halts at phase boundaries when next phase would exceed cap. |
| `--from` | `/pipeline` | Free-text context for feature-file auto-generation. Step 1.5 uses it alongside analysis/PRP/deferred items. Mutually exclusive with `--adopt` and `--renew`. |
| `--plan` | `/pipeline` | Path to a plan-mode markdown file (typically `~/.claude/plans/<slug>.md`). Without a path, auto-picks the most-recently-modified file in `~/.claude/plans/` within the last 60 min. Pipeline ingests via an in-process Agent dispatch and writes `docs/features.md`. Mutually exclusive with `--from`, `--adopt`, `--renew`, and a positional feature file. 200 KB cap. |
| `--teams` | `/pipeline` | Force `always teams` for this run — orchestrator dispatches `/review --teams` at every review boundary regardless of heuristic or persisted `**Review style:**`. Distinct from `/review --teams` (inner-skill flag); both still exist. Mutually exclusive with `--no-teams`. |
| `--no-teams` | `/pipeline` | Force `never teams` for this run — orchestrator dispatches plain `/review` at every review boundary, suppressing the heuristic and the persisted `**Review style:**`. Mutually exclusive with `--teams`. |

**Note:** `/code-health` has its own arguments (`--scope`, `--quick`, `--threshold`) — it sits outside the main pipeline. Its `--scope` scopes quality dimensions, not file paths.

### --scope

When `--scope` is present on `/review`:
1. If value matches task ID pattern (e.g., `2.3`): look up task files in plan, scope git diff to those files
2. If value is a path: scope git diff to that path

Default (no --scope): auto-detect from reopened tasks (review Step 3.5). If no reopened tasks exist: full diff.

### --no-parallel

When `--no-parallel` is present on `/implement-plan`:
1. Skip parallel detection entirely
2. Execute all tasks sequentially (Step 2 of implement-plan)
3. Use when: worktree issues, debugging, or tasks with implicit dependencies not captured in the plan

**Default behavior (no --no-parallel):** `/implement-plan` automatically attempts parallel execution for phases with multiple tasks that have zero file overlap. Falls back to sequential if tasks share files or have noted dependencies.

## Project Startup

**New project:**
1. Scaffold + `.claude/CLAUDE.md` + `.gitignore`. Claude exclusions → `.git/info/exclude`.
   - **Base branch init:** If no git repo exists: `git init && git checkout -b main && git commit --allow-empty -m "init: empty base"`. If a repo exists but has no `main` or `master` branch and no remote: `git branch main $(git rev-list --max-parents=0 HEAD | tail -1)` to create `main` at the first commit. Feature branches are created later by `/new-branch`.
2. Check tools: `~/.claude/skills/`, `~/.claude/agents/`, MCPs. Ask about tool libraries (`~/claude-library/`, `~/claude-skills/`, `~/.claude/tresor-resources/`).
3. Run `/pipeline` and step through Charter Discovery (Step 0) to capture requirements as `docs/charter.md`. (Legacy `/interview-prp` is deprecated but still installed for one release.)

**Existing project / defined task — pre-check:**
Before running `/analyze`, verify a base branch exists using the Base Branch Detection snippet (see § Base Branch Detection below). If detection fails and there's no remote, prompt the user to create one: `git branch main <first-commit-hash>`. This prevents `/review` from blocking later in the pipeline.

**Resuming:** Read `docs/progress.md` first → current plan + current task → read the plan and task prompt.

## Directory Convention

- **`docs/`** — AI workflow files only: progress.md, plan.md, prompts.md, analysis.md, prp.md, review, pipeline-state.md, pipeline-intel.json, .last-verify.json. NOT committed — individual patterns are listed in `~/.claude/config/never-stage.txt`, and enforced by `block-stage-sensitive.sh`. New workflow files added to `docs/` must also be added to both the canonical list and the hook.
  - **`docs/archive/`** — Rotated iteration Status tables produced by `/create-plan`. Treated as workflow metadata: never committed, excluded via `~/.git/info/exclude` and `never-stage.txt`.
- **`documentation/`** — Application documentation: API refs, user guides, architecture docs. IS committed.

## Plan & Progress

- **Versioning:** Plan and prompts files follow the **Versioning Convention** below.
- **progress.md is history-preserving:** Completed (`done`) tasks are never removed. Superseded `todo`/`doing` tasks may be replaced when a new plan is created. New tasks are appended. Superseded iteration Status tables are rotated to `docs/archive/progress-v<N>.md` by `/create-plan` — see that skill's Step 5.
- **Task reopening:** `/review` can set completed tasks back to `todo` with note `reopened: review-vN`. `/implement-plan` reads the referenced review file for guidance on what to fix. New micro-tasks may be created if findings don't map to existing tasks.
- **Pointer system:** `progress.md` has `**Plan:**`, `**Prompts:**`, and `**Charter:**` fields pointing to the active files. All reader skills (`/implement-plan`, `/review`, `/ppr`) follow these pointers — never hardcode `docs/plan.md`.
- **Charter pointer:** `progress.md` has a `**Charter:**` field. `/pipeline` Step 0 writes this pointer when it creates or adopts a charter. Downstream phases read it to locate `docs/charter.md`.
- **Analysis pointer:** `progress.md` has an `**Analysis:**` field. `/analyze` updates it. `/create-plan` follows it instead of hardcoding `analysis.md`.
- **Review pointer:** `progress.md` has a `**Review:**` field. `/review` updates it when saving findings. `/implement-plan` follows it when re-executing reopened tasks.
- **analysis.md:** Follows the **Versioning Convention** below. Pointer in progress.md tracks current file.
- **prp.md:** User is asked before overwriting an existing PRP.
- **Never stage:** See `~/.claude/config/never-stage.txt` — the hook `block-stage-sensitive.sh` reads the same file.
- Use `git log`/`git diff` for recent changes — don't duplicate in progress.md.

## Versioning Convention

All versioned workflow files (plan, prompts, analysis, review, charter) follow the same archiving convention:

1. Check for existing files: `ls docs/<type>*.md`
2. Find highest version N among `docs/<type>-v*.md` files (if none, N = 0)
3. If unversioned `docs/<type>.md` exists: archive it as `docs/<type>-v[N+1].md` (consumes slot N+1)
4. Write new file as `docs/<type>-v[N+2].md` (or `docs/<type>-v[N+1].md` if no unversioned file was archived)
5. First-time files: write as `docs/<type>.md` (no version suffix)

Skills reference this convention rather than duplicating the logic.

## Context-Aware Clearing

Not all pipeline transitions need `/clear`. Use the right tool for each transition:

| From | To | Action | Reason |
|------|----|--------|--------|
| `/pipeline` Step 0 | `/create-plan` | `/compact` | Charter Discovery output is the input — keep in context |
| `/interview-prp` (deprecated) | `/create-plan` | `/compact` | Legacy PRP path — use `/pipeline` Step 0 going forward |
| `/analyze` | `/create-plan` | `/compact` | Analysis output is the input — keep in context |
| `/create-plan` | `/new-branch` | (none) | Trivial operation, context still relevant |
| `/new-branch` | `/implement-plan` | `/clear` | Fresh context for implementation, plan is on disk |
| `/implement-plan` | `/review` | `/clear` | Fresh context prevents bias toward own code |
| `/review` (pass) | `/ppr` | `/compact` | Lightweight transition; preserves session continuity |
| `/review` (findings) | `/implement-plan` | `/clear` | Fresh context for fix implementation |
| `/review` (scope change) | `/create-plan` | `/clear` | Re-planning needs fresh context |
| `/create-plan` (re-plan) | `/implement-plan` | `/clear` | Same as initial plan→implement; branch already exists, skip `/new-branch` |
| `/ppr` | `/post-merge` | (none) | Trivial cleanup |
| `/post-merge` | next task | `/clear` | Full reset for new work |
| `/pipeline` phase→phase (subagent mode) | any | Agent dispatch | Replaces `/compact` with true context isolation |

**Manual changes between steps:** If you make manual edits after `/implement-plan`, commit them before running `/review`:
```bash
git add <files> && git commit -m "fix: <description>"
```
`/review` only analyzes committed changes (`git diff $BASE...HEAD`). Uncommitted edits will be invisible to review and will block `/ppr`.

## Deferred Items

`progress.md` has a `## Deferred` section for work that is explicitly postponed (not abandoned):

```
## Deferred
| Item | Source | Reason | Target Iteration |
|------|--------|--------|-----------------|
| Feature X | plan-v1.md | Needs dedicated iteration | Next |
```

- `/create-plan` reads deferred items and asks whether to include any in the new plan
- Items included in the new plan are removed from Deferred
- Items that remain deferred are preserved
- New deferrals from the current plan are added

## Review Files

Review findings follow the **Versioning Convention** above.
- `progress.md` has a `**Review:**` pointer to the current review file
- Review files include: each finding, which task it relates to, severity (blocking/non-blocking)
- `/review` saves findings AND reopens tasks in progress.md
- `/implement-plan` reads the review file when executing reopened tasks

## Base Branch Detection

All skills that need the base branch (e.g., `/review`, `/post-merge`, `/ppr`) use this standard snippet:

```bash
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
[ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}')
[ -z "$BASE" ] && BASE="main"
git rev-parse --verify "$BASE" 2>/dev/null || echo "ERROR: Base branch '$BASE' not found locally."
```

If this snippet needs updating, change it here — all skills reference this section.

## Pipeline State Schema

`docs/pipeline-state.md` is the per-run state file written by `/pipeline`. Fields (all written by Step 5.1 unless noted):

- `**Feature file:**` — path to the feature file being processed
- `**Feature:**` — `<index> / <total>` (1-based)
- `**Name:**` — current feature H2 header (`<type>/<name>`)
- `**Step:**` — current phase (`analyze` | `plan` | `implement` | `review`)
- `**Review cycles:**` — integer, incremented on each Path B iteration
- `**Replan count:**` — integer, incremented on each Path C iteration
- `**Started:**` — pipeline start timestamp
- `**Max USD:**` — hard cap for cumulative cost across the run (from `--max-usd`). Value is `unlimited` when the flag was omitted; the budget check treats `unlimited` as a no-op.
- `**Max turns:**` — hard cap for accumulated sub-agent turns (from `--max-turns`). Value is `unlimited` when the flag was omitted.
- `**Phase Mode:**` `subagent` | `inline` (legacy/Path N) — set per-feature at Step 5.0. New features always start as `subagent`. `inline` appears only in (a) legacy state files written under the prior heuristic policy, or (b) Path N nit-attack sub-paths (Edit-tool only). See § Phase Mode Precedence below.
- `**Last phase agent:**` subagent ID of the most recently dispatched phase — present whenever the phase ran via the `Agent` tool. Omitted only when the phase ran inline (Path N nit-attack).
- `**Feature class:**` `dev` | `non-dev` — set per-feature at Step 5.5.0. Drives TDD routing: `dev` features dispatch a tdd-test-writer + tdd-implementer pair per task; `non-dev` features use the standard implement-plan dispatch.
- `**Charter:**` path to the active charter file (e.g., `docs/charter.md`), or `(none)` when `--no-charter` is in effect. Written by Step 5.1 from the resolved charter path. Step 3 (resume) reads and preserves this field; if it points to a valid file, Step 0 is not re-run.
- `**Review style:**` `always teams` | `never teams` | `orchestrator decides` — per-feature preference deciding whether `/review` is dispatched with `--teams`. Written by Step 5.1 in priority order: (1) `--teams` / `--no-teams` session override, (2) Charter Topic 11 answer if charter exists, (3) default `orchestrator decides`. When `orchestrator decides`, Step 5.6.0 applies the heuristic: `DIFF_LINES > 500 OR DIFF_FILES > 8 OR feature_class = dev → --teams`. Sticky for the duration of a feature.
- `**Prior finding count:**` total findings (blocking + non-blocking) from previous review cycle — used by Path B convergence heuristic
- `**Non-converging cycles:**` consecutive cycles where finding count did not decrease — retained for observability only; Path B no longer halts on this counter (bounded solely by the 5-cycle hard cap, after which Path C escalation fires)
- `**Conv guard logged:**` 0 or 1 — set to 1 the first time `CONVERGENCE_GUARD_DISABLED` is emitted for this feature. Persisted to disk so pipeline resumes do not re-emit the log line. Cleared to 0 at feature init; not reset by `path_c_replan`.

## Phase Mode Precedence

The pipeline selects `subagent` as the phase mode at every feature-loop entry. There is no surface-area heuristic. A mode-drift incident exposed the underlying bug: a `subagent`-mode feature was dropping to inline post-review because Path B did not honor the recorded `**Phase Mode:**`. The Path B fix (read-fresh + Agent dispatch) closes the drift; the DESC_LEN/HAS_CONSTRAINTS/HAS_AC heuristic was removed alongside it because once Path B always dispatches as `subagent`, every feature ends up `subagent` regardless of surface area, making the heuristic dead policy.

| Stage | Mode |
|-------|------|
| Feature start (Step 5.0) | `subagent` — always, unconditional |
| Path B re-implement / re-review | `subagent` — Path B reads `**Phase Mode:**` fresh and dispatches via Agent tool |
| Path C re-plan / re-implement / re-review | `subagent` — same as Path B |
| Path N (nit-only post-review) | `inline` — the ONLY legitimate inline-dispatch path; max 2 cycles, Edit-tool only |
| Optional Row-2 nit preamble (`PIPELINE_NIT_FIRST=1`) | `inline` — runs Path N body before falling through to Path B subagent dispatch |

**On resume:** Preserve the saved `**Phase Mode:**` from `docs/pipeline-state.md`. Never silently downgrade `subagent` → `inline`. Direct invocation of `Skill: implement-plan` or `Skill: review` on a `subagent`-mode resume is a contract violation — see SKILL.md Step 3 § "Phase Mode preservation contract".

**Legacy state files:** A resumed state file recording `**Phase Mode:** inline` (written under the prior heuristic) is preserved for the in-flight feature only. New features added after a legacy resume dispatch via `subagent`. Pipeline logs `LEGACY_PHASE_MODE: inline mode preserved for in-flight feature; new features dispatch via subagent` once per resume.

Mode is recorded in `docs/pipeline-state.md` at Step 5.1 per-feature.

## Pipeline Entry Point

`/pipeline` (Skill — in-process) is the only entry point in the portable build. It runs all phases inside a single Claude Code session. Phase Mode is always `subagent` for new features (Agent-tool dispatch per phase) — there is no surface-area heuristic. Path N nit-attack sub-paths run inline by design (Edit-tool only, max 2 cycles).

An out-of-process subprocess driver is intentionally not shipped. If you need a long unattended run outside an interactive Claude session, fork and add your own driver — the per-phase prompt templates in `~/.claude/skills/pipeline/reference.md` are the contract a driver must implement.

---

## MCP Constraints

**Global servers** (in `~/.claude.json` — available to all projects):
- **context7:** Library/framework documentation lookup. Universally useful.
- **local-rag:** Niche API docs only (exchange APIs in `~/exchange-docs/`). Don't RAG standard frameworks.

**Per-project servers** (add to `.mcp.json` in project root where needed):
- **sequential-thinking:** Deep reasoning chains. Add when tasks require multi-step logic.
- **RepoMapper:** Structural code patterns, class hierarchies, call graphs. Add for large codebases.
- **voicemode:** Push-to-talk voice interaction via `converse` tool.
- **claude-context:** Codebase semantic RAG via `@zilliztech/claude-context` (community MCP — NOT Anthropic). AST-aware chunking + Merkle-tree incremental indexing; complements serena (LSP/symbolic navigation) by providing semantic retrieval against natural-language objectives. Opt-in via `CLAUDE_INSTALL_OPTIONALS=claude-context`. `/analyze` Step 3.6 skips semantic retrieval below 50000 LOC. local-mode (Ollama / Transformers embedding, no Milvus account) and cloud-mode (Milvus / Zilliz creds via `MILVUS_ADDRESS` / `MILVUS_TOKEN`) both supported — env-var skeleton lives in `.mcp.json.template` `_optional_claude_context_mcpServers`. Upstream benchmark: <5s per `git pull` for incremental Merkle-tree re-indexing (benchmark, not a guarantee).

Example `.mcp.json` for a project needing RepoMapper:
```json
{
  "mcpServers": {
    "RepoMapper": {
      "type": "stdio",
      "command": "~/.local/share/mcp-servers/RepoMapper/.venv/bin/python",
      "args": ["~/.local/share/mcp-servers/RepoMapper/repomap_server.py"]
    }
  }
}
```

**Other MCP servers** (configured per-project as needed):
- **Gmail:** Can search/read/draft but **cannot send**. Draft only.
- **Google Calendar:** Full CRUD.

## Phase Tool Routing

Compact routing table for each pipeline phase. Native tools (Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch) are in each SKILL.md `allowed-tools` — not repeated here. MCPs listed are available when configured; skills auto-detect availability at runtime.

| Phase | MCPs | Agent Types | Sub-Skills | Memory Reads | Hooks | WorkerProvider |
|-------|------|-------------|------------|--------------|-------|----------------|
| `/interview-prp` (DEPRECATED — use `/pipeline` Step 0) | — | — | — | `user_profile.md` | block-stage-sensitive, block-dangerous-commands | — |
| `/analyze` | context7 (resolve + query), local-rag (query + ingest) | — | — | `user_profile.md`, `feedback_plan_trust.md`, `reference_claude_skills.md`, `reference_tresor.md` | block-stage-sensitive, block-dangerous-commands | — |
| `/create-plan` | context7 (resolve + query), local-rag (query) | — | — | `feedback_workflow.md`, `feedback_plan_trust.md`, `project_env_cleanup.md` | block-stage-sensitive | — |
| `/implement-plan` | context7 (API lookups), local-rag (query per phase), RepoMapper (structural nav), sequential-thinking (complex logic) | tdd-test-writer, tdd-implementer, worktree agents, docs-writer, trading-bot-developer, data-pipeline-engineer | `/simplify` | `feedback_worktree_commit.md`, `feedback_parallel_sessions.md`, `feedback_hooks_jq.md` | pre-edit-protect, tdd-order-check, post-edit-format, test-logger, block-stage-sensitive, block-dangerous-commands, stop-completion-gate | WorkerProvider (claude default) |
| `/review` | — | code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer | `/code-health` (--health) | `feedback_review_verification.md`, `feedback_docs_gitignore.md` | strip-ai-attribution, block-stage-sensitive | — |
| `/ppr` | — | — | — | `feedback_docs_gitignore.md` | strip-ai-attribution, block-push-main | — |
| `/post-merge` | — | — | — | — | block-dangerous-commands | — |
| `/pipeline` | (delegates to phase skills) | phase subagents (--phase-mode subagent) | `/implement-plan`, `/review` (inline) | (delegates to phase skills) | (delegates to phase skills) | (delegates to /implement-plan) |
| `consumer-web-app` workload (overlay) | gstack browse daemon (via `/gstack-*`); OpenAI Images API (only `/gstack-design-shotgun`) | — | `/gstack-office-hours`, `/gstack-design-consultation`, `/gstack-plan-design-review`, `/gstack-design-shotgun`, `/gstack-design-html`, `/gstack-qa`, `/gstack-design-review`, `/gstack-devex-review`, `/gstack-benchmark`, `/gstack-document-release`, `/gstack-canary`, `/gstack-retro` (overlay on native phase skills — full per-phase mapping in `~/.claude/CLAUDE.md` § Consumer Web App Mode) | — | (inherits from per-phase rows above) | — |

### Memory Feed

How acquired memories (`~/.claude/projects/<project-slug>/memory/`) inform each phase. Reads are advisory — Claude reads memories when contextually relevant, not on every invocation.

| Memory File | Phases | How It's Used |
|-------------|--------|---------------|
| `user_profile.md` | analyze, interview-prp (deprecated) | Tailors question depth and phrasing to user's role and expertise. Charter Discovery (`/pipeline` Step 0) does not re-read this memory yet. |
| `feedback_plan_trust.md` | analyze, create-plan | Avoids over-exploration; sets plan detail level (from a past over-exploration incident) |
| `feedback_workflow.md` | create-plan | Respects user preference for explicit agent control vs auto-spawning |
| `feedback_worktree_commit.md` | implement-plan | Ensures worktree agents commit before reporting done |
| `feedback_parallel_sessions.md` | implement-plan | Checks git log before assuming working-tree state (concurrent sessions) |
| `feedback_review_verification.md` | review | Uses findings registry instead of bulk-verification agents |
| `feedback_hooks_jq.md` | implement-plan | Ensures hooks use python3 for JSON parsing (jq not installed) |
| `feedback_docs_gitignore.md` | review, ppr | Claude exclusions go in .git/info/exclude, not .gitignore |
| `reference_claude_skills.md` | analyze | Check available skills inventory before recommending tools |
| `reference_tresor.md` | analyze | Check available prompt templates and standards |
| `project_env_cleanup.md` | create-plan | Tracks project state context across iterations |

### Memory Integration

All memory files are in `~/.claude/projects/<project-slug>/memory/`, indexed by `MEMORY.md` which is loaded into system context at session start.

**Memory writes:** Any phase can write new memories when:
- User corrects Claude's approach → write feedback memory
- New project context surfaces → write project memory
- New external resources discovered → write reference memory

Writes follow the auto-memory save protocol in the system instructions.

## Tools

- Tool libraries: `~/claude-skills/` (optional install), `~/.claude/tresor-resources/`. Install per-project via symlink.

## Per-Project Evaluation

- **Anti-rationalization hook**: For complex multi-phase projects (adds latency per tool call).
- **On-demand skills**: Charter Discovery via `/pipeline` Step 0 for product discovery (legacy `/interview-prp` deprecated — PRP-style artifact still available there), `/ascii-diagram` for architecture.
- **Context status line**: Real-time context usage monitoring via `/statusline`.
- **LSP plugins**: `pyright-lsp` active globally. Per-project: `typescript-lsp`, `csharp-lsp`, etc.
