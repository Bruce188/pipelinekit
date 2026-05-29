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

Every finding is classified by **severity** and **category**. Agents emit findings using these labels so the dedupe/triage step can compare apples to apples.

### Severity (universal — code, web, infra, docs)

| Severity | Definition | Examples |
|----------|------------|----------|
| **critical** | Blocks a core workflow, causes data loss, security breach, or crashes the system | Auth bypass, SQL injection, unbounded resource use, secret committed, irreversible destructive op without confirmation |
| **high** | Major functionality broken or unsafe under realistic load — no workaround | Race condition under concurrent writes, missing rollback, leak in long-running daemon, regression in shipped feature |
| **medium** | Works but degrades quality, performance, or maintainability — workaround exists | Missing test for new branch, inefficient O(n²) where O(n) is reachable, error path silently swallowed, public API without docs |
| **low** | Polish, style, micro-optimization, or documentation gap that doesn't block | Inconsistent naming, missing JSDoc on internal helper, log noise, unused import |

### Categories (code review default)

1. **Correctness** — logic errors, off-by-one, wrong operator, missed null/empty case, broken invariants
2. **Security** — auth/authz gaps, injection, secret handling, CSRF/SSRF, dependency CVEs, unsafe deserialisation
3. **Concurrency** — races, deadlocks, missing locks, reordered writes, leaked tasks/promises
4. **Performance** — algorithmic complexity, N+1 queries, blocking I/O on hot paths, memory bloat
5. **Tests** — missing coverage on new logic, brittle assertions, fixtures coupled to impl details, flaky tests
6. **Maintainability** — overgeneralisation, dead code, hidden coupling, magic numbers, missing types
7. **Observability** — silent error paths, missing logs at boundaries, no metrics on new code paths
8. **Documentation** — public API not documented, README out of date, ADRs missing for non-obvious choices

### Categories (web/UI review — used when charter project_type = web)

1. **Visual/UI** — layout breaks, broken images, alignment, dark mode issues
2. **Functional** — broken links, dead buttons, validation bypass, state-not-persisting
3. **UX** — confusing nav, missing loading indicators, unclear errors, dead ends
4. **Content** — typos, lorem ipsum, truncated text, wrong labels
5. **Performance** — slow loads (>3s), jank, layout shift, oversized assets
6. **Console/Errors** — JS exceptions, 4xx/5xx, CORS, mixed content
7. **Accessibility** — missing alt, unlabeled inputs, keyboard nav, focus traps, contrast

> Source: adapted from gstack `qa/references/issue-taxonomy.md`. Severity ladder is universal; category lists are split so backend reviews aren't graded on visual polish and web reviews aren't missed for accessibility.

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

Count review cycles scoped to the **current feature** only, not the whole docs/ directory.
A raw `ls docs/review-v*.md | wc -l` is wrong: historical review files from other features
accumulate and force every subsequent /review to trip the cap.

```bash
BRANCH=$(git branch --show-current)

# Option A: Pipeline-state-scoped count (preferred when pipeline is driving)
if [ -f docs/pipeline-state.md ] && grep -q "^\*\*Review cycles:\*\*" docs/pipeline-state.md; then
  REVIEW_COUNT=$(grep "^\*\*Review cycles:\*\*" docs/pipeline-state.md | sed 's|.*:\*\*[[:space:]]*||' | awk '{print $1}')
else
  # Option B: Branch-scoped count for manual invocations.
  # Parse **Branch:** header in each docs/review-v*.md and count matches.
  # Files missing the Branch: header are NOT counted (fallback: ignore).
  REVIEW_COUNT=0
  for f in docs/review-v*.md; do
    [ -f "$f" ] || continue
    FB=$(grep "^\*\*Branch:\*\*" "$f" | head -1 | sed 's|.*:\*\*[[:space:]]*||')
    if [ "$FB" = "$BRANCH" ]; then
      # Verify HEAD SHA is reachable from current branch (catches stale files
      # from abandoned branches recreated with the same name)
      FH=$(grep "^\*\*HEAD:\*\*" "$f" | head -1 | sed 's|.*:\*\*[[:space:]]*||')
      if [ -n "$FH" ] && ! git merge-base --is-ancestor "$FH" HEAD 2>/dev/null; then
        continue
      fi
      REVIEW_COUNT=$((REVIEW_COUNT + 1))
    fi
  done
fi
```

If `$REVIEW_COUNT` >= 5 AND `--force` is NOT present:
**STOP** with:
> "Review cycle limit reached (5 iterations for this feature). This suggests a scope or design issue rather than incremental fixes.
> Options:
> - Re-plan: /create-plan to restructure the approach
> - Override: /review --force to continue (not recommended — diminishing returns past 5 cycles)
> - Pipeline: /pipeline handles this automatically with re-plan after 5 cycles"

