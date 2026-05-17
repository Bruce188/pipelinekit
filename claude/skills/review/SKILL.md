---
name: review
description: Multi-agent parallel review with auto-scaling agent selection. Scales from 2 agents (small diffs) to 6-agent teams (large diffs). Supports --scope, --health, --force, --teams, and --design-pass.
argument-hint: [--scope <task-id|path>] [--health] [--force] [--teams] [--design-pass]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, Skill
effort: high
---

# Review — Multi-Agent Parallel Review

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

### Categories (web/UI review — used when `--design-pass` is on)

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

### Step 2.5: Health Check (--health only)

Only if `--health` was passed as an argument:

1. Run `/code-health --quick --scope quality,tests` on the project. If `/code-health` fails or is unavailable, note "Health check: unavailable" in the report and continue.
2. Capture the health score and top issues
3. Include in the final report (Step 10) as an additional section:
   ```
   Health: [score]/10 ([quality], [tests])
     [Top 2-3 issues if score < 8.0]
   ```
4. Health results are informational — they do not block or create findings

If `--health` is not present: skip this step.

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

Note: This step can set teams_mode=true independently of Step 5.5 (--teams flag). Either source activates teams mode. The 2,000-line size guard warning (Step 4) and the 5,000-line escalation threshold are separate concerns — both can fire on the same diff.

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

### Step 5.5: Agent Teams Detection (--teams only)

If `teams_mode` is already true (set by Step 4.5 large diff escalation): log "Teams mode already active (large diff escalation)." Skip to Step 6.

If `--teams` argument is present:

1. Save current env var state: `teams_was_set=$CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
2. If env var is not set or not "1": auto-export it for this review run:
   - Set `teams_auto_set=true`
   - Log: "Auto-enabling Agent Teams for --teams flag."
   Note: The `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var controls whether Claude Code's Agent tool uses the teams protocol. Setting it via Bash `export` makes it available to subsequent Agent tool calls within the same session. The cleanup section of Step 7 (sub-item 9) reverts this if auto-set.
3. Set `teams_mode=true`. Log: "Agent Teams mode enabled — agents will communicate during review."
4. If `review_tier=small`: upgrade `review_tier=medium`. Log: "Upgrading from small to medium tier for teams mode."

If `--teams` is NOT present AND `teams_mode` is not already true: set teams_mode=false. Proceed to Step 6.

---

### Step 6: Spawn Review Agents

1. Read `docs/progress.md` -> parse `**Plan:**` field -> read the plan file.
2. Extract: objective, completed tasks, constraints
3. If REVIEW.md was loaded in Step 3a, include its instructions in all agent prompts. If prior findings were loaded in Step 3b, include them as additional context (labeled "Prior review findings — verify if addressed").

**Tier-based agent selection:**

- **If `review_tier=small`:** Spawn only 2 agents:
  - Agent 1 (code-reviewer) — from `agent-prompts.md` § "Agent 1 -- code-reviewer"
  - Agent 5 (spec-tracer) — from `~/.claude/agents/spec-tracer.md`
  Skip security-auditor, test-engineer, performance-tuner, and karpathy-reviewer. These agents add overhead that exceeds their value on small diffs. Note: karpathy-reviewer is deliberately excluded from small tier — see `documentation/review-cost.md` for the cost/detection trade-off rationale.

- **If `review_tier=medium`:** Spawn all 6 agents as independent agents (the 5 existing reviewers + karpathy-reviewer). No changes to existing logic.

- **If `review_tier=large` (teams_mode=true):** Spawn all 6 as named teammates (the 5 existing reviewers + karpathy-reviewer). No changes to existing teams logic.

All selected agents receive the path to $DIFF_FILE (from Step 4) and objective. Launch all selected agents in a single message using the Agent tool (parallel tool calls — up to 6 in medium / large tier). Each agent reads the diff via the Read tool. This avoids duplicating the full diff across agent prompts (~75% token savings).

Note: `teams_mode` can be activated by either `--teams` flag (Step 5.5) or large diff escalation (Step 4.5). Both paths lead to the same team-based review below.

If an agent fails to return structured output or times out, note that agent as "incomplete" and continue collecting results from the remaining agents. Do not block on a single agent failure.

**If teams_mode=true:**

Instead of 5 independent Agent calls, spawn all 5 as named teammates that communicate via SendMessage:
1. Spawn each agent using the Agent tool with a descriptive name ('code-reviewer', 'security-auditor', 'test-engineer', 'performance-tuner', 'spec-tracer', 'karpathy-reviewer') so they can communicate via SendMessage during execution
2. Each agent receives the same prompt as the independent path (below), PLUS this additional instruction at the top:

   > You are part of a review team. As you find issues, share them with your teammates using SendMessage. When you see a teammate's finding that relates to your domain, note the correlation. If a teammate's finding changes your assessment of something, update your analysis.
   >
   > Your teammates: code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer, karpathy-reviewer.
   > Communicate findings as you go — don't wait until you're done.
   >
   > For each finding, include an additional field:
   > - **Correlated by:** [agent names] (if another teammate flagged a related issue)

