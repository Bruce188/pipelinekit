---
name: pipeline-review
description: Multi-agent parallel review with auto-scaling agent selection. Scales from 2 agents (small diffs) to 6-agent teams (large diffs). Teams mode is default-on; pass --no-teams to opt out. Supports --scope, --force, --no-teams. Renamed from `review` per F20 to avoid collision with the harness's built-in GitHub PR-review template — the bare `review` slug stays reserved for direct user `/review <PR#>` invocation.
argument-hint: [--scope <task-id|path>] [--force] [--no-teams]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - Skill
  - mcp__agentmemory
  - mcp__serena
  - mcp__sequential-thinking
effort: high
paths:
  - claude/skills/review/**
  - docs/review*.md
  - docs/progress.md
  - docs/pipeline-state.md
---

# Pipeline-Review — Multi-Agent Parallel Review

## Threshold Constants

These constants control automatic agent selection based on diff size (measured in lines from `$DIFF_LINES`):

- `SMALL_DIFF_THRESHOLD = 500` — diffs below this use lightweight review (2 agents)
- `LARGE_DIFF_THRESHOLD = 5000` — diffs exceeding this auto-enable Agent Teams (5 agents, collaborative)
- Diffs between these thresholds use the standard 5-agent independent review

---

## Issue Taxonomy

Every finding is classified by **severity** (universal `critical | high | medium | low`) and **category** (code-review default set, plus a web/UI set used when charter `project_type = web`). Agents emit findings using these labels so the dedupe/triage step can compare apples to apples.

Full severity definitions, both category lists, and the rationale: see `reference.md` § "Issue Taxonomy".

---

Sanity gate → secret scan → auto-scaled review agents → collect findings.

```
Sanity Gate (quick test run)
  ↓ PASS only
Secret Scanner Pre-Check (on scoped diff)
  ↓ CLEAN only
Tier Detection (small < 500 lines / medium / large > 5000 lines)
  ↓
Review Agents (2 for small, 5 for medium, 5 + teams for large)
  ↓
Collect, Deduplicate, Save Findings
```

---

## Process

### Step 1: Detect Project Type and Base Branch

```bash
ls package.json pyproject.toml requirements.txt setup.py *.sln *.csproj 2>/dev/null
```

Detect the base branch using the standard snippet from `~/.claude/rules/workflow.md` § Base Branch Detection.

| Found | Type |
|-------|------|
| `package.json` | Node.js |
| `pyproject.toml` or `requirements.txt` or `setup.py` | Python |
| `*.sln` or `*.csproj` | .NET / C# |
| Multiple types | Mixed — run all applicable sets |
| None | Warn, attempt best-guess based on file extensions |

If `git rev-parse --verify "$BASE"` fails: **STOP.** Output:
> "Cannot determine base branch. Run `git fetch origin` or set origin/HEAD with `git remote set-head origin --auto`."

Use `$BASE` in place of hardcoded `main` in all `git diff` commands throughout this skill.

---

### Step 1.5: Review Cycle Cap (per-branch/per-feature)

Count review cycles scoped to the **current feature** only (never a global `ls docs/review-v*.md | wc -l`). Prefer `pipeline-state.md`'s `**Review cycles:**` field when the pipeline drives; fall back to counting `docs/review-v*.md` files whose `**Branch:**` header matches the current branch and whose `**HEAD:**` SHA is reachable from HEAD.

If `$REVIEW_COUNT` >= 5 AND `--force` is absent: **STOP** with the cycle-limit message (re-plan / `--force` / pipeline auto-replan options). If `--force` is present: log the override and proceed. The `--force` flag must never be passed by the pipeline.

Full counting bash (both options), the verbatim STOP message, and the notes: see `reference.md` § "Step 1.5 — Review Cycle Cap (per-branch/per-feature)".

---

### Step 2: Sanity Gate

Quick smoke test to catch obvious breakage before spawning agents — NOT a full suite.

1. **Verification-marker fast path:** if `/implement-plan` left a fresh `docs/.last-verify.json` (matching HEAD SHA, `tests_passed` + `build_passed` true, age ≤ 600s, no uncommitted tracked changes), set `SKIP_SANITY=true`, log the inherited verification, and skip the test run. The marker is then deleted.
2. **Otherwise run the per-language sanity command** (`pytest --tb=line -q --no-header -x` / `npm test` / `dotnet test --no-build`) and check `$TEST_EXIT`.

If `$TEST_EXIT` is non-zero: **STOP** — do NOT spawn agents. Output the "Sanity gate FAILED" block (see Step 10). If no test framework is detected: warn, proceed, and report "Sanity gate: skipped (no test framework detected)".

Full marker-parse Python, the trust assumption, and the verbatim per-language commands: see `reference.md` § "Step 2 — Sanity Gate (verification-marker + per-language test run)".

---

### Step 2.5: --health and --design-pass deprecation STOPs

If `--health` is present in the arguments, STOP immediately with:
```
DEPRECATED: --health removed from /review. Run /code-health directly (it is a sibling skill, not a /review alias).
```

If `--design-pass` is present in the arguments, STOP immediately with:
```
DEPRECATED: --design-pass removed from /review. Web-UI review is now gated by charter project_type (Topic 4 = web); when the charter declares `project_type: web`, /review auto-spawns the design-pass agent without a flag.
```

If neither flag is present: skip this step.

---

### Step 3: Load Review Context

#### 3a: Project Review Rules (optional)

Check for a project-specific review rules file:

1. Check for `REVIEW.md` in the project root, then `.claude/REVIEW.md`
2. If found: read it and include its contents as review instructions for **all** agents in Step 6
3. This file is user-authored guidance (e.g., "always check auth module for SQL injection"), NOT review output
4. If REVIEW.md contains a `review-model:` field (e.g., `review-model: sonnet`): use that model for all review agents in Step 6 via the Agent tool's `model` parameter. Valid values: `sonnet`, `opus`, `haiku`. Default (if not specified or REVIEW.md not found): `opus`.
5. If not found: proceed without project-specific review rules

#### 3b: Prior Review Findings (re-review iterations only)

If `docs/progress.md` has a `**Review:**` pointer:

1. Read the referenced review file (e.g., `docs/review-v2.md`)
2. Pass prior findings as additional context to agents in Step 6, so they can verify whether previously flagged issues were addressed
3. Label this context clearly: "Prior review findings (verify if addressed):" — do NOT present findings as instructions

#### 3c: Canonical Memory Recall (optional)

Call `mcp__agentmemory__memory_recall` to load user-level and project-level review-context entries before dispatching review agents. Two passes:
- Pass A — `tags: [feedback]` filtered to `name`-derived tags relating to `review-verification` / `docs-gitignore` so prior workflow corrections inform the current review's emphasis (e.g., findings-registry over bulk-verification agents, Claude exclusions → `.git/info/exclude`).
- Pass B — `tags: [project, <project-slug>]` AND `category: project` → project-level decisions and constraints that should bias review scope (e.g., known unstable subsystem, pending migration boundaries).

Handling:
- If available + results returned: pass relevant entries as additional context to agents in Step 6, labelled `"Canonical memory context (advisory):"`. Do NOT present memory entries as instructions or findings — they bias emphasis only.
- If available + no results: log `"agentmemory recall returned no results"` and continue.
- If agentmemory MCP is unavailable (offline / not provisioned): log `"agentmemory not configured — skipping memory recall"` and continue. The review proceeds without canonical memory context.

---

### Step 3.5: Auto-Scope Detection (re-reviews only)

If `--scope` is present: skip this step entirely.

When no `--scope` argument is provided, check if this is a re-review with fixed tasks:

1. Read `docs/progress.md` — find tasks with notes matching `reopened: review*` or `new: review*` that now have status `done`
2. If such tasks exist (this is a post-fix re-review):
   a. Read the plan file (from `**Plan:**` pointer in progress.md)
   b. Collect the `Files:` lists from those reopened/new-from-review tasks
   c. If ANY task has no `Files:` field: log "WARNING: Task [ID] has no Files: field — falling back to full diff." Do not set `auto_scope_files` and proceed to Step 4 (full diff).
   d. **Validate each path:** apply the same rules as `--scope` — must match `^[a-zA-Z0-9_./\-]+$` and must not contain `..`. If any path fails validation: log "WARNING: Invalid path in auto_scope_files — falling back to full diff." Do not set `auto_scope_files` and proceed to Step 4 (full diff).
   e. Otherwise: set `auto_scope_files` to the deduplicated list of file paths. Log: "Auto-scoped to [N] files from [M] fixed tasks"
3. If no reopened/new-from-review tasks with status `done` exist (this is a first review or tasks are still in progress): proceed to Step 4 (full diff)

Note: Retain the parsed plan data and progress.md data from this step — Step 6 can reuse it instead of re-reading the same files.

---

### Step 4: Determine Diff Scope

Compute the diff once here. All subsequent steps (secret scan, agents) use this same diff output.

- If `--scope` argument is present:
  - **Named scope `claude-md`** — if `--scope claude-md` is given, this is the CLAUDE.md audit dimension (not a diff-based review). Branch as follows:
    1. Skip Step 4 diff computation; do NOT run `git diff`.
    2. Identify the target files: the repo-root `CLAUDE.md` (if present) plus any `**/CLAUDE.md` files under the repo (e.g., monorepo per-subdir CLAUDE.md). Cap at 10 files; if more, warn and proceed with the first 10.
    3. Skip Steps 5 (secret scan) and 6 (multi-agent dispatch). Instead, dispatch a SINGLE agent via the Agent tool with `subagent_type: claude-md-guardian` and a prompt containing the file paths and instruction "audit per `## Pipelinekit Overlay — /review Integration` in your definition".
    4. The agent returns findings in pipelinekit's review schema (`Section | Severity | Finding | Recommendation`).
    5. Write findings to the active review file (per the `**Review:**` pointer in `docs/progress.md`) under a new top-level section `## CLAUDE.md Audit`.
    6. Skip Steps 7, 8, 9 (size guard, summary, task reopening). Exit normally — the audit dimension does not reopen tasks; it produces an informational report that the human reviews.
  - If value contains `..`: **STOP** with error "Invalid --scope value. Path traversal sequences (..) are not allowed."
  - **Validate the scope value:** must match `^[a-zA-Z0-9_./\-]+$`. If it contains shell metacharacters or fails validation: **STOP** with error "Invalid --scope value. Use alphanumeric characters, dots, slashes, hyphens, and underscores only."
  - If value looks like a task ID (e.g., `2.3`): read `docs/progress.md` -> find the `**Plan:**` field -> read the plan file -> find the task -> get its `Files:` list -> if `Files:` is empty or absent, **stop with error**: "Task [ID] has no Files: field. Use `--scope <path>` with an explicit path instead." -> otherwise `git diff "$BASE"...HEAD -- file1 file2 ...`
  - If value looks like a path (e.g., `src/auth/`): `git diff "$BASE"...HEAD -- <path>`