If `--force` IS present:
Log warning: "Review cycle cap overridden with --force. Cycle $REVIEW_COUNT."
Proceed normally.

Notes:
- The count is scoped per-branch/per-feature, never global across the docs/ directory.
- Pipeline invocations use `pipeline-state.md`'s `**Review cycles:**` field as the authoritative count.
- Manual invocations fall back to parsing the `**Branch:**` header in each `docs/review-v*.md`.
- Files missing the `Branch:` header are not counted (legacy files from before Step 8 wrote this header).
- The pipeline's own cap (Step 5.8) still applies and is redundant with this per-feature cap.
- The `--force` flag must never be passed by the pipeline.

---

### Step 2: Sanity Gate

**Verification marker check:** Before running tests, check if `/implement-plan` left a fresh verification marker:

```bash
MARKER="docs/.last-verify.json"
SKIP_SANITY=false

if [ -f "$MARKER" ]; then
  # Parse marker first (cheap file read) before running git status (expensive tree scan)
  HEAD_SHA=$(git rev-parse HEAD)
  MARKER_DATA=$(python3 -c "
import json, datetime, sys
try:
    with open(sys.argv[1]) as f:
        m = json.load(f)
    sha = m.get('commit_sha', '')
    ran_at = m.get('ran_at', '')
    tests = m.get('tests_passed', False)
    build = m.get('build_passed', False)
    if not (isinstance(tests, bool) and tests and isinstance(build, bool) and build):
        print('STALE'); sys.exit(0)
    if sha != sys.argv[2]:
        print('STALE'); sys.exit(0)
    marker_time = datetime.datetime.fromisoformat(ran_at)
    now = datetime.datetime.now(datetime.timezone.utc)
    # Writer always produces UTC; handle naive as UTC defensively
    if marker_time.tzinfo is None:
        marker_time = marker_time.replace(tzinfo=datetime.timezone.utc)
    age_seconds = (now - marker_time).total_seconds()
    if age_seconds > 600:
        print('STALE'); sys.exit(0)
    print(f'VALID {sha[:7]} {ran_at[:19]}')
except Exception:
    print('STALE')
" "$MARKER" "$HEAD_SHA" 2>/dev/null)

  if [[ "$MARKER_DATA" == VALID* ]]; then
    # Only trust the marker if there are no uncommitted tracked changes
    if [ -z "$(git status --porcelain -uno)" ]; then
      SKIP_SANITY=true
      read -r _ SANITY_SHA SANITY_TIME <<< "$MARKER_DATA"
    fi
  fi
  rm -f "$MARKER"
fi
```

**Trust assumption:** both writer and reader run in the same local Claude session. The marker is a plain JSON file with no integrity protection (no HMAC/signature). It provides no defense against external file tampering — only against redundant test runs within a single pipeline invocation.

If `$SKIP_SANITY` is true: log `"Verification inherited from implement: $SANITY_SHA at $SANITY_TIME. Sanity gate skipped."` and skip the rest of Step 2. In the final report (Step 10), replace "Sanity gate: passed" with "Sanity gate: inherited from implement ($SANITY_SHA at $SANITY_TIME)".

If `$SKIP_SANITY` is false: proceed with the existing sanity gate logic below.

Quick test run to catch obvious breakage. This is NOT a full test suite — just a fast smoke test. Prefer a dedicated smoke test script if available (e.g., `npm run test:smoke`, `pytest -m smoke`). Project-specific REVIEW.md can specify the test command.

**Python:**
```bash
pytest --tb=line -q --no-header -x 2>&1; TEST_EXIT=$?
# Show last 5 lines of output for context, then check exit code
if [ $TEST_EXIT -ne 0 ]; then echo "SANITY_GATE_FAILED"; fi
```

**Node.js:**
```bash
# Check if a test script exists before running
if node -e "const p=require('./package.json'); if(!p.scripts||!p.scripts.test||p.scripts.test.includes('no test specified')) process.exit(1)" 2>/dev/null; then
  npm test 2>&1; TEST_EXIT=$?
else
  echo "No test script configured — skipping sanity gate"; TEST_EXIT=0
fi
if [ $TEST_EXIT -ne 0 ]; then echo "SANITY_GATE_FAILED"; fi
```

**C# / .NET:**
```bash
dotnet test --no-build -v q --nologo 2>&1; TEST_EXIT=$?
if [ $TEST_EXIT -ne 0 ]; then echo "SANITY_GATE_FAILED"; fi
```

Check `$TEST_EXIT` (not the pipe exit code). If non-zero: stop immediately. Do NOT spawn agents. Output the "Sanity gate FAILED" block (see Step 10).

If no test framework is detected: warn and proceed. Output "Sanity gate: skipped (no test framework detected)" in the final report instead of "passed."

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

**If teams_mode=true:**