3. Each agent prompt still includes: objective, REVIEW.md rules (if loaded), prior findings (if re-review), path to $DIFF_FILE
4. Agents self-coordinate: if security-auditor finds an auth issue, test-engineer can check coverage for that path

**If teams_mode=false (default):**

Launch as independent agents (existing behavior below).

Agent prompt templates are defined in `agent-prompts.md` (same directory).
Load the relevant block when spawning each agent.

- **Agent 1 -- code-reviewer:** see `agent-prompts.md` § "Agent 1 -- code-reviewer"
- **Agent 2 -- security-auditor:** see `agent-prompts.md` § "Agent 2 -- security-auditor"
- **Agent 3 -- test-engineer:** see `agent-prompts.md` § "Agent 3 -- test-engineer"
- **Agent 4 -- performance-tuner:** see `agent-prompts.md` § "Agent 4 -- performance-tuner"
- **Agent 5 -- spec-tracer:** prompt defined in `~/.claude/agents/spec-tracer.md`
- **Agent 6 -- karpathy-reviewer:** prompt defined in `~/.claude/agents/karpathy-reviewer.md` (self-contained, like spec-tracer)

**Default model mapping:** Absent a `REVIEW.md` `review-model:` override (see Step 3a), each reviewer runs on the model declared in its agent-file frontmatter. Deep-reasoning reviewers run on opus; pattern-based reviewers drop to sonnet; spec comparison runs on haiku for cost.

| Agent | Default model | Rationale |
|-------|--------------|-----------|
| code-reviewer | opus | Deep reasoning; a single missed issue is expensive |
| security-auditor | opus | Deep reasoning; security misses have high blast radius |
| test-engineer | sonnet | Pattern-based gap-finding that sonnet handles well |
| performance-tuner | sonnet | Pattern-based bottleneck analysis |
| spec-tracer | haiku | Structured diff-vs-objective comparison; ~20× cheaper |
| karpathy-reviewer | opus | Symbol/API resolution requires deep reasoning; false positives are expensive to triage |

When `review-model:` is set in REVIEW.md it applies uniformly to all six agents and bypasses these per-agent defaults (see Step 3a for override semantics).

---

### Step 7: Collect and Deduplicate Results

1. Wait for all spawned agents to complete (2 for small tier, 5 for medium/large tier). Note any that failed/timed out as "incomplete".
2. **Check agent completion:** If ALL spawned agents failed or timed out: **STOP** with "Review BLOCKED — all agents failed. Re-run /review." If some but not all agents failed: proceed with remaining results but include a warning: "WARNING: [N] agent(s) incomplete ([names]). Results may be partial."
3. Merge all findings into a single list
4. Deduplicate: if two agents flag the same file:line, keep the higher severity and combine descriptions
4.5. **Hallucination prose-guard:** for each finding with `category: hallucination` AND `severity: blocking`, Read the cited file at the cited line. If the line is inside a comment (`#`, `//`, `/* */`), docstring (`"""`, `'''`), or markdown prose block, downgrade severity to `non-blocking` and append the note "downgraded by category-hallucination prose guard (cited line is comment/docstring/prose)". One Read per blocking-hallucination finding — cheap, protects against future prompt drift.
5. Sort: blocking first, then non-blocking, then nit
6. Count totals by severity
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

### Step 7.8: Charter Scope Classification (if charter present)

After auto-fix (Step 7.5), before saving findings:

```bash
test -f docs/charter.md && echo "CHARTER_FOUND" || echo "NO_CHARTER"
```

**If `docs/charter.md` is absent:** classify all findings as `in-scope`. Proceed to Step 8 with the combined findings list unchanged.

**If `docs/charter.md` exists:** read sections `## Non-Goals` and `## MVP Boundary`. For each remaining finding in the findings list:

1. If the finding maps to a charter Non-Goal or MVP Boundary `Out` item (partial string match on the finding's description or the file it targets):
   - Classify as `out-of-scope`.
   - Move to the `## Deferred` section in `docs/progress.md` with note: `charter: out of scope (review-vN)`.
   - Do NOT reopen any task for this finding — out-of-scope findings never trigger Path B.

2. Otherwise: classify as `in-scope`. Keep in the findings list.

**Review report structure (when charter present):** the review file written in Step 8 uses two sub-sections:

```
## In-Scope Findings
[findings classified in-scope — these trigger task reopening in Step 9]

## Out-of-Scope Findings (Deferred)
[findings classified out-of-scope — informational only; moved to Deferred]
```

**Task reopening (Step 9) operates only on in-scope findings.** Out-of-scope findings never reopen tasks and never feed into Path B re-implement cycles.

**If `docs/charter.md` is absent:** use a single `## Findings` section (current behavior unchanged).

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

## Optional: --design-pass (UI / web review)

When `--design-pass` is present in the arguments, spawn one **additional** review agent in Step 6 (alongside the standard 2/5/5+teams set). This agent rates the diff against seven design dimensions and produces "what would make this a 10" specifications for any dimension scoring below 8.

**When to use:** the diff touches user-facing pages, components, design tokens, layout/spacing, accessibility attributes, or interaction patterns. Skip for pure backend diffs.

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
