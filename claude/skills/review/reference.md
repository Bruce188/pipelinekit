# Pipeline-Review — Reference Appendix

Material the `pipeline-review` skill consults but does not execute inline.
`SKILL.md` keeps the executable step flow; the verbose taxonomies, worked
examples, and rationale prose live here. Each `SKILL.md` pointer names the
heading below it is deferring to.

---

## Issue Taxonomy

Referenced from `SKILL.md` (top-of-file pointer) and Step 6 / Step 7. Every
finding is classified by **severity** and **category** so the dedupe/triage
step can compare apples to apples.

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

## Step 7.8 — Charter Scope Classification (full body)

Referenced from `SKILL.md` Step 7.8. This classifier runs after Step 7.5 (Auto-Fix Detection) and before Step 8 (Save Review Findings). The call is strictly post-aggregation: it consumes the merged, deduped, auto-fix-finalized findings list and decorates each entry with a `scope_tag`. The 5-agent panel composition (Step 6) is untouched — no agent prompts, agent count, or agent communication semantics change.

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

The `scope_tag` decoration each finding carries is consumed downstream by Step 8 (Save Review Findings, the `**Scope classification:**` field) and Step 9 (task reopening — `out` findings are filtered out before reopen).

---

## Step 7.8 — Two-axis classification worked examples