Instead of 5 independent Agent calls, spawn all 5 as named teammates that communicate via SendMessage:
1. Spawn each agent using the Agent tool with a descriptive name ('code-reviewer', 'security-auditor', 'test-engineer', 'performance-tuner', 'spec-tracer', 'symbol-verifier') so they can communicate via SendMessage during execution
2. Each agent receives the same prompt as the independent path (below), PLUS this additional instruction at the top:

   > You are part of a review team. As you find issues, share them with your teammates using SendMessage. When you see a teammate's finding that relates to your domain, note the correlation. If a teammate's finding changes your assessment of something, update your analysis.
   >
   > Your teammates: code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer, symbol-verifier.
   > Communicate findings as you go — don't wait until you're done.
   >
   > For each finding, include an additional field:
   > - **Correlated by:** [agent names] (if another teammate flagged a related issue)

3. Each agent prompt still includes: objective, REVIEW.md rules (if loaded), prior findings (if re-review), path to $DIFF_FILE
4. Agents self-coordinate: if security-auditor finds an auth issue, test-engineer can check coverage for that path

#### Teams dispatch shape — MANDATORY

When `teams_mode=true`, the lead MUST dispatch the base reviewer set as **exactly N `Agent` tool calls in a single assistant turn**, where N is the count of selected reviewer agents (5 for the base panel, +1 if `symbol-verifier` is included). The base agent types are, verbatim:

- `code-reviewer`
- `security-auditor`
- `test-engineer`
- `performance-tuner`
- `spec-tracer`

Optional additions per Step 6 tier rules: `symbol-verifier` (medium / large tier). When included, it counts toward the bundle and the single-turn rule applies to it too.

**Correct shape (worked example, 5-agent base panel):**

```
<one assistant turn>
  Agent(name='code-reviewer',     prompt=…, model=opus)
  Agent(name='security-auditor',  prompt=…, model=opus)
  Agent(name='test-engineer',     prompt=…, model=sonnet)
  Agent(name='performance-tuner', prompt=…, model=sonnet)
  Agent(name='spec-tracer',       prompt=…, model=haiku)
</one assistant turn>
```

All five `Agent` invocations live inside a single assistant message — the harness fans them out concurrently, each in its own context window, each with its own specialist prompt from `agent-prompts.md`. Serial turns or wrapping-as-one are contract violations.

**Contract violations (do NOT do any of these):**

1. **Wrap-as-one-Agent.** Dispatch a SINGLE generic `Agent` (e.g. `Agent(name='F<N> review', prompt='do a 5-perspective review')`) that runs all five perspectives inside one subagent's context. This forfeits parallelism, forfeits per-role specialist prompts, and forfeits inter-agent context isolation. The single subagent runs ~5× the tool calls and produces a flat single-voice review. **This is a contract violation.**
2. **One-per-turn serial dispatch.** Dispatch `code-reviewer` alone in one assistant turn, then `security-auditor` alone in the next turn, then `test-engineer` alone in the next, and so on. Each individual call IS a real specialist dispatch — but the assistant turns are serial, so the harness runs them sequentially instead of concurrently. Total wall time is ~5× the bundled shape. **This is a contract violation.**
3. **Fall-back-to-inline.** When dispatch feels expensive, "just run /pipeline-review quickly to wrap up" by invoking the `Skill: pipeline-review` tool inline OR by reading the diff and emitting findings directly. This skips the entire teams-mode contract: no specialist roles, no parallel execution, no Step 6 dispatch shape at all. **This is a contract violation** (see also `claude/skills/pipeline/SKILL.md` § Phase Mode Precedence — direct `Skill: pipeline-review` invocations are forbidden when Phase Mode is `subagent`).

**Background:** F6 of castellum branch `test/taxii-misp-self-hosted-smoke` (2026-05-26, 560-line diff, teams-on per heuristic) exhibited all three violations sequentially in the same lead session: wrap-as-one → one-per-turn → recovery only on second user nudge. This subsection exists to give the lead a pattern-match surface against those specific failures.

**Cross-reference:** the generic parallelism reminder lives in `~/.claude/rules/agents-worktrees.md` § Subagent Defaults. This subsection is the teams-on review-specific instantiation of that rule.

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

**Default model mapping:** Absent a `REVIEW.md` `review-model:` override (see Step 3a), each reviewer runs on the model declared in its agent-file frontmatter. Deep-reasoning reviewers run on opus; pattern-based reviewers drop to sonnet; spec comparison runs on haiku for cost.

| Agent | Default model | Rationale |
|-------|--------------|-----------|
| code-reviewer | opus | Deep reasoning; a single missed issue is expensive |
| security-auditor | opus | Deep reasoning; security misses have high blast radius |
| test-engineer | sonnet | Pattern-based gap-finding that sonnet handles well |
| performance-tuner | sonnet | Pattern-based bottleneck analysis |
| spec-tracer | haiku | Structured diff-vs-objective comparison; ~20× cheaper |
| symbol-verifier | opus | Symbol/API resolution requires deep reasoning; false positives are expensive to triage |