- If no `--scope` AND `auto_scope_files` is set (from Step 3.5): `git diff "$BASE"...HEAD -- [auto_scope_files]`. Log: "Using auto-scope from Step 3.5"
- If no `--scope` AND `auto_scope_files` is NOT set: `git diff "$BASE"...HEAD` (full diff)

Store the diff in a temp file for subsequent steps:
```bash
DIFF_FILE=$(mktemp)
git diff "$BASE"...HEAD [-- files if scoped or auto-scoped] > "$DIFF_FILE"
```
Note: Do NOT use `trap 'rm -f "$DIFF_FILE"' EXIT` — agents in Step 6 may still be reading the file when trap fires. Clean up $DIFF_FILE explicitly at the end of Step 7 after all agents have returned.

- If diff is empty: check `git log "$BASE"..HEAD --oneline`. If no commits: **STOP** with "No changes found between current branch and $BASE — nothing to review." If commits exist but diff is empty: **STOP** with "Commits exist but diff is empty (possible revert or no-op merge) — nothing to review."

**Size guard:** Count diff lines (`wc -l < "$DIFF_FILE"`). Store this count as `$DIFF_LINES` for use by Step 4.5. Threshold: 2,000 lines without `--scope` or auto-scope, 3,000 lines with `--scope` or `auto_scope_files` (scoped/auto-scoped reviews are more focused so larger diffs are acceptable). If diff exceeds the threshold:
- Log warning: "Diff is [N] lines. Large diffs degrade review quality."
- If `--scope` is not set: suggest "Consider using `--scope <task-id>` or `--scope <path>` to narrow the review."
- Proceed regardless (warning only, not blocking), but note the size in the final report.

