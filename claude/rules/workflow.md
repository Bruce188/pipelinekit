---
description: Detailed workflow conventions — plan management, versioning, directory structure, context-aware clearing, base-branch detection. Loads only in projects with workflow structure.
paths:
  - "**/docs/**"
  - "**/.claude/**"
---

# Workflow Operational Details

> 計劃管理、目錄結構、RAG、專案啟動之詳細規範。核心原則留於 ~/.claude/CLAUDE.md；此檔專述操作細節。

## Global Argument Convention

技能接受可選 `--` 參數。參數在命令後傳遞（例如 `/pipeline-review --scope 2.3`）。

| Argument | Available on | Behavior |
|----------|-------------|----------|
| `--scope` | `/pipeline-review` | Target task ID (`--scope 2.3`) or path (`--scope src/auth/`) |
| `--no-parallel` | `/implement-plan` | Force sequential execution, skip parallel detection |
| `--renew` | `/pipeline` | Regenerate feature file from deferred items + failed features, then process |
| `--force` | `/pipeline-review` | Override review cycle cap (manual only — never passed by pipeline) |
| `--no-teams` | `/pipeline-review` | Opt out of Agent Teams. Teams default-on; disables cross-agent comms for run. |
| `--no-teams` | `/pipeline` | Force `never teams` — dispatches `Skill: pipeline-review --no-teams` at every review boundary, suppressing heuristic and persisted `**Review style:**`. |
| `--max-usd` | `/pipeline` | Hard cap on cumulative USD. Default: unlimited. Halts at phase boundaries when next phase would exceed cap. |
| `--max-turns` | `/pipeline` | Hard cap on accumulated sub-agent turns. Default: unlimited. Halts at phase boundaries. |
| `--from` | `/pipeline` | Free-text context for feature-file auto-gen. Step 1.5. Excl `--adopt`, `--renew`. |
| `--plan` | `/pipeline` | Path to plan-mode markdown (typically `~/.claude/plans/<slug>.md`). No path → most-recent file in `~/.claude/plans/` within 60 min. Ingests via in-process Agent dispatch → `docs/features.md`. Excl `--from`, `--adopt`, `--renew`, positional. 200 KB cap. |
| `--issues` | `/pipeline` | Ingest GitHub Issues as feature source. Forms: `label:<name>`, `milestone:<name>`, `all`, bare `<name>` (→ `label:<name>`). Routes Step 1.45. Excl `--plan`, `--from`, `--adopt`, `--renew`, positional. |
| `--issues-limit` | `/pipeline` | Cap issues at `<N>` (default 50, max 200). |
| `--issues-sort` | `/pipeline` | Sort: `created` (default), `updated`, `priority`. |
| `--issues-comment-author` | `/pipeline` | Override maintainer-comment heuristic. Only `<login>` comments inform constraint extraction. |
| `--no-prompts` | `/pipeline` | Session-wide autonomy modifier. Skip every `AskUserQuestion` for run. Sites fall back to safe default. Old `--auto` is deprecation alias for one release. |
| `--no-review` | `/pipeline` | Skip review phase. Step 5.6 synthesises Path A pass (one-line skip-notice, updates `**Review:**`) → `/ppr`. |
| `--no-ppr` | `/pipeline` | Skip `/ppr` per feature. Halt: `Status: COMPLETED (--no-ppr halt; no push/PR/merge)`. Dry-run implement+review. |
| `--no-docs` | `/pipeline` | Skip Documentation Update Phase. Aliases `PIPELINE_SKIP_DOCS=1`. |
| `--no-tdd` | `/pipeline` | Force `FEATURE_CLASS = non-dev` for every feature. Bypasses Step 5.5.0 — standard `implement-plan`, no TDD pairing. |
| `--no-test-loop` | `/pipeline` | Disable implement-plan test-run inner loop (Step 2e.5). Records `NO_TEST_LOOP=true`. No effect on TDD red/green; suppresses post-task test+fix-retry loop. |
| `--no-notifications` | `/pipeline` | Disable notification emission. Aliases `PIPELINE_NO_NOTIFICATIONS=1`. |

**Note:** `/code-health` has its own arguments (`--scope`, `--quick`, `--threshold`) — sits outside main pipeline. Its `--scope` scopes quality dimensions, not file paths.