When `review-model:` is set in REVIEW.md it applies uniformly to all six agents and bypasses these per-agent defaults (see Step 3a for override semantics).

---

### Step 6.5: Skill-Compliance Gates

Three pipelinekit-canonical gates that catch skill-overreach, hook-observability holes, and documentation-richness regressions before they merge. Gates fire only when the diff touches the matching file types — no repo-wide scans — and produce findings inside the existing review output schema (Step 7 dedup applies uniformly). Gates are not user-configurable; their thresholds live in `claude/skills/review/check-skill-compliance.sh`.

**Gate (a) — Skill-paths-or-allowlist (blocking).** Every `claude/skills/<name>/SKILL.md` in the diff must either declare `paths:` in its YAML frontmatter (scoping the directories where the skill applies) or appear in the 4-entry allowlist at `docs-source/skills-scope-policy.md § Global-by-design allowlist`. Catches skills that silently apply globally.

**Gate (b) — Hook denial-tracker (non-blocking).** Every `claude/hooks/*.{sh,py}` in the diff (excluding `tests/` and helper files prefixed with `_`) must either call `denial_tracker` (via `python3 claude/hooks/denial_tracker.py`, matching the pattern in `claude/hooks/block-stage-sensitive.sh`) or carry an opt-out comment `# denial_tracker:no <reason>` near the top of the file. Catches hooks that deny silently without telemetry.

**Gate (c) — Docs richness (blocking).** Every changed `docs-source/<name>.md` must have a corresponding rendered `documentation/<name>.html` that passes `python3 claude/skills/docs-writer/richness_check.py <html-path>` (positional invocation). The source may carry `<!-- richness-exempt: <reason> -->` to skip. Missing HTML → blocking "render via docs-writer" finding (`gate-c-missing-render` sub-case). Failing richness → blocking finding with suggested remediation.

**Invocation:** the review subagent runs `bash claude/skills/review/check-skill-compliance.sh` and captures stdout. Each block of `**File:** … **Severity:** … **Issue:** … **Suggestion:** … **Scope:** … **Intent:**` is treated as one finding and merged into the review output schema unchanged.

**Exit codes:** 0 = zero findings, 1 = at least one blocking, 2 = non-blocking only. Non-blocking findings flow through Path M when small + mechanical; blocking findings route through Path B.

**Full script:** `claude/skills/review/check-skill-compliance.sh`.

**Smoke test:** `bash claude/skills/review/tests/test_skill_compliance_gates.sh`.

#### Step 6.5.5: Docs Richness Verification (corpus-level)

When `git diff $BASE...HEAD --name-only | grep -qE '^docs-source/.*\.md$|^documentation/.*\.html$'` returns non-empty, additionally invoke:

```bash
python3 claude/skills/docs-writer/richness_check.py --staged
```

This runs the richness check across the entire `documentation/*.html` corpus picked up by `--staged` (which reads `git diff --cached --name-only --diff-filter=ACMR` filtered to `documentation/*.html`). Distinct from Gate (c) per-file invocation — `--staged` produces one verdict per touched HTML file in a single subprocess call.

**Exit code semantics:** 0 → all pass, 1 → at least one failure. Non-zero exit produces a blocking review finding.

---

### Step 7: Collect and Deduplicate Results

1. Wait for all spawned agents to complete (2 for small tier, 5 for medium/large tier). Note any that failed/timed out as "incomplete".
2. **Check agent completion:** If ALL spawned agents failed or timed out: **STOP** with "Review BLOCKED — all agents failed. Re-run /review." If some but not all agents failed: proceed with remaining results but include a warning: "WARNING: [N] agent(s) incomplete ([names]). Results may be partial."
3. Merge all findings into a single list
4. Deduplicate: if two agents flag the same file:line, keep the higher severity and combine descriptions
4.5. **Hallucination prose-guard:** for each finding with `category: hallucination` AND `severity: blocking`, Read the cited file at the cited line. If the line is inside a comment (`#`, `//`, `/* */`), docstring (`"""`, `'''`), or markdown prose block, downgrade severity to `non-blocking` and append the note "downgraded by category-hallucination prose guard (cited line is comment/docstring/prose)". One Read per blocking-hallucination finding — cheap, protects against future prompt drift.
5. Sort: blocking first, then non-blocking, then nit
6. Count totals by severity
6.4. For findings requiring multi-step severity/correctness reasoning (e.g. a borderline blocking-vs-non-blocking call, or a correctness claim that hinges on a chain of preconditions), call `mcp__sequential-thinking__sequentialthinking` to structure the reasoning before finalizing the severity. Skip silently when sequential-thinking is unavailable.
6.5. **Cross-feature intel collection:**
   a. Scan each agent's output for "**Cross-Feature Intel:**" sections.
   b. For each intel note found, construct a JSON entry:
      ```json
      {
        "from_feature": "[current feature name — read from docs/pipeline-state.md **Name:** field, or from plan objective if not in pipeline mode]",
        "target_feature": "[from agent's Target: field]",
        "target_keywords": ["from agent's Keywords: field, split by comma and trimmed"],
        "severity": "[from agent's Severity: field]",
        "note": "[from agent's Note: field]",
        "discovered_at": "[current ISO 8601 timestamp]",
        "discovered_by": "[agent name, e.g., security-auditor]",
        "consumed_by": null,
        "consumed_at": null
      }
      ```
   c. Read `docs/pipeline-intel.json` (create as empty array `[]` if file does not exist).
   d. Append new entries to the array and write back to `docs/pipeline-intel.json`.
   e. Log: "Cross-feature intel: [N] notes captured for [comma-separated target features/keywords]"
   f. If no intel notes found in any agent output: skip silently (no log, no file write).