---

### Step 4.5: Large Diff Escalation

After computing the diff, check if escalation to Agent Teams is warranted:

1. Use `$DIFF_LINES` from Step 4 (already computed by the size guard)
2. If lines <= 5,000: proceed normally (teams_mode remains at its default value: false)
3. If lines > 5,000:
   a. Save current env var state: `teams_was_set=$CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
   b. Export: `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
   c. Set `teams_mode=true` and `teams_auto_set=true`
   d. Log: "Large diff ([N] lines) — auto-enabling Agent Teams for this review."

   Note: The `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var controls whether Claude Code's Agent tool uses the teams protocol. Setting it via Bash `export` makes it available to subsequent Agent tool calls within the same session. The cleanup section of Step 7 (sub-item 9) reverts this if auto-set.

**Cleanup:** After Step 7 completes (success or failure): if `teams_auto_set` is true AND `teams_was_set` was not '1', unset `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. This ensures the environment is not permanently modified.

Note: This step can set teams_mode=true independently of Step 5.5 (default-on; --no-teams opt-out). Either source activates teams mode. The 2,000-line size guard warning (Step 4) and the 5,000-line escalation threshold are separate concerns — both can fire on the same diff.

---

### Step 4.6: Diff-Size Tier Detection

Determine the review tier based on `$DIFF_LINES` (computed in Step 4):