### --scope

`--scope` 出現於 `/pipeline-review` 時：
1. If value matches task ID pattern (e.g., `2.3`): look up task files in plan, scope git diff to those files
2. If value is a path: scope git diff to that path

Default (no --scope): auto-detect from reopened tasks (review Step 3.5). If no reopened tasks exist: full diff.

### --no-parallel

`--no-parallel` 出現於 `/implement-plan` 時：
1. Skip parallel detection entirely
2. Execute all tasks sequentially (Step 2)
3. Use when: worktree issues, debugging, or tasks with implicit deps not in plan

**Default (no --no-parallel):** `/implement-plan` attempts parallel execution for phases with multiple tasks at zero file overlap. Falls back to sequential if tasks share files or have noted deps.

## Project Startup

**New project:**
1. Scaffold + `.claude/CLAUDE.md` + `.gitignore`. Claude exclusions → `.git/info/exclude`.
   - **Base branch init:** No repo: `git init && git checkout -b main && git commit --allow-empty -m "init: empty base"`. Repo without `main`/`master` branch and no remote: `git branch main $(git rev-list --max-parents=0 HEAD | tail -1)` creates `main` at first commit. Feature branches via `/new-branch`.
2. Check tools: `~/.claude/skills/`, `~/.claude/agents/`, MCPs. Ask about libraries (`~/claude-library/`, `~/claude-skills/`, `~/.claude/tresor-resources/`).
3. Run `/pipeline`, step through Charter Discovery (Step 0) → `docs/charter.md`.

**Existing project / defined task — pre-check:**
執行 `/analyze` 前，以基底分支偵測片段（見 § Base Branch Detection）確認基底分支存在。偵測失敗且無遠端者，提示創建：`git branch main <first-commit-hash>`。防 `/pipeline-review` 後段阻塞。

**Resuming:** Read `docs/progress.md` first → current plan + current task → read plan and task prompt.

## Directory Convention

- **`docs/`** — AI workflow only: progress.md, plan.md, prompts.md, analysis.md, prp.md, review, pipeline-state.md, pipeline-intel.json, .last-verify.json. NOT committed — patterns in `~/.claude/config/never-stage.txt`, enforced by `block-stage-sensitive.sh`. New files in `docs/` must register in both list and hook.
  - **`docs/archive/`** — Rotated Status tables from `/create-plan`. Never committed, excluded via `~/.git/info/exclude` and `never-stage.txt`.
- **`documentation/`** — App docs: API refs, guides, architecture. IS committed.

## Plan & Progress

- **Versioning:** Plan and prompts follow **Versioning Convention** below.
- **progress.md history-preserving:** `done` tasks never removed. Superseded `todo`/`doing` may be replaced. New tasks appended. Superseded Status tables → `docs/archive/progress-v<N>.md` via `/create-plan` Step 5.
- **Task reopening:** `/pipeline-review` may set completed back to `todo` with `reopened: review-vN`. `/implement-plan` reads review file for guidance. New micro-tasks created if findings unmapped.
- **Pointer system:** `progress.md` has `**Plan:**`, `**Prompts:**`, `**Charter:**` pointing to active files. Readers (`/implement-plan`, `/pipeline-review`, `/ppr`) follow — never hardcode `docs/plan.md`.
- **Charter pointer:** `**Charter:**` field. `/pipeline` Step 0 writes on create or adopt. Downstream reads to locate `docs/charter.md`.
- **Analysis pointer:** `**Analysis:**` field. `/analyze` updates. `/create-plan` follows instead of hardcoding.
- **Review pointer:** `**Review:**` field. `/pipeline-review` updates on save. `/implement-plan` follows for reopened tasks.
- **analysis.md:** Follows **Versioning Convention**. Pointer in progress.md tracks current.
- **prp.md:** User asked before overwriting.
- **Never stage:** `~/.claude/config/never-stage.txt` — hook `block-stage-sensitive.sh` reads same file.
- Use `git log`/`git diff` for recent changes — don't duplicate in progress.md.

## Versioning Convention

版本化工作流文件（plan, prompts, analysis, review, charter）遵同一歸檔規範：