7. If teams_mode was true:
   - Agents may have already self-deduplicated via communication. Still run dedup (step 4 above) as a safety net.
   - Preserve "Correlated by:" fields — these show cross-agent insights that independent review would miss.
   - In the summary, note: "Review mode: Agent Teams (collaborative)"
8. Clean up the temp diff file: `rm -f "$DIFF_FILE"`
9. If `teams_auto_set` is true and `teams_was_set` was not '1': unset `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.

---

### Step 7.5: Auto-Fix Detection

After collecting and deduplicating findings (Step 7):

1. Separate findings by severity: blocking, non-blocking, nit
2. If no nit findings exist: skip this step entirely, proceed to Step 8.
3. If nit findings exist (regardless of other severities):
   a. Only apply fixes to files referenced by nit findings. If `--scope` is set or `auto_scope_files` is active, additionally verify each nit's file falls within that scope before applying.
   b. Before applying fixes, record the existing tracked files:
      ```bash
      EXISTING_FILES=$(git ls-files)
      ```
   c. Apply nit fixes inline using the Edit tool. Only apply to findings explicitly tagged `severity: nit` — never auto-fix non-blocking or blocking.
   d. Re-run the sanity gate (Step 2) after all nit fixes
   e. If sanity gate passes:
      1. Stage the fixed files by name (not `git add -A`). **Never stage** protected files — see canonical list in `~/.claude/rules/workflow.md` § "Never stage". The `block-stage-sensitive.sh` hook enforces this automatically.
      2. Commit: `git commit -m "fix: minor code quality improvements"`
      3. If pre-commit hook fails: fix the issue and retry (max 2 retries). If still failing: revert nit fixes (step 3.f below) and keep nits in findings.
      4. Remove auto-fixed nit findings from the findings list
   f. If sanity gate fails: revert nit fixes:
      1. `git checkout HEAD -- <files>` for each modified file
      2. Remove any files that were created during the fix but not in $EXISTING_FILES:
         ```bash
         for f in $(git ls-files --others --exclude-standard); do
           echo "$EXISTING_FILES" | grep -qxF "$f" || git clean -f -- "$f"
         done
         ```
      3. Keep nit findings in the findings list
4. If zero findings remain after auto-fix (all were nits, all fixed): continue to Step 8 which handles the auto-fix-only path.
5. Otherwise: continue to Step 8 (save review findings) with remaining findings.

No flag needed — nit auto-fix always runs when nits are present.

---

### Step 7.6: Path M / Defer Enforcement Contract

Before Step 8 writes the review file, the reviewer MUST honor three contracts that close the F21 root-cause failure mode: Path M cherry-pick + prose `Defer.` remainder + silent non-blocking acceptance leaking findings between phases.

**Contract 1 — Path M is ALL findings or NONE.**

Path M (per `~/.claude/rules/workflow.md` § "Path M gate examples") is a batch gate. When Path M qualifies, it applies to ALL non-blocking + nit findings in the batch — or to NONE. Partial Path M (apply the N qualifying findings inline + defer the M-N remainder in prose) is FORBIDDEN. When `>= 1` finding disqualifies any Path M per-finding gate (`lines_changed > 5`, `files_changed > 1`, `total_finding_count > 3`, `total_lines_across_findings > 8`, non-mechanical `Suggestion:`, or any blocker present), the ENTIRE batch routes to Path B for re-implement subagent dispatch.

Symptom of violation: review file shows N findings, commit applies fixes to a subset K < N, remaining N-K findings carry `Defer.` / `Out of scope.` / `bundle with ...` prose annotations with no state transition out of the review file. This is the failure pattern documented in castellum F6 review-v40.md (2026-05-26, F21 root cause). The pipeline accepted the Path M outcome, advanced to `/ppr`, and merged a PR while 16 findings (10 non-blocking + 6 nits) lived only in the review file body — invisible to `/pipeline --renew`, `/create-plan` Deferred consumption, and `progress.md` readers.

**Contract 2 — Defer requires a state transition.**

When a finding is legitimately Defer-class (truly out-of-scope, future iteration, multi-line documentation polish bundling with a follow-up PR), the reviewer MUST perform exactly ONE of the following three state transitions per deferred finding. Prose `Defer.` without a state transition is a contract violation.

The three legitimate Defer destinations:

1. **`docs/progress.md` `## Deferred` table row** — append a row of the shape `| <finding-id-or-short-name> | review-vN.md | <reason> | <target-iteration> |` to the active `progress.md`'s `## Deferred` table. Create the table if absent. This is the cheapest and most visible destination — default to it when unsure.
2. **New feature block in the active feature file** — append a new H2 feature block (matching the existing feature-file schema) to the in-flight feature file (the one driving the current pipeline run; see `~/.claude/memory/feedback-pipeline-feature-add-to-running-file.md` when present). Suitable when the deferred work is non-trivial and merits its own future feature.
3. **Task reopen in `progress.md`** — set the closest matching task back to `todo` with note `reopened: review-vN` and add the finding's remediation guidance to the task's prompt body in the prompts file (the standard Step 9 task-reopen flow). Suitable when the deferred work belongs to an existing task that simply needs a follow-up touch.