1. If `$DIFF_LINES < 500` (SMALL_DIFF_THRESHOLD): set `review_tier=small`. Log: "Small diff ([N] lines) — lightweight review: code-reviewer + spec-tracer only."
2. If `$DIFF_LINES >= 500` and `$DIFF_LINES <= 5000` (LARGE_DIFF_THRESHOLD): set `review_tier=medium`. Log: "Standard diff ([N] lines) — full 5-agent independent review."
3. If `$DIFF_LINES > 5000`: set `review_tier=large`. Log: "Large diff ([N] lines) — 5-agent collaborative review (teams mode)."

The tier affects which agents are spawned in Step 6.

---

### Step 5: Secret Scanner Pre-Check

Run secret-scanner patterns on the scoped diff (from Step 4). Only match added lines (`^\+`) to avoid flagging removed secrets:

```bash
timeout 30 grep -nE '^\+.*(AKIA[0-9A-Z]{16}|AIzaSy[a-zA-Z0-9_-]{33}|sk-[a-zA-Z0-9]{20,128}|sk-ant-[a-zA-Z0-9_-]{20,128}|sk-proj-[a-zA-Z0-9_-]{20,128}|sk_live_[a-zA-Z0-9]{24,128}|ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{22,255}|xox[baprs]-[a-zA-Z0-9-]{10,128}|npm_[a-zA-Z0-9]{36}|SG\.[a-zA-Z0-9_-]{22,128}\.[a-zA-Z0-9_-]{22,128}|-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----|password\s*=\s*"[^"]{8,128}"|password\s*=\s*'"'"'[^'"'"']{8,128}'"'"'|mongodb(\+srv)?://[^@\s]+@|postgres(ql)?://[^@\s]+@|mysql://[^@\s]+@|api[_-]?key\s*[:=]\s*"[^"]{10,128}"|api[_-]?key\s*[:=]\s*'"'"'[^'"'"']{10,128}'"'"'|(Authorization|Bearer)\s*[:=]\s*"[^"]{10,128}"|(rk_live_|whsec_)[a-zA-Z0-9]{10,}|eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}|(secret|token|access_key)\s*[:=]\s*"[^"]{10,}"|(secret|token|access_key)\s*[:=]\s*'"'"'[^'"'"']{10,}'"'"'|(redis|amqp|mssql)://[^@\s]+@|Server=.*Password=[^;]+|DefaultEndpointsProtocol=.*AccountKey=)' "$DIFF_FILE"
```

If `timeout` exits with code 124 (timed out): log "WARNING: Secret scanner timed out on large diff. Proceeding without secret scan — review agents will catch obvious issues." Proceed to agent review.

If matches found:
1. Check if matches are in test fixtures, comments, or documentation (patterns like `# example`, `// test`, `mock`, `fixture`, `placeholder`)
2. If ALL matches are clearly false positives (test fixtures/examples): log as warnings, proceed to agent review
3. If ANY matches look like real secrets: report immediately as blocking findings. Do NOT spawn agents. Output the "Secrets detected" block (see Step 10).

If clean: proceed to agent review.

---