Referenced from `SKILL.md` Step 7.8 § "Two-axis classification heuristic".
The executable classifier invocation and the `scope` / `intent` axis
definitions live in this reference file (§ "Step 7.8 — Charter Scope
Classification (full body)" above); the worked examples below are
illustrative.

Each finding carries TWO independent tags:

- **scope** ∈ `{in, out, adjacent}` — relationship to charter Goal / MVP Boundary / Non-Goals.
- **intent** ∈ `{correctness, polish, design, unrelated}` — the *kind* of issue (independent of severity).

Severity (blocking / non-blocking / nit) remains the routing gate. `scope` +
`intent` are decoration; they do NOT determine Path A/B/M/N selection.

Worked examples:

1. **correctness in-scope** — `{scope: in, intent: correctness}`: off-by-one in the async runtime hardening logic the feature ships. Severity `blocking`. Auto-reopens task via Step 9.
2. **polish adjacent** — `{scope: adjacent, intent: polish}`: a naming consistency tweak near the new module but in a sibling file. Surfaced as Run Log advisory; not deferred, not routed through Path B.
3. **design out** — `{scope: out, intent: design}`: a suggestion to introduce a new DB adapter (charter Non-Goal). Auto-deferred with Reason `out-of-scope of charter (review-vN) (intent: design)`.
4. **unrelated out** — `{scope: out, intent: unrelated}`: a typo fix in an untouched documentation file. Auto-deferred with Reason `out-of-scope of charter (review-vN)` (no intent suffix when intent=unrelated).

If reviewer emits `scope=in` but the token-overlap classifier returns `out_of_scope` or `scope_creep`, `CHARTER_SCOPE_CONFLICT` is raised and the review-file write is skipped — the orchestrator routes to Path B for re-review.

---

## Step 7.8 — Deployment-target mismatch (Topic 10)

Referenced from `SKILL.md` Step 7.8 § "Deployment-target mismatch (Topic 10)".

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

## Web/UI review (charter-gated)

Referenced from `SKILL.md` Step 6 and the end-of-file pointer.

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

---

## Step 6.5 — Skill-Compliance Gates (gate detail)

Referenced from `SKILL.md` Step 6.5. The executable invocation, exit-code
routing, and the three-row gate summary stay inline in Step 6.5; the per-gate
catch-rationale and parse shape live here.

**Gate (a) — Skill-paths-or-allowlist (blocking).** Every `claude/skills/<name>/SKILL.md` in the diff must either declare `paths:` in its YAML frontmatter (scoping the directories where the skill applies) or appear in the 4-entry allowlist at `docs-source/skills-scope-policy.md § Global-by-design allowlist`. Catches skills that silently apply globally.

**Gate (b) — Hook denial-tracker (non-blocking).** Every `claude/hooks/*.{sh,py}` in the diff (excluding `tests/` and helper files prefixed with `_`) must either call `denial_tracker` (via `python3 claude/hooks/denial_tracker.py`, matching the pattern in `claude/hooks/block-stage-sensitive.sh`) or carry an opt-out comment `# denial_tracker:no <reason>` near the top of the file. Catches hooks that deny silently without telemetry.

**Gate (c) — Docs richness (blocking).** Every changed `docs-source/<name>.md` must have a corresponding rendered `documentation/<name>.html` that passes `python3 claude/skills/docs-writer/richness_check.py <html-path>` (positional invocation). The source may carry `<!-- richness-exempt: <reason> -->` to skip. Missing HTML → blocking "render via docs-writer" finding (`gate-c-missing-render` sub-case). Failing richness → blocking finding with suggested remediation.

**Finding parse shape:** the review subagent runs `bash claude/skills/review/check-skill-compliance.sh` and captures stdout. Each block of `**File:** … **Severity:** … **Issue:** … **Suggestion:** … **Scope:** … **Intent:**` is treated as one finding and merged into the review output schema unchanged.

**Full script:** `claude/skills/review/check-skill-compliance.sh`. **Smoke test:** `claude/skills/review/tests/test_skill_compliance_gates.sh`.

### Step 6.5.5 — Docs Richness Verification (corpus-level)

Referenced from `SKILL.md` Step 6.5. When `git diff $BASE...HEAD --name-only | grep -qE '^docs-source/.*\.md$|^documentation/.*\.html$'` returns non-empty, additionally invoke:

```bash
python3 claude/skills/docs-writer/richness_check.py --staged
```

This runs the richness check across the entire `documentation/*.html` corpus picked up by `--staged` (which reads `git diff --cached --name-only --diff-filter=ACMR` filtered to `documentation/*.html`). Distinct from Gate (c)'s per-file positional invocation — `--staged` produces one verdict per touched HTML file in a single subprocess call.

**Exit code semantics:** 0 → all pass, 1 → at least one failure. Non-zero exit produces a blocking review finding.

## Step 2 — Sanity Gate (verification-marker + per-language test run)

Referenced from `SKILL.md` Step 2. The full marker-parse and per-language sanity commands live here; SKILL.md keeps the routing summary.

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

If `$SKIP_SANITY` is false: proceed with the sanity gate logic below.

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

## Step 1.5 — Review Cycle Cap (per-branch/per-feature)

Referenced from `SKILL.md` Step 1.5. Full counting logic and notes; SKILL.md keeps the STOP threshold and the routing summary.

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

## Step 7 — Collect and Deduplicate Results (full procedure)

Referenced from `SKILL.md` Step 7. The full ordered procedure including the cross-feature intel JSON shape and the teams cleanup.

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

## Step 7.5 — Auto-Fix Detection (full procedure)

Referenced from `SKILL.md` Step 7.5. Nit auto-fix always runs when nits are present — no flag needed.

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

## Step 7.6 — Path M / Defer Enforcement Contract (full body)

Referenced from `SKILL.md` Step 7.6. Before Step 8 writes the review file, the reviewer MUST honor three contracts that close the F21 root-cause failure mode: Path M cherry-pick + prose `Defer.` remainder + silent non-blocking acceptance leaking findings between phases.

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

## Step 9 — Review-Tests derivation (per-agent rules)

Referenced from `SKILL.md` Step 9 item 3. For each reopened task (or new micro-task), generate a **Review Tests** section and append it to the task's prompt in the prompts file (from the `**Prompts:**` pointer in `progress.md`). The derivation rule depends on which agent raised the finding:

- **test-engineer findings:** use the finding's **Suggestion:** directly as the test spec (it already describes what test to write).
- **code-reviewer findings (logic errors, correctness):** derive a test that would catch the reported issue — specify test name, file, and key assertion.
- **security-auditor findings:** derive a test that exercises the vulnerable path and asserts secure behavior (e.g., `test_rejects_sql_injection_in_username`).
- **performance-tuner findings:** derive a benchmark or assertion if measurable (e.g., `test_batch_query_executes_single_db_call`), otherwise note "N/A — not unit-testable".
- **Nit-level findings (style, naming, formatting):** note "N/A — no testable behavior".

Format appended to the existing task prompt:

```
**Review Tests:** [test file]: [test_name_1] — [assertion], [test_name_2] — [assertion]
```

The same Review-Tests rules apply when item 4 creates a new micro-task and when item 5 creates a nit micro-task. This ensures `/implement-plan` can execute TDD on review-generated tasks.