1. Check for existing files: `ls docs/<type>*.md`
2. Find highest version N among `docs/<type>-v*.md` files (if none, N = 0)
3. If unversioned `docs/<type>.md` exists: archive it as `docs/<type>-v[N+1].md` (consumes slot N+1)
4. Write new file as `docs/<type>-v[N+2].md` (or `docs/<type>-v[N+1].md` if no unversioned file was archived)
5. First-time files: write as `docs/<type>.md` (no version suffix)

Skills reference this convention rather than duplicating logic.

## Context-Aware Clearing

非所有管道轉換均需 `/clear`。各轉換選合適工具：

| From | To | Action | Reason |
|------|----|--------|--------|
| `/pipeline` Step 0 | `/create-plan` | `/compact` | Charter Discovery output is the input — keep in context |
| `/analyze` | `/create-plan` | `/compact` | Analysis output is the input — keep in context |
| `/create-plan` | `/new-branch` | (none) | Trivial operation, context still relevant |
| `/new-branch` | `/implement-plan` | `/clear` | Fresh context for implementation, plan is on disk |
| `/implement-plan` | `/pipeline-review` | `/clear` | Fresh context prevents bias toward own code |
| `/pipeline-review` (pass) | `/ppr` | `/compact` | Lightweight transition; preserves session continuity |
| `/pipeline-review` (findings) | `/implement-plan` | `/clear` | Fresh context for fix implementation |
| `/pipeline-review` (scope change) | `/create-plan` | `/clear` | Re-planning needs fresh context |
| `/create-plan` (re-plan) | `/implement-plan` | `/clear` | Same as initial plan→implement; branch exists, skip `/new-branch` |
| `/ppr` | `/post-merge` | (none) | Trivial cleanup |
| `/post-merge` | next task | `/clear` | Full reset for new work |
| `/pipeline` phase→phase (subagent mode) | any | Agent dispatch | Replaces `/compact` with true context isolation |

**Manual edits between steps:** Commit before `/pipeline-review`:
```bash
git add <files> && git commit -m "fix: <description>"
```
`/pipeline-review` analyzes committed only (`git diff $BASE...HEAD`). Uncommitted edits invisible and block `/ppr`.

## Deferred Items

`progress.md` has `## Deferred` section for work explicitly postponed (not abandoned):

```
## Deferred
| Item | Source | Reason | Target Iteration |
|------|--------|--------|-----------------|
| Feature X | plan-v1.md | Needs dedicated iteration | Next |
```

- `/create-plan` reads deferred items, asks which to include
- Items included → removed from Deferred
- Items remaining deferred preserved
- New deferrals from current plan appended

## Review Files

Review findings follow **Versioning Convention** above.
- `progress.md` `**Review:**` pointer to current file
- Review files: each finding, related task, severity (blocking/non-blocking)
- `/pipeline-review` saves findings AND reopens tasks in progress.md
- `/implement-plan` reads review file on reopened tasks

## Base Branch Detection

需基底分支之技能（如 `/pipeline-review`, `/post-merge`, `/ppr`）均用此標準片段：

```bash
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
[ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}')
[ -z "$BASE" ] && BASE="main"
git rev-parse --verify "$BASE" 2>/dev/null || echo "ERROR: Base branch '$BASE' not found locally."
```

If this snippet needs updating, change here — all skills reference this section.

## Pipeline State Schema

`docs/pipeline-state.md` per-run state from `/pipeline`. Fields (from Step 5.1 unless noted):