### Step 5.5: Agent Teams Detection (default-on; --no-teams to opt out)

If `teams_mode` is already true (set by Step 4.5 large diff escalation): log "Teams mode already active (large diff escalation)." Skip to Step 6.

If `--no-teams` argument is present:
1. Set `teams_mode=false`. Log "Agent Teams disabled via --no-teams."
2. Skip to Step 6.

Otherwise (default behaviour — teams ON):

1. Save current env var state: `teams_was_set=$CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
2. If env var is not set or not "1": auto-export it for this review run:
   - Set `teams_auto_set=true`
   - Log: "Auto-enabling Agent Teams (default; pass --no-teams to disable)."
   Note: The `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var controls whether Claude Code's Agent tool uses the teams protocol. Setting it via Bash `export` makes it available to subsequent Agent tool calls within the same session. The cleanup section of Step 7 (sub-item 9) reverts this if auto-set.
3. Set `teams_mode=true`. Log: "Agent Teams mode enabled — agents will communicate during review."
4. If `review_tier=small`: upgrade `review_tier=medium`. Log: "Upgrading from small to medium tier for teams mode."

---

### Step 6: Spawn Review Agents

1. Read `docs/progress.md` -> parse `**Plan:**` field -> read the plan file.
2. Extract: objective, completed tasks, constraints
3. If REVIEW.md was loaded in Step 3a, include its instructions in all agent prompts. If prior findings were loaded in Step 3b, include them as additional context (labeled "Prior review findings — verify if addressed").

**Tier-based agent selection:**

- **If `review_tier=small`:** Spawn only 2 agents:
  - Agent 1 (code-reviewer) — from `agent-prompts.md` § "Agent 1 -- code-reviewer"
  - Agent 5 (spec-tracer) — from `~/.claude/agents/spec-tracer.md`
  Skip security-auditor, test-engineer, performance-tuner, and symbol-verifier. These agents add overhead that exceeds their value on small diffs. Note: symbol-verifier is deliberately excluded from small tier — see `documentation/review-cost.md` for the cost/detection trade-off rationale.

- **If `review_tier=medium`:** Spawn all 6 agents as independent agents (the 5 existing reviewers + symbol-verifier). No changes to existing logic.

- **If `review_tier=large` (teams_mode=true):** Spawn all 6 as named teammates (the 5 existing reviewers + symbol-verifier). No changes to existing teams logic.

All selected agents receive the path to $DIFF_FILE (from Step 4) and objective. Launch all selected agents in a single message using the Agent tool (parallel tool calls — up to 6 in medium / large tier). Each agent reads the diff via the Read tool. This avoids duplicating the full diff across agent prompts (~75% token savings).

Reviewers may use serena (`mcp__serena__find_symbol` / `mcp__serena__find_referencing_symbols`) for cross-file symbol resolution when tracing a finding beyond the diff hunk; fall back to Grep when serena is unavailable.

Note: `teams_mode` is default-on (Step 5.5) and can also be activated by large diff escalation (Step 4.5). Either source — the default OR the escalation — leads to the same team-based review below. `--no-teams` opts out of the default; the 5000-line escalation still overrides the opt-out as a last-resort safety net.

If an agent fails to return structured output or times out, note that agent as "incomplete" and continue collecting results from the remaining agents. Do not block on a single agent failure.

**If teams_mode=true:** spawn all selected reviewers as named teammates that communicate via SendMessage (each gets a `Correlated by:` field instruction). The lead MUST dispatch the base reviewer set as **exactly N `Agent` tool calls in a single assistant turn** — serial turns or wrapping-as-one are contract violations. The full teams-mode dispatch detail, the MANDATORY single-turn contract, the verbatim agent-type list, the three anti-patterns (**wrap-as-one-Agent**, **one-per-turn serial dispatch**, **fall-back-to-inline**), the correct-shape worked example, and the F6 background: see `agent-prompts.md` § "Teams dispatch shape — worked example and anti-patterns".

**If teams_mode=false (default):**

Launch as independent agents (existing behavior below).

Agent prompt templates are defined in `agent-prompts.md` (same directory).
Load the relevant block when spawning each agent.