**Contract 3 — Silent non-blocking acceptance is FORBIDDEN.**

A non-blocking finding that exits review without ONE of: (a) Path M inline-applied (under Contract 1's all-or-none rule), (b) Path B reopened-task (Step 9 standard flow), (c) Defer state transition per Contract 2 above, is dropped silently between phases. This is a contract violation. The reviewer MUST route every non-blocking finding through one of the three actionable surfaces before exiting Step 8. If unsure, default to Defer destination 1 (`progress.md` `## Deferred` row) — the table is cheap and visible to `/pipeline --renew` / `/create-plan` consumption.

The same contract applies uniformly to inline Path N (Edit-tool nit), Path M (Edit-tool mini-fix), the F19 teams-on dispatch shape, and the F20 `pipeline-review` slug. Every reviewer subagent reads this section before Step 8.

---

### Step 7.8: Charter Scope Classification (if charter present)

This classifier runs after Step 7.5 (Auto-Fix Detection) and before Step 8 (Save Review Findings). The call is strictly post-aggregation: it consumes the merged, deduped, auto-fix-finalized findings list and decorates each entry with a `scope_tag`. The 5-agent panel composition (Step 6) is untouched — no agent prompts, agent count, or agent communication semantics change.

**Pre-heredoc shim — initialize shell variables:**

Before running the Python classifier, create a temp file for the findings JSON and pre-compute the next review filename using the Versioning Convention from `~/.claude/rules/workflow.md`. Both variables must be set before the heredoc fires; without them `sys.argv[1]`/`sys.argv[2]` are empty strings and the `open()` calls inside the script crash.

```bash
# Create a temp file for the findings JSON.
FINDINGS_JSON=$(mktemp --suffix=.json)
# Write the in-memory findings list (built in Step 7) directly to $FINDINGS_JSON
# as a JSON array. No shell-variable indirection is required — the executor
# writes the file directly from the in-memory list.

# Pre-compute the next review filename per the Versioning Convention.
# Find the highest existing review-vN.md in docs/ and increment by 1.
_REVIEW_N=$(ls docs/review-v*.md 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1 || echo 0)
REVIEW_FILE_NAME="review-v$((_REVIEW_N + 1)).md"
```

Then invoke the classifier:

```bash
python3 - "$FINDINGS_JSON" "$REVIEW_FILE_NAME" <<'PYEOF'
import json, sys
from claude.lib.pipeline import charter_classifier

skip, log = charter_classifier.classifier_should_skip()
if skip:
    print(log, file=sys.stderr)
    sys.exit(0)

with open(sys.argv[1]) as f:
    findings = json.load(f)
with open("docs/charter.md") as f:
    charter_text = f.read()

try:
    decorated = charter_classifier.classify_findings(findings, charter_text, two_axis=True)
except charter_classifier.CharterScopeConflictError as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(2)  # orchestrator routes exit code 2 → Path B re-spawn

charter_classifier.append_out_of_scope_to_deferred(
    "docs/progress.md", decorated, sys.argv[2]
)

# Drop out-of-scope findings from the in-memory list so Step 9 does
# not reopen tasks for them (analysis-v25 § 8). They remain in
# review-vN.md for the audit trail.
surviving = [f for f in decorated if f.get("scope") != "out"]

# Surface adjacent count in the Summary block of the review file.
adjacent_count = sum(1 for f in decorated if f.get("scope") == "adjacent")
if adjacent_count:
    print(f"ADJACENT_COUNT={adjacent_count}", file=sys.stderr)

with open(sys.argv[1], "w") as f:
    json.dump(surviving, f)
PYEOF

# Read the surviving findings list back from the file (Step 8 uses it).
# The executor reads $FINDINGS_JSON to get the decorated, filtered findings.
rm -f "$FINDINGS_JSON"
```

**Constraint surface:**

- The classifier is **advisory** — the existing `severity` column on review-vN.md remains the gate for blocking/non-blocking. `scope` and `intent` are decoration alongside severity, not a replacement for it.
- `scope_creep` raises a flag, never blocks. The review file's `## Summary` section gains a line: `Charter scope-creep flag: <N> finding(s) — consider /pipeline --renew or charter amendment`. The orchestrator (`/pipeline`) is the consumer; this step does not auto-edit the charter or auto-replan.
- `out_of_scope` (new: `scope == "out"`) findings are auto-appended to `docs/progress.md` § Deferred via `append_out_of_scope_to_deferred` and dropped from the in-memory findings list before Step 9 runs, so Step 9 never reopens tasks for them. They are still written to `review-vN.md` for the audit trail.
- `adjacent` findings (`scope == "adjacent"`) surface as advisory only. When `adjacent_count > 0`, the review file `## Summary` gains: `Charter scope adjacent: <N> finding(s) — advisory only`. Adjacent findings are NEITHER deferred NOR routed through Path B.
- When `classifier_should_skip` trips (no progress.md, no `**Charter:**` line, pointer literal `(none)`, or pointer references a missing file), the canonical log line `CHARTER_ABSENT_CLASSIFIER_SKIPPED: <reason>` is printed to stderr, the review file is written with its current charter-unaware schema, and `progress.md` § Deferred is not touched.
- When reviewer-emitted `scope=in` contradicts the token-overlap classifier (`out_of_scope` or `scope_creep`), `CharterScopeConflictError` is raised and the canonical token `CHARTER_SCOPE_CONFLICT: finding "<snippet>" tagged scope=in by reviewer but classifier returns <tag>` is printed to stderr. Review-file write is skipped; orchestrator routes exit code 2 to Path B re-spawn.

#### Two-axis classification heuristic

Each finding carries TWO independent tags:

- **scope** ∈ `{in, out, adjacent}` — relationship to charter Goal / MVP Boundary / Non-Goals.
- **intent** ∈ `{correctness, polish, design, unrelated}` — the *kind* of issue (independent of severity).

Severity (blocking / non-blocking / nit) remains the routing gate. `scope` + `intent` are decoration; they do NOT determine Path A/B/M/N selection.

Worked examples:

1. **correctness in-scope** — `{scope: in, intent: correctness}`: off-by-one in the async runtime hardening logic the feature ships. Severity `blocking`. Auto-reopens task via Step 9.
2. **polish adjacent** — `{scope: adjacent, intent: polish}`: a naming consistency tweak near the new module but in a sibling file. Surfaced as Run Log advisory; not deferred, not routed through Path B.
3. **design out** — `{scope: out, intent: design}`: a suggestion to introduce a new DB adapter (charter Non-Goal). Auto-deferred with Reason `out-of-scope of charter (review-vN) (intent: design)`.
4. **unrelated out** — `{scope: out, intent: unrelated}`: a typo fix in an untouched documentation file. Auto-deferred with Reason `out-of-scope of charter (review-vN)` (no intent suffix when intent=unrelated).

If reviewer emits `scope=in` but the token-overlap classifier returns `out_of_scope` or `scope_creep`, `CHARTER_SCOPE_CONFLICT` is raised and the review-file write is skipped — the orchestrator routes to Path B for re-review.

#### Deployment-target mismatch (Topic 10)

When charter Topic 10 declares a concrete deployment target (one of
`vercel`, `railway`, `render`, `digitalocean`, `azure`, `aws`, `gcp`),
the classifier additionally demotes findings that name a *different*
provider to `scope: "out"`. A `deployment_target` value of `none` (or
a missing section) skips this dimension — generic findings are NOT
demoted.

Provider-token lookup table (matches `DEPLOYMENT_PROVIDER_TOKENS` in
`claude/lib/pipeline/charter_classifier.py`):

| Provider | Token phrases | Example mismatch finding |
|----------|---------------|--------------------------|
| `vercel` | `vercel`, `vercel.json`, `edge function(s)`, `vercel deploy`, `vercel cli` | "Vercel cold-start latency exceeds 800ms" |
| `railway` | `railway`, `railway.toml`, `railway up`, `railway cli` | "Railway healthcheck flaps under load" |
| `render` | `render`, `render.yaml`, `render service` | "Render service restart loop on OOM" |
| `digitalocean` | `digitalocean`, `digital ocean`, `doctl`, `.do/app.yaml`, `do droplet` | "DigitalOcean droplet provisioning timeout" |
| `azure` | `azure`, `azure functions`, `azure app service`, `az cli`, `bicep`, `arm template` | "Azure functions cold-start latency spike" |
| `aws` | `aws lambda`, `aws s3`, `aws cloudformation`, `aws sam`, `aws iam`, `aws cdk`, `amazon s3`, `amazon ec2` | "AWS Lambda timeout exceeds 15 min cap" |
| `gcp` | `gcp`, `google cloud`, `cloud run`, `cloud functions`, `gcloud`, `firebase hosting` | "Cloud Run revision rollback fails" |

Worked example: charter Topic 10 = `vercel`. Reviewer emits a finding
`"Azure functions cold-start latency spike"`. The classifier checks
the token set against `DEPLOYMENT_PROVIDER_TOKENS["azure"]`, matches
on `azure functions`, observes the charter provider is `vercel`
(different), and tags the finding `scope: "out"`. The Deferred append
then records it with Reason `out-of-scope of charter (review-vN)`.

Conflict path: if the reviewer pre-emits `scope: "in"` on the same
Azure-named finding under a Vercel charter, the classifier raises
`CharterScopeConflictError` and the orchestrator routes to Path B
re-review (identical to the existing scope-conflict path).

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
3. **Generate a Review Tests section** for each reopened task and append it to the task's prompt in the prompts file (from the `**Prompts:**` pointer in progress.md):
   - test-engineer findings: use the finding's **Suggestion:** directly as the test spec (it already describes what test to write)
   - code-reviewer findings (logic errors, correctness): derive a test that would catch the reported issue — specify test name, file, and key assertion
   - security-auditor findings: derive a test that exercises the vulnerable path and asserts secure behavior (e.g., `test_rejects_sql_injection_in_username`)
   - performance-tuner findings: derive a benchmark or assertion if measurable (e.g., `test_batch_query_executes_single_db_call`), otherwise note "N/A — not unit-testable"
   - Nit-level findings (style, naming, formatting): note "N/A — no testable behavior"

   Format appended to the existing task prompt:
   ```
   **Review Tests:** [test file]: [test_name_1] — [assertion], [test_name_2] — [assertion]
   ```

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

### The seven dimensions (rate 0–10 each)

| # | Dimension | What "10" looks like |
|---|-----------|---------------------|
| 1 | **Information architecture** | Page/screen defines what user sees first / second / third. Navigation flow is explicit. "If you can only show 3 things, which 3?" answered. |
| 2 | **Interaction state coverage** | Every UI feature specifies loading, empty, error, success, partial. Empty states have warmth, primary action, context — they're features, not blanks. |
| 3 | **User journey & emotional arc** | Storyboard exists: STEP / USER DOES / USER FEELS / SUPPORTED-BY columns. 5-sec visceral, 5-min behavioral, 5-year reflective horizons addressed. |
| 4 | **Visual specificity** | UI descriptions are specific to *this* product, not generic "cards with icons" or "clean modern UI". No AI-slop patterns: no purple-blue gradients, no symmetric 3-column icon-circle grids, no centered-everything, no decorative blobs, no icons-in-colored-circles, no system-ui as primary display font. |
| 5 | **Accessibility** | Keyboard nav patterns explicit, ARIA landmarks named, touch targets ≥ 44px, body text ≥ 16px with contrast ≥ 4.5:1, visited/unvisited link distinction preserved. |
| 6 | **Design-system alignment** | If a `DESIGN.md` exists, every new component cites tokens/components from it. New components flagged when they expand the vocabulary. If no DESIGN.md, the gap is flagged as a separate finding. |
| 7 | **Spacing & rhythm** | Section-to-section rhythm intentional, not the cookie-cutter hero → 3 features → testimonials → pricing → CTA at uniform heights. Heading proximity correct (heading visually closer to its section than to the preceding one). |

### Output format (per dimension)

```
**Dimension N — [name]: <score>/10**
- What's missing: [concrete gap]
- What 10 would look like: [specific change]
- Severity if shipped as-is: [critical|high|medium|low]
- Category: [from web/UI taxonomy above]
```

### Hard rejection patterns (instant-fail — flag any of these as `critical`)

1. Generic SaaS card grid as the first impression
2. Strong headline with no clear action / CTA
3. Beautiful image with weak brand presence
4. Carousel with no narrative purpose
5. App UI built from stacked decorative cards instead of a layout
6. Placeholder-as-label form pattern (label disappears once user types)

> Source: adapted from gstack `plan-design-review/SKILL.md` Pass 1–7 + design hard rules. Distilled to seven dimensions per the "More to Steal" framework.