- `**Feature file:**` — path
- `**Feature:**` — `<index> / <total>` (1-based)
- `**Name:**` — current feature H2 (`<type>/<name>`)
- `**Step:**` — phase (`analyze` | `plan` | `implement` | `review` | `done`)
- `**Completed:**` — ISO8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) on clean termination. From Step 5.10. Absent on halts (failed, BUDGET_EXCEEDED, Path C stuck).
- `**Features merged:**` — count completing `/ppr`. From Step 5.10. Absent on halts.
- `**Review cycles:**` — integer, +1 per Path B
- `**Replan count:**` — integer, +1 per Path C
- `**Path D attempted:**` — bool, default `false`. Set `true` before Path D salvage dispatch (persist pre-subagent so mid-dispatch crash bars double-fire on resume). Absent on legacy = `false`. See SKILL.md Step 5.8 Path D row, `reference.md` § "Path D — Fresh-context Salvage".
- `**Started:**` — pipeline start ts
- `**Max USD:**` — hard cap (from `--max-usd`). `unlimited` on omit; budget check no-ops.
- `**Max turns:**` — hard cap (from `--max-turns`). `unlimited` on omit.
- `**Phase Mode:**` `subagent` | `inline` (legacy/Path N) — per-feature at Step 5.0. New always `subagent`. `inline` only in (a) legacy state files, or (b) Path N (Edit-tool only). See § Phase Mode Precedence.
- `**Inline cycles:**` — int, default 0, +1 per Path M cycle; cap 2. Resets at feature init. Overflow (`> 2`) → Path B step 6 (re-review only). Separate from Path N `**Nit cycles:**` — each path gets independent 2-cycle allowance. See SKILL.md Step 5.7 Row 1.7, reference.md § "Path M — Inline Mini-Fix".
- `**Last phase agent:**` subagent ID of last dispatched phase — present when via `Agent`. Omitted on inline (Path N).
- `**Feature class:**` `dev` | `non-dev` — at Step 5.5.0. Drives TDD: `dev` dispatches tdd-test-writer + tdd-implementer pair per task; `non-dev` uses standard implement-plan.
- `**Charter:**` path to charter (e.g., `docs/charter.md`), or `(none)` on `--no-charter`. From Step 5.1. Step 3 (resume) reads and preserves; valid → Step 0 not re-run.
- `**Review style:**` `always teams` | `never teams` | `orchestrator decides` — per-feature teams toggle. Priority: (1) `--no-teams` override (`never teams`), (2) Charter Topic 11, (3) default `orchestrator decides`. With `orchestrator decides`, Step 5.6.0 heuristic: `DIFF_LINES > 500 OR DIFF_FILES > 8 OR feature_class = dev → teams-on`. Teams default-on, "never teams" → `Skill: pipeline-review --no-teams`; else plain `Skill: pipeline-review`. Sticky per feature.
- `**Prior finding count:**` total findings (blocking + non-blocking) from prev cycle — Path B heuristic
- `**Non-converging cycles:**` consecutive cycles where count didn't decrease — observability only; Path B bounded by 5-cycle hard cap (Path C escalates)
- `**Conv guard logged:**` 0 or 1 — set 1 first time `CONVERGENCE_GUARD_DISABLED` emitted for feature. Persisted so resumes do not re-emit. Cleared at feature init; not reset by `path_c_replan`.

## Phase Mode Precedence

管道在每次特性循環入口選 `subagent` 為階段模式，無界面面積啟發式。模式漂移事件揭示根本缺陷：`subagent` 特性審查後因 Path B 未遵 `**Phase Mode:**` 而降為 inline。Path B 修復（讀新 + Agent 派送）閉合漂移；DESC_LEN/HAS_CONSTRAINTS/HAS_AC 啟發式隨之移除——Path B 始終以 `subagent` 派送，啟發式成廢策略。

| Stage | Mode |
|-------|------|
| Feature start (Step 5.0) | `subagent` — always |
| Path B re-implement / re-review | `subagent` — reads `**Phase Mode:**` fresh, dispatches via Agent |
| Path C re-plan / re-implement / re-review | `subagent` — same as Path B |
| Path N (nit-only post-review) | `inline` — inline-dispatch path (alongside Path M); max 2 cycles, Edit-tool only |
| Path M (small non-blocking fixes post-review) | `inline` — Edit-tool only, max 2 cycles, conservative gate (see SKILL.md Step 5.7 Row 1.7) |
| Optional Row-2 nit preamble (`PIPELINE_NIT_FIRST=1`) | `inline` — runs Path N body, falls through to Path B subagent dispatch |

> Tracer-bullet framing throughout this file (vertical-slice priority, anti-horizontal-slicing) follows Matt Pocock's adaptation of *The Pragmatic Programmer* (Hunt & Thomas, 1999). See `claude/skills/tdd/SKILL.md` lines 26–49 for vendored anti-pattern doc.

**Path M gate examples:**