- **Agent 1 -- code-reviewer:** see `agent-prompts.md` § "Agent 1 -- code-reviewer"
- **Agent 2 -- security-auditor:** see `agent-prompts.md` § "Agent 2 -- security-auditor"
- **Agent 3 -- test-engineer:** see `agent-prompts.md` § "Agent 3 -- test-engineer"
- **Agent 4 -- performance-tuner:** see `agent-prompts.md` § "Agent 4 -- performance-tuner"
- **Agent 5 -- spec-tracer:** prompt defined in `~/.claude/agents/spec-tracer.md`
- **Agent 6 -- symbol-verifier:** prompt defined in `~/.claude/agents/symbol-verifier.md` (self-contained, like spec-tracer)

**Default model mapping:** absent a `REVIEW.md` `review-model:` override (Step 3a), each reviewer runs on its agent-file default — opus for deep-reasoning roles (code-reviewer, security-auditor, symbol-verifier), sonnet for pattern-based roles (test-engineer, performance-tuner), haiku for spec-tracer. A `review-model:` override applies uniformly to all six. Full per-agent table and rationale: see `agent-prompts.md` § "Default model mapping".

---

### Step 6.5: Skill-Compliance Gates

Three pipelinekit-canonical gates catch skill-overreach, hook-observability holes, and documentation-richness regressions before they merge. Gates fire only when the diff touches the matching file types — no repo-wide scans — and produce findings inside the existing review output schema (Step 7 dedup applies uniformly). Thresholds are not user-configurable; they live in `claude/skills/review/check-skill-compliance.sh`.

| Gate | Severity | Fires on | Pass condition |
|------|----------|----------|----------------|
| (a) Skill-paths-or-allowlist | blocking | `claude/skills/<name>/SKILL.md` | declares `paths:` OR in `docs-source/skills-scope-policy.md § Global-by-design allowlist` |
| (b) Hook denial-tracker | non-blocking | `claude/hooks/*.{sh,py}` (excl `tests/`, `_`-prefixed) | calls `denial_tracker` OR carries `# denial_tracker:no <reason>` |
| (c) Docs richness | blocking | changed `docs-source/<name>.md` | matching `documentation/<name>.html` passes richness check OR source carries `<!-- richness-exempt: <reason> -->` |

Per-gate catch-rationale, the `gate-c-missing-render` sub-case, and the finding-block parse shape: see `reference.md` § "Step 6.5 — Skill-Compliance Gates (gate detail)".

**Invocation:** the review subagent runs `bash claude/skills/review/check-skill-compliance.sh` and captures stdout. Each `**File:** … **Severity:** … **Issue:** … **Suggestion:** … **Scope:** … **Intent:**` block is one finding, merged into the review output schema unchanged.

**Exit codes:** 0 = zero findings, 1 = at least one blocking, 2 = non-blocking only. Non-blocking findings flow through Path M when small + mechanical; blocking findings route through Path B.

**Smoke test:** `bash claude/skills/review/tests/test_skill_compliance_gates.sh`.

#### Step 6.5.5: Docs Richness Verification (corpus-level)

When the diff touches `docs-source/*.md` or `documentation/*.html`, additionally run `python3 claude/skills/docs-writer/richness_check.py --staged` (corpus-level — one verdict per touched HTML file, distinct from Gate (c)'s per-file invocation). Non-zero exit produces a blocking review finding. Full invocation guard and exit-code semantics: see `reference.md` § "Step 6.5.5 — Docs Richness Verification (corpus-level)".

---

### Step 7: Collect and Deduplicate Results

Merge, dedupe, and finalize findings from all spawned agents:

1. **Completion check** — if ALL agents failed/timed out: **STOP** with "Review BLOCKED — all agents failed." If some failed: warn and proceed with partial results.
2. **Merge + dedupe** same file:line (keep higher severity, combine descriptions); apply the hallucination prose-guard (downgrade blocking `category: hallucination` findings whose cited line is comment/docstring/prose); sort blocking → non-blocking → nit and count by severity. Use `mcp__sequential-thinking` for borderline severity/correctness calls (skip silently if unavailable).
3. **Cross-feature intel** — scan agent output for `**Cross-Feature Intel:**` notes and append JSON entries to `docs/pipeline-intel.json` (skip silently if none).
4. **Cleanup** — `rm -f "$DIFF_FILE"`; if `teams_auto_set` and `teams_was_set` was not `1`, unset `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. Teams mode preserves `Correlated by:` fields and notes "Review mode: Agent Teams (collaborative)".

Full ordered procedure including the intel JSON shape: see `reference.md` § "Step 7 — Collect and Deduplicate Results (full procedure)".

---

### Step 7.5: Auto-Fix Detection

Nit auto-fix always runs when `severity: nit` findings are present (no flag). If none exist, skip to Step 8.

When nits exist: record `EXISTING_FILES=$(git ls-files)`, apply nit fixes inline (Edit tool, nit-tagged only, scope-checked), then re-run the Step 2 sanity gate. If it passes — stage by name (never `git add -A`, never protected files), commit `fix: minor code quality improvements`, drop the fixed nits from the findings list. If it fails — `git checkout HEAD -- <files>`, `git clean` any new untracked files, and keep the nits in findings. Proceed to Step 8 with whatever findings remain.

Full procedure with the revert/clean bash and pre-commit retry logic: see `reference.md` § "Step 7.5 — Auto-Fix Detection (full procedure)".

---

### Step 7.6: Path M / Defer Enforcement Contract

Before Step 8 writes the review file, the reviewer MUST honor three contracts (F21 root cause: Path M cherry-pick + prose `Defer.` remainder + silent non-blocking acceptance leaking findings between phases):

- **Contract 1 — Path M is ALL findings or NONE.** Path M is a batch gate over all non-blocking + nit findings. Partial application (fix N, defer M-N in prose) is FORBIDDEN. If `>= 1` finding disqualifies any per-finding gate (`lines_changed > 5`, `files_changed > 1`, `total_finding_count > 3`, `total_lines_across_findings > 8`, non-mechanical `Suggestion:`, or any blocker present), the ENTIRE batch routes to **Path B**.
- **Contract 2 — Defer requires a state transition.** A legitimately Defer-class finding MUST get exactly ONE of: (1) `docs/progress.md` `## Deferred` table row (default when unsure), (2) new H2 feature block in the active feature file, (3) task reopen in `progress.md`. Prose `Defer.` with no state transition is a violation.
- **Contract 3 — Silent non-blocking acceptance is FORBIDDEN.** Every non-blocking finding exits review via Path M inline (Contract 1), Path B reopened-task (Step 9), or a Contract-2 Defer transition — never left only in the review-file body.

The contract applies uniformly to Path N, Path M, the F19 teams-on dispatch shape, and the F20 `pipeline-review` slug. Every reviewer subagent reads this before Step 8.

Full contract bodies, the F21 violation symptom, and the three Defer destinations in detail: see `reference.md` § "Step 7.6 — Path M / Defer Enforcement Contract (full body)".

---

### Step 7.8: Charter Scope Classification (if charter present)

Runs after Step 7.5 (Auto-Fix Detection), before Step 8 (Save Review Findings). Strictly post-aggregation: consumes the merged, deduped, auto-fix-finalized findings list and decorates each entry with a `scope_tag` (advisory — `severity` stays the blocking/non-blocking gate). The 5-agent panel composition (Step 6) is untouched. `out_of_scope` findings are auto-appended to `docs/progress.md` § Deferred and dropped before Step 9; `adjacent` findings surface as advisory only; a scope conflict (`CHARTER_SCOPE_CONFLICT`) routes to Path B.

The pre-heredoc shim (`FINDINGS_JSON=`, `REVIEW_FILE_NAME=`), the `charter_classifier` Python heredoc (`classifier_should_skip`, `classify_findings(..., two_axis=True)`, `CHARTER_ABSENT_CLASSIFIER_SKIPPED` skip-log, the `Charter scope adjacent` Summary line), and the full constraint surface: see `reference.md` § "Step 7.8 — Charter Scope Classification (full body)".

The two-axis classification heuristic (scope × intent) and the deployment-target mismatch dimension (Topic 10): see `reference.md` § "Step 7.8 — Two-axis classification worked examples" and § "Step 7.8 — Deployment-target mismatch (Topic 10)".

---

### Step 8: Save Review Findings

Follow the **Versioning Convention** from `~/.claude/rules/workflow.md` for review files.

Include a header in the review file with metadata:
```
**HEAD:** [output of `git rev-parse --short HEAD`]
**Branch:** [output of `git branch --show-current`]
**Date:** [current date]
```
This enables the staleness check in `/ppr` Step 1.5.

Each finding includes:
- Description of the issue
- File:line reference
- Severity: blocking | non-blocking | nit
- Which agent found it (code-reviewer, security-auditor, test-engineer, performance-tuner)
- Which task it relates to (matched by file paths to plan task `Files:` lists)
- **Scope classification:** `in-scope` or `out-of-scope (charter)` (only present when `docs/charter.md` exists)

Note: the `review-vN` in task notes (e.g., `reopened: review-vN`) refers to the version number from the review filename (e.g., `review-v2.md` means N=2). For unversioned `review.md`, use `reopened: review`.

Update `docs/progress.md`: add or update the `**Review:**` pointer to the new review file. Update `**Last updated:**` date.

If all findings were auto-fixed (Step 7.5): still write a review file documenting what was auto-fixed, but do NOT reopen tasks. Proceed to the "No findings" outcome in Step 10.

If no findings at all (all agents returned clean + secret scanner clean): skip this step.

---

### Step 9: Reopen Tasks and Generate Test Specs

For findings that do NOT require scope changes (can be fixed within existing tasks):

1. Identify which task each finding belongs to by matching the files touched to the plan's task `Files:` lists
2. Set that task back to `todo` in `docs/progress.md` with note `reopened: review-vN`
3. **Generate a Review Tests section** for each reopened task and append it to the task's prompt in the prompts file (from the `**Prompts:**` pointer in progress.md). The per-agent derivation rules (test-engineer / code-reviewer / security-auditor / performance-tuner / nit) and the `**Review Tests:**` append format: see `reference.md` § "Step 9 — Review-Tests derivation (per-agent rules)".

4. If a finding doesn't map to any existing task, create a new micro-task entry:
   - Task ID: next available ID in the current phase
   - Name: brief description of what needs fixing
   - Status: `todo`
   - Note: `new: review-vN`
   - **Append a matching task prompt** to the prompts file with:
     - The finding details as the prompt body
     - A **Review Tests:** section (generated using the rules in step 3 above)

   This ensures `/implement-plan` can execute TDD on review-generated tasks.

5. **Nit-level findings that don't map to existing tasks** should also create micro-tasks:
   - Same format as item 4 above
   - Note: `nit: [description]` — these are fixed in the next `/implement-plan` run
   - Review Tests: "N/A — no testable behavior" (nits are style/formatting)

6. **Non-blocking finding contract (from Step 7.6):** Every non-blocking finding NOT auto-fixed by Step 7.5 nit pass and NOT eligible for Path M inline application MUST be one of: (a) mapped to a reopened task per step 1-2 above, (b) given a new micro-task per step 4 above, or (c) propagated to `docs/progress.md` `## Deferred` table per Step 7.6 Contract 2 destination 1. Silent acceptance — leaving the finding only in `review-vN.md` body without a state transition — is a contract violation forbidden by Step 7.6 Contract 3. See Step 7.6 for the full enforcement contract.

If ALL findings require scope changes (none map to existing tasks and all suggest architectural changes): skip this step entirely — tasks will be re-planned via `/create-plan`.

Update `**Last updated:**` in progress.md after all changes.

If no findings: skip this step.

---

### Step 10: What's Next

Output templates for each review outcome are defined in `output-templates.md` (same directory):

- Sanity gate FAILED
- Secrets detected
- Review BLOCKED (all agents failed)
- No findings (or all nits auto-fixed)
- Findings exist, no scope change
- Mixed findings (some fixable, some require scope change)
- Findings require scope change

Select the template matching the outcome and substitute placeholder values (`[N blocking, M non-blocking, P nits]`, `[review filename]`, etc.).

---

## Web/UI review (charter-gated)

When the project's `docs/charter.md` declares `project_type: web` (Charter Topic 4), Step 6 auto-spawns one additional review agent alongside the standard 2/5/5+teams set. The agent rates the diff against seven design dimensions and produces "what would make this a 10" specifications for any dimension scoring below 8. This replaces the legacy `--design-pass` flag — gating is now charter-driven, not flag-driven.

**Categorisation:** findings from this agent use the web/UI categories from the Issue Taxonomy section above (Visual/UI, Functional, UX, Content, Performance, Console/Errors, Accessibility).

The seven scored dimensions (rate 0–10 each), the per-dimension output format, and the six instant-fail hard-rejection patterns: see `reference.md` § "Web/UI review (charter-gated)".