- **Qualifying:** 2 non-blockers: NB1 "rename `foo` → `fooBar` (1 line, 1 file)", NB2 "tighten error string (2 lines, 1 file)". 2 findings, 3 lines, 1 file each. Mechanical `Suggestion:` → Path M.
- **Disqualifying (multi-line):** 1 finding, 12 lines. `lines_changed > 5` → Path B.
- **Disqualifying (multi-file):** 1 finding, 2 files. `files_changed > 1` → Path B.
- **Disqualifying (count):** 4 findings, each ≤ 5 lines / 1 file. `total_finding_count > 3` → Path B.
- **Disqualifying (aggregate lines):** 3 findings of 4+3+3 (10 total). Each ≤ 5 per-finding, BUT `total_lines_across_findings > 8` → Path B.
- **Disqualifying (logic suggestion):** `Suggestion:` reads "rework error-handling to use new `Result<T,E>` pattern". No mechanical Edit → Path B.
- **Disqualifying (blocker present):** any blocker short-circuits clause 1 → Path B.
- **Disqualifying (partial-application):** Review batch contains 5 findings; 3 qualify per-finding (each ≤ 5 lines, 1 file, mechanical) but 2 disqualify (multi-line or non-mechanical). Reviewer's instinct: "apply Path M to the 3, defer the other 2 in prose." FORBIDDEN. The entire batch routes to Path B. Defer is NOT a fallback for the unqualified remainder — Defer requires a state transition (see `claude/skills/review/SKILL.md` Step 7.6 Contract 2: `progress.md` `## Deferred` row, new feature block, or task reopen). Path M is all-findings-or-none.

**On resume:** Preserve saved `**Phase Mode:**` from `docs/pipeline-state.md`. Never silently downgrade `subagent` → `inline`. Direct `Skill: implement-plan` or `Skill: pipeline-review` on `subagent`-mode resume is contract violation — see SKILL.md Step 3 § "Phase Mode preservation contract".

**Legacy state files:** Resumed file recording `**Phase Mode:** inline` (prior heuristic) preserved for in-flight feature only. New features post-legacy-resume dispatch `subagent`. Pipeline logs `LEGACY_PHASE_MODE: inline mode preserved for in-flight feature; new features dispatch via subagent` once per resume.

Mode in `docs/pipeline-state.md` at Step 5.1 per-feature.

## Pipeline Entry Point

`/pipeline` (Skill — in-process) is only entry point in portable build. Runs all phases in single Claude Code session. Phase Mode always `subagent` for new features (Agent-tool dispatch per phase) — no surface-area heuristic. Path N sub-paths inline by design (Edit-tool only, max 2 cycles).

子程序驅動器不隨附交付。若需在互動 Claude session 外進行長時間無人值守執行，自行分叉並添加驅動器——`~/.claude/skills/pipeline/reference.md` 中各階段提示模板是驅動器必須實現的契約。

---

## MCP Constraints

**Global servers** (in `~/.claude.json` — available to all projects):
- **context7:** Library/framework documentation lookup. Universally useful.
- **local-rag:** Niche API docs only (exchange APIs in `~/exchange-docs/`). Don't RAG standard frameworks.

**Per-project servers** (add to `.mcp.json` in project root where needed):
- **sequential-thinking:** Deep reasoning chains. Multi-step logic tasks.
- **RepoMapper:** Structural patterns, class hierarchies, call graphs. Large codebases.
- **voicemode:** Push-to-talk via `converse`.
- **claude-context:** Semantic RAG via `@zilliztech/claude-context` (community MCP — NOT Anthropic). AST chunking + Merkle-tree incremental indexing; complements serena (LSP/symbolic) with semantic retrieval. Uncomment `.mcp.json.template` block to enable. `/analyze` Step 3.6 skips below 50000 LOC. local-mode (Ollama / Transformers, no Milvus account) and cloud-mode (Milvus / Zilliz creds via `MILVUS_ADDRESS` / `MILVUS_TOKEN`) supported. Upstream benchmark: <5s per `git pull` for incremental re-indexing.

Example `.mcp.json` for project needing RepoMapper:
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

各管道階段緊湊路由表。原生工具（Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch）在各 SKILL.md `allowed-tools`——此處不重複。MCP 在已配置時可用；技能執行期自動偵測。

> *Agent-type selection for the rows below follows `~/.claude/rules/agents-worktrees.md § Typed-subagent selection rule` — pick the most specific specialist; `general-purpose` is a justified fallback only.*

| Phase | MCPs | Agent Types | Sub-Skills | Memory Reads | Hooks | WorkerProvider |
|-------|------|-------------|------------|--------------|-------|----------------|
| `/analyze` | context7 (resolve + query), local-rag (query + ingest) | — | — | `user_profile.md`, `feedback_plan_trust.md`, `reference_claude_skills.md`, `reference_tresor.md` | block-stage-sensitive, block-dangerous-commands | — |
| `/create-plan` | context7 (resolve + query), local-rag (query) | — | — | `feedback_workflow.md`, `feedback_plan_trust.md`, `project_env_cleanup.md` | block-stage-sensitive | — |
| `/implement-plan` | context7 (API), local-rag (query) | tdd-test-writer, tdd-implementer, worktree agents, docs-writer, trading-bot-developer, data-pipeline-engineer | `/simplify` | `feedback_worktree_commit.md`, `feedback_parallel_sessions.md`, `feedback_hooks_jq.md` | pre-edit-protect, tdd-order-check, post-edit-format, test-logger, block-stage-sensitive, block-dangerous-commands, stop-completion-gate | WorkerProvider (claude default) |
| `/pipeline-review` | — | code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer | `/code-health` (sibling skill — run directly) | `feedback_review_verification.md`, `feedback_docs_gitignore.md` | strip-ai-attribution, block-stage-sensitive | — |
| `/ppr` | — | — | — | `feedback_docs_gitignore.md` | strip-ai-attribution, block-push-main | — |
| `/post-merge` | — | — | — | — | block-dangerous-commands | — |
| `/pipeline` | (delegates to phase skills) | phase subagents (--phase-mode subagent) | `/implement-plan`, `/pipeline-review` (inline) | (delegates to phase skills) | (delegates to phase skills) | (delegates to /implement-plan) |

> Note: the pipeline-phase review skill registers under `/pipeline-review` (renamed from `/review` per F20 `fix/review-skill-namespace-collision` to avoid collision with the harness's built-in GitHub PR-review template). The bare `/review` slug is reserved for direct user-driven PR-review invocation (`/review <PR#>`). See `claude/CLAUDE.md.template` Lean Conventions for the regression target.

### Memory Feed

已獲記憶（`~/.claude/projects/<project-slug>/memory/`）如何指導各階段。讀取為建議性。

| Memory File | Phases | How It's Used |
|-------------|--------|---------------|
| `user_profile.md` | analyze | Tailors question depth/phrasing to role and expertise. |
| `feedback_plan_trust.md` | analyze, create-plan | Avoids over-exploration; sets plan detail |
| `feedback_workflow.md` | create-plan | Respects explicit agent control vs auto-spawning |
| `feedback_worktree_commit.md` | implement-plan | Worktree agents commit before done |
| `feedback_parallel_sessions.md` | implement-plan | Checks git log before assuming tree state |
| `feedback_review_verification.md` | review | Findings registry over bulk-verification agents |
| `feedback_hooks_jq.md` | implement-plan | Hooks use python3 for JSON parsing |
| `feedback_docs_gitignore.md` | review, ppr | Claude exclusions → .git/info/exclude, not .gitignore |
| `reference_claude_skills.md` | analyze | Check skills before recommending tools |
| `reference_tresor.md` | analyze | Check prompt templates and standards |
| `project_env_cleanup.md` | create-plan | Tracks project state across iterations |

### Memory Integration

記憶檔於 `~/.claude/projects/<project-slug>/memory/`，由 `MEMORY.md` 索引，於 session 啟動載入系統上下文。

**Memory writes:** 任何階段在以下情形可寫入新記憶：
- User corrects Claude's approach → write feedback memory
- New project context surfaces → write project memory
- New external resources discovered → write reference memory

Writes follow auto-memory save protocol in system instructions.

## Tools

- Tool libraries: `~/claude-skills/` (optional install), `~/.claude/tresor-resources/`. Install per-project via symlink.

## Per-Project Evaluation

- **Anti-rationalization hook**: For complex multi-phase projects (adds latency per call).
- **On-demand skills**: Charter Discovery via `/pipeline` Step 0, `/ascii-diagram` for architecture.
- **Context status line**: Real-time monitoring via `/statusline`.
- **LSP plugins**: `pyright-lsp` global. Per-project: `typescript-lsp`, `csharp-lsp`, etc.
