---
name: pipeline
description: Autonomous pipeline orchestrator. Processes a feature list through the full workflow (analyze → plan → implement → review → merge) with zero human intervention. Supports --dry-run and --restart-from.
argument-hint: ([feature-file]|[--renew [--no-prompts]]|[--adopt]|[--from "<text>"]|[--plan [<path>]]|[--issues <selector>]) [--restart-from analyze|plan|implement|review] [--dry-run] [--no-charter|--charter <path>|--max-questions <N>] [--no-prompts] [--no-teams] [--no-review] [--no-ppr] [--no-docs] [--no-uat] [--uat-full-every-feature] [--no-tdd] [--no-test-loop] [--no-notifications] [--no-loop] [--max-loops <N>]
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - Skill
  - TodoWrite
effort: high
---

# Pipeline — Autonomous Feature Orchestrator

Processes a feature list sequentially through the complete workflow pipeline with zero human intervention. Each feature gets its own analysis, plan, branch, implementation, review, PR, and merge.

```
Feature File
  ↓
For each feature:
  analyze → plan → branch → implement → review → path A/B/C → merge
  ↓
Summary
```

---

## Process

### Step 0: Charter Discovery

Charter Discovery is the default-on front-loaded alignment phase. It produces `docs/charter.md` by asking the user a structured set of questions (from `claude/skills/pipeline/charter.md`) and writing a versioned charter artifact. Downstream phases read this charter to scope their work.

**Skip conditions (check in order — first match wins):**

1. `--no-charter` is present → skip entirely (legacy autonomous flow).
2. `--charter <path>` is present → adopt existing charter at `<path>`, set `**Charter:**` pointer in `progress.md`, skip discovery loop. Error cleanly on missing path.
3. `--max-questions 0` is present → treat as `--no-charter` (alias).
4. `docs/analysis*.md` (or `docs/analysis-v*.md`) OR `docs/plan*.md` exist AND `docs/charter.md` does NOT exist → **auto-extract draft charter from prior artifacts**, write `docs/charter.md` (status: `draft`), then surface a single `AskUserQuestion` (`accept` / `edit` / `start fresh discovery`). Detailed algorithm in `reference.md` § "Step 0: Charter Auto-Extract (when prior artifacts exist)". Auto-extract is interactive-only — skipped when `AskUserQuestion` is unavailable (non-interactive session). Implemented by `charter_extractor` (`claude/lib/pipeline/charter_extractor.py`).
5. `docs/charter.md` exists AND `progress.md` `**Charter:**` pointer is valid → skip (charter already produced for this run).

> **Note:** Auto-extract (condition 4) fires only when `docs/charter.md` is absent. If a versioned `docs/charter-v*.md` exists but `docs/charter.md` is absent, auto-extract still fires — auto-extract is for fresh-charter situations, not amendment.

**Mutual exclusivity:**
- `--no-charter` + `--charter <path>` → **STOP**: "ERROR: --no-charter and --charter are mutually exclusive."
- `--charter <path>` with missing target → **STOP**: "ERROR: --charter path not found: <path>"

**Charter Discovery loop (when not skipped):**

**Persona Re-Read (advisory, runs before topic 1):**

1. Probe: `cat docs/active-persona 2>/dev/null`
2. If absent or empty, log `"no active persona — proceeding with default Charter Discovery emphasis"` and fall through to topic 1.
3. If present, read `claude/agents/personas/<name>.md` and record a one-line emphasis note. Emphasis mapping:
   - `devops` → flag infra / operational / deployment / observability concerns
   - `growth-marketer` → flag GTM / user-impact / instrumentation / growth-loop concerns
   - `solo-founder` → flag scope-creep / opportunity-cost / smallest-valuable-version concerns
   - `startup-cto` → flag tech-debt vs time-to-market / hiring / scaling concerns
4. Surface: prepend a `## Persona Bias` block to the topic prompts — single prepend, once per loop, immediately after this sub-section. Conceptually a runtime banner surfaced once before topic 1 to prime the Charter Discovery framing. Example block:
   ```
   ## Persona Bias
   Active persona: <name> — <one-line emphasis note>
   ```
5. User-wins contract: if the user's topic answers contradict the persona's emphasis, the user's answers win — proceed without persona bias.

1. Print an explainer to the user:
   > "Charter Discovery (Step 0): Before the pipeline runs autonomously, let's align on what you want to build. I'll ask about 19 topics. You can exit at any point — just choose 'ship the charter now' to write the charter with what we have so far and continue."
   >
   > "To skip entirely: re-invoke with `--no-charter`. To adopt an existing charter: `--charter <path>`."

2. Read `claude/skills/pipeline/charter.md` for the question bank.

3. For each topic in order (Goal → Users → Problem → Success → Non-Goals → Constraints → MVP Boundary → Slice Strategy → Prior Art → Open Questions → Deployment target → Review style → AI Champion → LSP / symbol search MCP → Self-reflection → Codebase Map confirmation):
   a. Invoke `AskUserQuestion` with the topic's question and options from the bank.
   b. Record the user's answer.
   b.5 **Multi-party trigger (runs AFTER each topic answer, BEFORE the convergence check):** Scan the answer text for any of these trigger tokens: `teammate`, `customer segment`, `upstream`, `downstream`, `external service`. If any token matches AND the Stakeholders prompt has not yet fired this run (**once-per-run latch**), invoke a conditional `AskUserQuestion` asking: "Who are the decision-makers, blockers, or reviewers for this work? (one short line per stakeholder; skip if none apply)". Record the answer under `## Stakeholders` in the in-progress charter draft. Cross-reference: `claude/skills/pipeline/charter.md § Stakeholders (conditional probe)`.
   c. After the answer, invoke the convergence check from the bank:
      - **"ship the charter now"** → write `docs/charter.md` (status: `draft`), set `**Charter:**` pointer in `progress.md`, exit loop, continue pipeline.
      - **"continue to next topic"** → advance to the next topic.
      - **"go deeper / follow-up"** → ask the topic's follow-up question (if any), then advance.
      - **"edit manually"** → write current draft to `docs/charter.md` (status: `draft`), print path, **STOP** pipeline. User resumes via `/pipeline --charter docs/charter.md` when ready.

**Auto-detect short-circuit (Topic 10 only):** Before asking Topic 10 (Deployment target), check `docs/active-deployment`. If present, treat its value as the answer and skip the topic. If absent, probe the working tree for `vercel.json`, `railway.toml`, `render.yaml`, `.do/app.yaml`. If exactly one is found, pre-fill the Topic 10 answer with the matching provider slug and ask the user only for confirmation (single `AskUserQuestion` — exempt from the `--max-questions` topic-cap). If multiple config files coexist, log `DEPLOY_TARGET_AUTO_DETECT_CONFLICT: <files>` and fall through to a full Topic 10 prompt. If none found, ask the full Topic 10 prompt as normal. **Monorepo sub-dir probe (only when the root probe above returned zero matches):** additionally probe `apps/`, `packages/`, `services/` up to 2 levels deep (i.e. `apps/<x>/vercel.json` and `apps/<x>/<y>/vercel.json` are in-scope; `node_modules/**` and other roots are NOT) for the same four provider config files (`vercel.json`, `railway.toml`, `render.yaml`, `.do/app.yaml`). If exactly one sub-dir config is found, pre-fill the Topic 10 answer with its provider slug and ask for confirmation (single `AskUserQuestion` — exempt from `--max-questions`). If multiple sub-dir configs are found, log `DEPLOY_TARGET_MONOREPO_MULTI_CONFIG: <files>` and fall through to `AskUserQuestion` listing the candidate paths (interactive sessions); when `$NO_PROMPTS=true` (set by `--no-prompts` or the deprecation alias `--auto`), auto-pick the first alphabetical match and log `MONOREPO_AUTO_FIRST_MATCH: <file>` instead of prompting. If no sub-dir config is found either, ask the full Topic 10 prompt as normal.

4. After the final topic, run a final convergence check. If user is satisfied, write `docs/charter.md` (status: `ratified`), set `**Charter:**` pointer in `progress.md`.

**Charter file versioning:** follow the Versioning Convention from `claude/rules/workflow.md` — if `docs/charter.md` already exists, archive it to `docs/charter-v[N+1].md` before writing the new one.

**progress.md `**Charter:**` pointer:** written as `**Charter:** docs/charter.md` (or the versioned path) immediately after the charter file is written.

**`--max-questions <N>` behavior:** When `N > 0`, cap the total number of `AskUserQuestion` invocations at `N`. After the cap is reached, write the draft charter and continue. `N = 0` is the `--no-charter` alias (no discovery at all).

**`--max-questions` accounting for Stakeholders:** The conditional Stakeholders prompt (step 3b.5 above) counts toward the `--max-questions` cap. Setting `--max-questions 0` (the `--no-charter` alias) therefore skips it along with the rest of Charter Discovery.

**Charter scope vs. install gates:** Every native skill, agent, and hook ships default-on regardless of charter answers; the charter scopes the work, it does not enable or disable skills.

---

### Step 1: Parse Arguments

Parse `$ARGUMENTS`:
- Positional: feature file path (optional)
- `--dry-run` flag = preview mode
- `--restart-from <step>` = resume from a specific step. Valid: `analyze`, `plan`, `implement`, `review`
- `--renew` flag = regenerate feature file from failed/deferred items
- `--no-prompts` = session-wide autonomy modifier. Skip every `AskUserQuestion` invocation for the remainder of this pipeline run. Affects Step 0 (Charter Discovery topic loop, Stakeholders probe, Topic 10 deployment auto-detect / monorepo conflict probe), Step 0 auto-extract `accept/edit/start fresh discovery`, and Step 1.6 sub-step 6.5 charter re-validation drift. Each prompt site falls back to its safe default (skip the topic; take first-detected provider; auto-accept the auto-extracted draft; auto-accept drift entries into an HTML-comment header in `docs/features-renewed.md`). Set `NO_PROMPTS=true` for the rest of the run.
- `--auto` (DEPRECATED) = legacy alias for `--no-prompts`. On use, log to stderr: `DEPRECATED: --auto is now --no-prompts (scoped semantics extended to all prompts)`, then proceed as if `--no-prompts` were passed. Slated for removal one release after this change.
- `--no-review` = skip the review phase for every feature in this run. Step 5.6 synthesises a Path A (passed) outcome — writes a one-line skip notice review file, updates the `**Review:**` pointer in `docs/progress.md`, emits `phase-done`, and advances to Step 5.7 which routes to Path A. Use when you want implement → push → PR without multi-agent review.
- `--no-ppr` = skip `/ppr` for every feature. Halts each feature after review with `Status: COMPLETED (--no-ppr halt; no push/PR/merge)`. Skips docs and post-merge entirely. Useful for dry-running implement+review without touching origin.
- `--no-docs` = skip the Documentation Update Phase. Aliases `PIPELINE_SKIP_DOCS=1` at parse time (both honoured; either is sufficient).
- `--no-uat` = skip the UAT Phase for every feature in this run. Aliases `PIPELINE_SKIP_UAT=1` at parse time (both honoured; either is sufficient).
- `--uat-full-every-feature` = force the full role/button sweep on every feature instead of the diff-scoped default. Recorded as a local var (`UAT_FULL_EVERY_FEATURE`), not an env var — see the recording paragraph below.
- `--no-tdd` = force `FEATURE_CLASS = non-dev` for every feature in this run. Bypasses the Step 5.5.0 prefix-derived classification — every feature dispatches via the standard `implement-plan` path with no TDD pairing.
- `--no-test-loop` = disable the implement-plan test-run inner loop (Step 2e.5). Records `NO_TEST_LOOP=true` for the implement-plan dispatch. Does NOT affect TDD red/green phases — only suppresses the post-task project test command + fix-retry loop. Use when the project test command is slow or noisy in CI.
- `--no-notifications` = disable notification emission for the run. Aliases `PIPELINE_NO_NOTIFICATIONS=1` at parse time (both honoured; either is sufficient). The orchestrator exports `PIPELINE_NO_NOTIFICATIONS=1` for the rest of the session.
- `--adopt` flag = adopt current manual workflow state into pipeline
- `--max-usd <N>` = hard cap on cumulative USD across the entire run. Default: **unlimited** (flag omitted disables the budget check).
- `--max-turns <N>` = hard cap on accumulated sub-agent turns. Default: **unlimited**. When set, counts Agent tool invocations.
- `--from "<text>"` = free-text context for feature-file auto-generation. Stored as `FROM_TEXT`. Mutually exclusive with `--adopt` and `--renew`. Compatible with `--dry-run`, `--restart-from`, and all other flags.
- `--plan [<path>]` = ingest a plan-mode plan file. With a path: reads that file. Without a value: auto-picks the most-recently-modified `~/.claude/plans/*.md` if modified within the last 60 min (else STOP with a path-required error). `~/` and relative paths resolved. 200 KB cap. Mutually exclusive with `--from`, `--adopt`, `--renew`, and a positional feature-file path.
- `--issues <selector>` = ingest GitHub Issues as the feature source. Selector forms: `label:<name>`, `milestone:<name>`, `all`, or bare `<name>` (defaults to `label:<name>`). Routes to Step 1.45 (Issues-Mode Ingest). Mutually exclusive with `--plan`, `--from`, `--adopt`, `--renew`, and a positional feature-file path.
- `--issues-limit <N>` = cap fetched issues at `<N>` (default 50, max 200). When `gh issue list` returns more than the cap, log a warning and proceed with the top `<N>` per `--issues-sort` order. Ignored when `--issues` is absent.
- `--issues-sort <mode>` = sort mode for fetched issues. Values: `created` (default), `updated`, `priority`. `priority` is derived client-side from `priority:high|medium|low` labels (no priority label sorts to the end). Ignored when `--issues` is absent.
- `--issues-comment-author <login>` = override the maintainer-comment heuristic. When set, only comments authored by `<login>` are considered for constraint extraction. Ignored when `--issues` is absent.
- `--no-charter` = skip Step 0 Charter Discovery entirely; restores legacy autonomous flow.
- `--charter <path>` = adopt an existing charter file at `<path>`. Skips Step 0 discovery loop; sets the `**Charter:**` pointer in `progress.md`. STOP if the path does not exist: "ERROR: --charter path not found: <path>"
- `--max-questions <N>` = cap the total number of `AskUserQuestion` invocations in Step 0 at `N`. Default: unbounded. `--max-questions 0` is an alias for `--no-charter` (no discovery at all).
- `--no-teams` = force-disable Agent Teams for this run. Resolves `PIPELINE_TEAMS_OVERRIDE=never`. Persists into `**Review style:** never teams` for every feature in the run (overrides Charter Topic 11 and the heuristic). The orchestrator dispatches `Skill: pipeline-review --no-teams` at every review boundary. Teams mode is otherwise default-on (decided per-feature by the Step 5.6.0 heuristic).
- `--no-loop` = disable the default-on outer feature-sweep loop; restores legacy single-trip Step 5.10 termination. When set, Step 5.11 is a no-op and the pipeline exits after the first full sweep exactly as before this feature.
- `--max-loops <N>` = OPTIONAL hard ceiling on outer-loop iterations; when omitted, termination is still guaranteed by the STALLED no-progress guard. Only evaluated when `--no-loop` is absent.

**Removed (deprecated) flags — STOP on use:**
- `--teams` (pipeline-level): REMOVED. The orchestrator's per-feature Step 5.6.0 heuristic + the persisted `**Review style:**` (Charter Topic 11) already cover the "force teams on" surface. STOP with `DEPRECATED: --teams (pipeline) removed. Teams mode is default-on per-feature; pass --no-teams to opt out for this run.`

Validate mutual exclusivity: if `--from` and `--adopt` are both present, STOP with "ERROR: --from and --adopt are mutually exclusive." If `--from` and `--renew` are both present, STOP with "ERROR: --from and --renew are mutually exclusive." If `--plan` is combined with `--from`, `--adopt`, `--renew`, or a positional feature file, STOP with `ERROR: --plan is mutually exclusive with --from/--adopt/--renew/positional path`. If `--issues` is combined with `--from`, `--adopt`, `--renew`, `--plan`, or a positional feature file, STOP with `ERROR: --issues is mutually exclusive with --plan/--adopt/--renew/--from/positional path`. If `--no-charter` and `--charter <path>` are both present, STOP with "ERROR: --no-charter and --charter are mutually exclusive."

Determine feature file source (in priority order):
1. If `--adopt` is present → go to Step 1.7 (Adopt Manual Workflow). `--adopt` is mutually exclusive with providing a feature file path, `--renew`, and `--from`.
2. If `--plan` is present → go to **Step 1.4 (Plan-Mode Ingest)**.
3. If `--issues` is present → go to **Step 1.45 (Issues-Mode Ingest)**.
4. If a positional path argument is given AND the file exists → use it directly
5. If a positional path argument is given AND the file does NOT exist → STOP: "Feature file not found: [path]"
6. If `--renew` is present → go to Step 1.6 (Renew)
7. If no positional argument → go to Step 1.5 (Auto-Generate). If `FROM_TEXT` is set, Step 1.5 uses it as context.

Validate `--restart-from` if present: must be one of `analyze`, `plan`, `implement`, `review`.

Record `--max-usd` and `--max-turns` in `docs/pipeline-state.md` as `**Max USD:**` and `**Max turns:**` fields so the budget check at every phase boundary can read them. Write `unlimited` when the flag was not provided — the budget-check step treats `unlimited` as a no-op.

Record the teams override in a local variable for use by Step 5.1:
- If `--no-teams` is present: `PIPELINE_TEAMS_OVERRIDE=never`.
- Otherwise: `PIPELINE_TEAMS_OVERRIDE=decide`.

**`--no-prompts` / `--auto` short-circuit (applies to every `AskUserQuestion` call site in Step 0, Step 1.6, and elsewhere):** If `--no-prompts` was passed (or its deprecation alias `--auto`), set `$NO_PROMPTS=true`. Every `AskUserQuestion` invocation downstream is wrapped in `if [ "${NO_PROMPTS:-}" != "true" ]; then ... else <safe-default> fi`. Safe defaults per call site: Topic loop → skip the topic; Stakeholders multi-party probe → skip; Topic 10 deployment monorepo conflict → first-alphabetical match (legacy `--auto` carve-out behaviour); auto-extract `accept / edit / start fresh discovery` → `accept`; Step 1.6 sub-step 6.5 drift entries → auto-accept (recorded as HTML-comment header in `docs/features-renewed.md`, mirroring legacy `--renew --auto`).

**`--no-notifications` / `PIPELINE_NO_NOTIFICATIONS=1` export:** If `--no-notifications` is present at parse, export `PIPELINE_NO_NOTIFICATIONS=1` so the existing `claude/hooks/notify-emit.sh` short-circuit (line 20 of that script) fires for the rest of the session. The env var continues to work standalone (set before launching `/pipeline`); either is sufficient.

**`--no-docs` / `PIPELINE_SKIP_DOCS=1` export:** If `--no-docs` is present at parse, export `PIPELINE_SKIP_DOCS=1` so the existing Documentation Update Phase escape hatch fires.

**`--no-uat` / `PIPELINE_SKIP_UAT=1` export:** If `--no-uat` is present at parse, export `PIPELINE_SKIP_UAT=1` so the UAT Phase escape hatch fires (mirrors the `--no-docs` / `PIPELINE_SKIP_DOCS=1` pattern). The env var continues to work standalone; either is sufficient.

**`--no-review` / `--no-ppr` / `--no-tdd` / `--no-test-loop` / `--uat-full-every-feature` recording:** These flags are not env vars — record them as local variables (`NO_REVIEW`, `NO_PPR`, `NO_TDD`, `NO_TEST_LOOP`, `UAT_FULL_EVERY_FEATURE`) for the orchestrator to check at Step 5.5.0 (no-tdd), Step 5.6 (no-review), Step 5.8 Path A entry (no-ppr), the implement-plan Step 2e.5 inner loop short-circuit (no-test-loop), and the UAT Phase mode selection (`UAT_FULL_EVERY_FEATURE` forces full sweep per feature). `NO_TEST_LOOP` is forwarded into the implement-plan subagent dispatch context so the per-task inner loop honours it.

**`--no-loop` / `--max-loops` recording:** Record the loop control flags in `docs/pipeline-state.md` at Step 5.1 so Step 5.11 can read them on every iteration:
- `**Loop:**` — write `on` (default, when `--no-loop` is absent) or `off` (when `--no-loop` is present).
- `**Max loops:**` — write the integer value of `--max-loops <N>` when provided, or `unlimited` when the flag is absent.
- `**Loop count:**` — integer, starts `0`, incremented by `+1` at each outer-loop re-entry (Step 5.11 path (e)).
- `**Prev renew set:**` — last loop's renew-set size as an integer, or `(none)` on the first trip through Step 5.11.
- `**Loop no-progress count:**` — integer, starts `0`; incremented `+1` when the renew-set size did NOT strictly decrease vs the previous trip; reset to `0` when it does decrease; at `2` → STALLED exit (the guaranteed terminator).

The orchestrator exports `PIPELINE_FEATURE_INDEX="<N>/<M>"` (NB1 `N/M` shape from `docs/pipeline-state.md` `**Feature:**` line; set at Step 5.1) and `PIPELINE_FEATURE_NAME="<feature-name>"` so the notification payload's `feature_index` / `feature_name` fields are populated without re-parsing pipeline state.

### Step 1.4: Plan-Mode Ingest (--plan)

Triggered when `--plan [<path>]` is present. Converts a plan-mode plan file (`~/.claude/plans/<slug>.md` or any path; auto-picks the most-recent within 60 min when no path given) into `docs/features.md` via an in-process `general-purpose` Agent dispatch. Resolves + sanity-gates the path (> 0, ≤ 200 KB), archives the existing features file, dispatches with the "Plan-Mode Extraction Prompt" (content wrapped `<<<PLAN_CONTENT_BEGIN>>>…<<<PLAN_CONTENT_END>>>`, untrusted), validates (`# Feature Pipeline` + ≥1 `## [a-z]` section), writes, then proceeds to Step 2. Compatible with `--dry-run`, `--restart-from`, `--max-usd`, `--max-turns`.

See `reference.md` § "Step 1.4: Plan-Mode Ingest — Full Details" for the full path-resolution + dispatch + validation algorithm.

---

### Step 1.45: Issues-Mode Ingest (--issues)

Triggered when `--issues <selector>` is present. Converts the selector (`label:<name>` | `milestone:<name>` | `all` | bare `<name>` = `label:<name>`) into a `gh issue list` query, maps each open issue to a feature entry, and writes `docs/features.md`. Sanity-gates `gh` install + auth + GitHub remote (STOP on any miss), archives the existing features file (Versioning Convention), fetches via `claude/lib/pipeline/fetch_issues.sh`, dispatches a `general-purpose` Agent with the "Issues Extraction Prompt" (payload wrapped `<<<ISSUES_CONTENT_BEGIN>>>…<<<ISSUES_CONTENT_END>>>`, untrusted), validates (`# Feature Pipeline` + ≥1 `## [a-z]+/issue-[0-9]+-` header), writes, then proceeds to Step 2. Compatible with `--dry-run`, `--restart-from`, `--max-usd`, `--max-turns`.

See `reference.md` § "Step 1.45: Issues-Mode Ingest (--issues)" for the full algorithm (issue → feature mapping, slug derivation, commit-type heuristic, constraint extraction, failure modes).

---

### Step 1.46: Budget Preflight (at every phase boundary)

Before entering any phase (Step 5.2 analyze, 5.3 plan, 5.5 implement, 5.6 review, 5.8 Path A/B/C), run a budget check: sum the feature's cost-log entries (`~/.claude/logs/cost-events.jsonl`) into `CUMULATIVE`, read `**Max USD:**` from `docs/pipeline-state.md`. If `unlimited`/empty → no enforcement. Otherwise if `CUMULATIVE + estimated_next_phase_cost > MAX_USD`, halt: write `BUDGET_EXCEEDED: phase=<next-phase>, cumulative=…, cap=…` to state + Run Log, **STOP** with a human-readable message + resume hint (`/pipeline --restart-from <phase> --max-usd <higher-cap>`). Halts are **phase-boundary only**, never mid-phase. On breach the orchestrator emits a `feature-failed` beacon routed to `claude/hooks/notify-emit.sh` with `NOTIFY_EVENT_TYPE=budget-breach`.

See `reference.md` § "Step 1.46: Budget Preflight — Full Details" for the full cost-sum bash, estimate fallback, and notify semantics.

---

### Step 1.5: Auto-Generate Feature File

Triggered when no feature file path is provided.

1. Check for existing `docs/features.md`:
   - If `FROM_TEXT` is set: skip to generation below even if existing features exist (user explicitly wants a new feature file from their description).
   - If it exists AND has unprocessed features (features without a `### Run Log` entry or with no status in the run log): use it directly. Log: "Using existing feature file: docs/features.md"
   - If it exists but all features have been processed: continue to generation below

2. Gather context (read in order):
   a. If `FROM_TEXT` is set: use it as the primary feature description. Still read analysis/PRP (items b, c below) for structural context (project type, constraints), but `FROM_TEXT` drives the feature list.
   b. `docs/progress.md` → `**Analysis:**` pointer → read the analysis file → extract objective
   c. `docs/prp.md` → read and extract objectives/features
   d. If `FROM_TEXT` is not set AND neither the analysis file nor prp.md yields content: STOP with "No context found. Provide --from text, run /analyze first, or supply a feature file: /pipeline <file>"

3. Check `docs/progress.md` for a `## Deferred` section:
   - If deferred items exist: include each as a feature entry

4. Generate `docs/features.md`:
   - **When `FROM_TEXT` is the only source** (no analysis, no PRP):
     - Generate a single feature entry. Derive the H2 header type from the text (look for keywords: "add"/"create" → feat, "fix"/"repair" → fix, "refactor"/"restructure" → refactor, "test" → test, etc.; default to `feat`).
     - Use the text as the `**Description:**` field verbatim.
     - If the text describes multiple features (separated by clear intent boundaries like semicolons or distinct sentences about different features), generate multiple entries.
   - **When `FROM_TEXT` + analysis/PRP exist:**
     - Use `FROM_TEXT` as the primary feature description, supplement with constraints from analysis.
     - If the text describes multiple features, generate multiple entries.
   - **When no `FROM_TEXT` (standard auto-generate):**
     - For each objective/feature from the analysis or PRP:
       - Derive H2 header: `## <type>/<kebab-case-name>` where type is inferred from the objective (feat for new features, fix for bugs, refactor for restructuring, etc.)
       - Copy the objective as the `**Description:**` field
       - Copy any constraints as the `**Constraints:**` field
   - For each deferred item (regardless of `FROM_TEXT` presence):
     - Derive H2 header from the item description
     - Use the deferred item details as the `**Description:**` field
     - Add `**Constraints:**` noting it was deferred: "Deferred from [source]: [reason]"
   - Append empty `### Run Log` sections

5. Log: "Auto-generated feature file: docs/features.md ([N] features, source: [--from text|analysis|PRP])"
6. Proceed to Step 2 with `docs/features.md`

---

### Step 1.6: Renew Feature File

Triggered when `--renew` is present. Full flow defined in `reference.md` § "Step 1.6: Renew Feature File (--renew)". After renewal, proceed to Step 2 with `docs/features-renewed.md`. Includes a charter re-validation pass (see reference.md § Step 1.6 sub-step 6.5) when `**Charter:**` is not `(none)`. Emits a drift artifact at `docs/charter-drift.md` (or `docs/charter-drift-vN.md` per the Versioning Convention). When `--renew --no-prompts` is combined (or the deprecation alias `--renew --auto`), the `AskUserQuestion` gating inside sub-step 6.5 is bypassed and drift entries are auto-accepted into an HTML-comment header block.

---

### Step 1.7: Adopt Manual Workflow

Triggered when `--adopt` is present. Full flow defined in `reference.md` § "Step 1.7: Adopt Manual Workflow (--adopt)". After adoption, proceed with normal pipeline loop from the determined resume point.

---

### Step 0.5: MCP Preflight (once per run, after arg-parse, before Step 2)

Runs exactly ONCE at pipeline startup, after Step 1 arg-parse and before Step 2. Establishes the `CONNECTED_MCPS` cache (single `claude mcp list` probe) reused for the whole run, detects + wires applicable MCPs from the 4-item auto-wire set (`context7`, `agentmemory`, `serena`, `sequential-thinking`), emits advisory lines for suggestion-only servers (`codegraph`, `graphify`, `local-rag`, `RepoMapper`), runs serena onboarding when connected + memories absent, previews-only under `--dry-run`, then writes `**MCP connected:**` / `**MCP wired:**` to `docs/pipeline-state.md` and emits the `MCP_PREFLIGHT:` beacon. Missing `claude` CLI → `MCP_PREFLIGHT_SKIPPED` (non-fatal, empty cache).

See `reference.md` § "Step 0.5: MCP Preflight — Full Details" (probe bash, wire commands, suggestion advisory, serena onboarding contract, `--dry-run` preview, failure modes, beacon shape).

---

### Step 2: Read Feature File

Read the feature file (from Step 1, 1.5, 1.6, or 1.7). Parse features by H2 headers (`## <type>/<name>`).

Each feature block contains:
- **Description:** — the feature objective (feeds into analysis)
- **Constraints:** — optional restrictions (feeds into analysis constraints). If absent, treat as "None stated"
- **### Run Log** — section where pipeline appends execution logs. Skip this when reading feature definitions.

The H2 header format `## <type>/<name>` determines:
- `<type>` → branch prefix and commit type (feat, fix, refactor, docs, test, chore, perf)
- `<name>` → kebab-case feature identifier

Reserved housekeeping H2 headers are skipped by `parse_features` and MUST NOT be used as feature names: `Deferred`, `Closed`, `Notes`, `Manual actions` (case-insensitive, with an optional ` (...)` suffix like `## Manual actions (non-pipeline — reference only)`). These are documentation trailers — use them freely for deferred/manual/closed items without polluting the feature list. A real feature whose name happens to contain one of these words is fine as long as the separator is not a space — `## fix/deferred-backlog-cleanup` passes through untouched.

Validate: at least one feature with a Description field. If zero: **STOP** with "No features found in [file]. Each feature needs an H2 header (## type/name) and a **Description:** field."

---

### Step 3: Check Pipeline State (Resume Support)

Check for `docs/pipeline-state.md`:
- If it exists AND its `**Feature file:**` field matches the current feature file path: resume from the saved position. Log: "Resuming pipeline from feature [N]/[total], step [step]"
- If it exists but references a different feature file: warn "Stale pipeline state from a different run — starting fresh." Remove the state file.
- If it does not exist: start from the first feature.

**Terminal-state guard (fires before any --restart-from override):** If `docs/pipeline-state.md` contains `**Step:** done` AND `--restart-from <phase>` is present, STOP with:

> ERROR: Pipeline already complete. To start a new run: archive docs/features.md (e.g. `mv docs/features.md docs/features-vN.md`) and re-invoke /pipeline without --restart-from.

This guard exists to prevent silent re-execution of a finished pipeline. The terminal marker is written by Step 5.10 Terminal Cleanup.

The `--restart-from` argument overrides the saved step (but not the saved feature index). If both `--restart-from` and a state file are present, use the state file's feature index but the `--restart-from` step.

**Phase Mode preservation contract (REQUIRED on every resume):** When resuming, the assistant MUST read `docs/pipeline-state.md` and locate the `**Phase Mode:**` field. The mode recorded there governs every subsequent phase invocation for the in-flight feature.

| Recorded mode | Required behavior on resume |
|---------------|------------------------------|
| `subagent` | Every subsequent phase (analyze, plan, implement, review) MUST be dispatched via the `Agent` tool using the corresponding `<!-- PHASE: ... -->` template from `reference.md`. **Inline invocation is FORBIDDEN.** Direct calls to `Skill: implement-plan` or `Skill: pipeline-review` (without an enclosing Agent dispatch) are a contract violation — they bypass context isolation and must not be used. If the assistant is tempted to "just run /pipeline-review quickly to wrap up", STOP and dispatch via Agent instead. |
| `inline` | Legacy mode preserved for in-flight features only. Continue inline for the current feature. New features added to the run dispatch via `subagent`. Log: `LEGACY_PHASE_MODE: inline mode preserved for in-flight feature; new features dispatch via subagent`. |
| (missing/empty) | Default to `subagent` and write `**Phase Mode:** subagent` back to the state file before proceeding. Leave `**Last phase agent:**` absent until the next phase actually dispatches and returns an ID. |

**Self-check before any phase invocation on resume:** Before invoking a phase skill or Agent, the assistant must explicitly answer two questions: (1) "What does `**Phase Mode:**` say in `docs/pipeline-state.md` right now?" (read it, do not rely on memory), and (2) "Does my next planned tool call match that mode?" If the planned call is `Skill: pipeline-review` and Phase Mode is `subagent`, the call is wrong — switch to `Agent(... <!-- PHASE: review --> template ...)` instead.

---

### Step 4: --dry-run Mode

If `--dry-run` is present, for each feature output this preview and then **STOP** (do not execute anything):

```
[DRY RUN] Feature [N]/[total]: <type>/<name>
  1. Write analysis → docs/analysis-vN.md
  2. Generate plan → docs/plan-vN.md + docs/prompts-vN.md
  3. Create branch → <type>/<name>
  4. Invoke /implement-plan
  5. Invoke /pipeline-review
  6. Path A: push → PR → CI check (fix if failing, max 3 attempts) → auto-merge → cleanup
     Path B: fix reopened tasks → re-review (max 5 cycles)
     Path C: re-plan with findings → implement → review (max 1 re-plan)
  7. Log results to feature file
```

After all features: output "Dry run complete. [N] features would be processed." and **STOP**.

---

### Step 5: Feature Processing Loop

For each feature, sequentially (starting from resume point if applicable):

---

##### Step 5.0: Phase Mode Selection (per-feature, before Step 5.1)

**Default policy: `PHASE_MODE = subagent`. Always. Unconditional.**

Every initial phase dispatch (analyze, plan, implement, review) runs as an Agent-tool subagent for context isolation. There is no surface-area heuristic, no "trivial features run inline" carve-out, and no description/constraint/acceptance-criteria check. Inline is no longer a valid spawn mode for any pipeline phase at feature-loop entry.

Decision rule:
1. Set `PHASE_MODE = subagent`. Always.
2. The only place `inline` may surface is the narrow nit-attack sub-path documented in Step 5.7 (post-review, when only nits remain or as a preamble to Path B). It is never the default and never applies to analyze, plan, or the initial implement/review of a feature.

Record `**Phase Mode:** subagent` in `docs/pipeline-state.md` (Step 5.1 writes the full template — this sub-step guarantees the value is known before that write happens).

**Progress beacon helper:** At each phase transition (Step 5.1, 5.2, 5.3, 5.5, 5.6, and on Path B/C entry), emit a beacon to the user via:
`Bash(command='printf "[PIPELINE] feat=%s/%s step=%s cycle=%s :: %s (%s) worker=%s\n" "$IDX" "$TOTAL" "$STEP" "$CYC" "$NAME" "$TAG" "$WORKER" >&2', description='Progress beacon')`
where `$IDX/$TOTAL/$STEP/$CYC/$NAME/$TAG/$WORKER` are the current values from `docs/pipeline-state.md`. Tags: `phase-pre`, `phase-done`, `path-b-pre`, `path-c-pre`, `path-d-pre`, `path-d-post`, `feature-start`, `feature-done`, `feature-failed`, `docs-pre`, `docs-done`.

For notify-class tags (`feature-failed`, `path-b-pre`, `path-c-pre`, `feature-done`), the beacon helper ALSO invokes `claude/hooks/notify-emit.sh --mode beacon` with `NOTIFY_*` env vars derived from `docs/pipeline-state.md` (`NOTIFY_FEATURE_INDEX` from `**Feature:**`, `NOTIFY_STEP` from `**Step:**`, `NOTIFY_FEATURE_NAME` from `**Name:**`, `NOTIFY_EVENT_TYPE` per the canonical hook event mapping in § Notifications below, `NOTIFY_TEXT` from the in-memory `<task-notification>` `<summary>` or the beacon's tag context, capped at 200 chars by the helper). For `feature-failed` specifically, the helper invocation also sets `NOTIFY_PATH_D_ATTEMPTED` to the current `**Path D attempted:**` boolean from `docs/pipeline-state.md` so the beacon-mode payload surfaces `path_d_attempted` — letting the user tell at a glance whether the salvage path ran before the feature died. For interactive sessions with Remote Control + "Push when Claude decides" enabled, the orchestrator captures the helper's JSON-line stdout and forwards it to the `PushNotification` tool (Claude Code 2.1.110+). For non-interactive sessions, `PushNotification` is unavailable and the helper falls through to the `Notification`-hook OSC 777 `terminalSequence` path. The non-notify tags (`phase-pre`, `phase-done`, `feature-start`, `docs-pre`, `docs-done`) emit only the printf beacon — no notify-emit invocation. The helper short-circuits to a no-op when `PIPELINE_NO_NOTIFICATIONS=1` is set in the environment.

`$WORKER` defaults to `claude` when no routing override is in effect. When `/implement-plan` Step 1.5 resolves a per-task `worker:` header to an alternate class, `$WORKER` is set to that class name before the beacon fires. The resolution order for `$WORKER` is defined in `claude/lib/worker-provider/interface.md` § Env-var resolution.

**TASKS panel helper (TodoWrite):** Side-by-side with each beacon, the orchestrator MUST call the `TodoWrite` tool so the host UI's TASKS panel (e.g. T3 Code's right-hand pane) reflects what the pipeline is currently working on. This is non-optional — the TodoWrite state IS the user-facing visibility into pipeline progress. The orchestrator is expected to keep a single live todo list across the run; each transition rewrites the whole list with updated statuses.

Required structure (one item per upcoming/active/completed pipeline action for the **current feature**, in order):
1. `Feature <IDX>/<TOTAL>: <NAME> — analyze`
2. `Feature <IDX>/<TOTAL>: <NAME> — plan`
3. `Feature <IDX>/<TOTAL>: <NAME> — branch`
4. `Feature <IDX>/<TOTAL>: <NAME> — implement` (append `(cycle <CYC>)` when Path B/C is active and `<CYC> >= 2`)
5. `Feature <IDX>/<TOTAL>: <NAME> — review` (append `(cycle <CYC>)` when Path B is active)
6. `Feature <IDX>/<TOTAL>: <NAME> — path <A|B|C|N>` (only present after Step 5.7 selects a path; replaced on each re-route)
7. `Feature <IDX>/<TOTAL>: <NAME> — merge` (Path A only — present once Path A is selected)

Status mapping per tag:
- `feature-start` (Step 5.1): rewrite the list with items 1–5 (and 7 if known) all `pending`. If multiple features remain in the run, append a tail item per remaining feature: `Feature <j>/<TOTAL>: <name> — pending` (single line, status `pending`) so the user sees the full queue.
- `phase-pre` for `<phase>`: mark every prior phase row as `completed`, mark `<phase>` as `in_progress`. Leave later phases `pending`.
- `phase-done` for `<phase>`: mark `<phase>` as `completed`. Do NOT also flip the next phase to `in_progress` here — that happens on the next `phase-pre`.
- `path-b-pre` / `path-c-pre`: append/replace items 4 and 5 with `(cycle <CYC>)` suffix and set their status to `pending`; reset row 6 to `Path B` or `Path C` `in_progress`. Prior cycles stay as `completed` rows above.
- `feature-done` (Step 5.9 success): mark every row for this feature `completed`. If a queue tail exists, leave following features as `pending`.
- `feature-failed` (Step 5.9 fail / budget halt / CD halt): mark the in-progress row as `cancelled` with the failure reason in the row text (e.g. `— review (cycle 5) [HALTED: convergence cap]`). Tail features stay `pending`.

Implementation note: build the new list in memory, then call `TodoWrite` with the full array — TodoWrite replaces the whole list on every call, so partial updates are fine. Do not gate the TodoWrite call on `$PHASE_MODE` — it fires identically for `subagent` and `inline`.

**Why subagent always (rationale):** Anthropic's multi-agent guidance: isolated context per phase reduces token usage by ~67% on average and prevents cross-phase contamination — the reviewer's findings should not bias the re-implementer's reasoning. The cost of subagent dispatch on truly trivial features is negligible compared to the bug surface of mode drift on resume (incident: a `subagent`-mode feature dropped to inline post-review because Path B did not honor the recorded mode, and the assistant on resume invoked `Skill: pipeline-review` directly without consulting `**Phase Mode:**`). `inline` is the exception, not the default — reserved exclusively for the Path N nit-attack sub-path.

**Phase routing contract:** Each phase below (Step 5.2 analyze, 5.3 plan, 5.5 implement, 5.6 review) is dispatched via the `Agent` tool using the corresponding template from `reference.md` § "Step 5.x: Phase Subagent Dispatch — Prompt Templates". The orchestrator reads the on-disk artifact (analysis/plan/prompts/review file) for state instead of phase output. Path B and Path C re-invocations also dispatch via Agent — they MUST read `**Phase Mode:**` fresh from `docs/pipeline-state.md` before each re-invoke, never trust a stale local variable. See `reference.md` § "Step 5.8: Execute Path — Full Details".

**Subagent write-surface convention:** Each phase dispatch substitutes placeholders into the corresponding `<!-- PHASE: ... -->` template in `reference.md`. Any step inside a dispatched subagent that writes a `docs/*.md` artefact (analysis, plan, prompts, review file) MUST use the Bash heredoc surface (`cat > docs/<file>.md <<'EOF' … EOF`) — the Claude Code agent harness heuristically rejects the `Write` tool on `docs/*.md` from subagent contexts. For in-place updates (e.g. `docs/progress.md`), the `Edit` tool is permitted. The full convention is documented at `claude/skills/pipeline/reference.md` § Subagent Write-Surface Convention (normative). This is a harness-level constraint, NOT a hook — the `block-stage-sensitive.sh` and `pre-edit-protect.sh` PreToolUse hooks are correctly scoped to `git add` and `.env`/credentials respectively, and do not intercept Write tool calls on `docs/*.md`.

The "inline instructions" preserved in Steps 5.2/5.3/5.5/5.6 below are kept as the canonical spec of what each phase must do — they are the reference body the subagent prompt template points at. They are NOT the execution path for the orchestrator under normal operation.

**Legacy state files:** If a resumed `docs/pipeline-state.md` records `**Phase Mode:** inline` (written under the previous heuristic-based policy), preserve that mode for the in-flight feature to avoid breaking running work, but log once: `LEGACY_PHASE_MODE: inline mode preserved for in-flight feature; new features dispatch via subagent`. New features added to the run after the legacy resume use `subagent`.

**Model defaults per phase:**

| Phase     | Default Model | Override                           |
|-----------|---------------|------------------------------------|
| analyze   | opus          | —                                  |
| plan      | opus          | —                                  |
| implement | sonnet        | Task prompt `Model:` header        |
| review    | opus          | REVIEW.md `review-model:` field    |

Look up the phase model from this table. Store as `PHASE_MODEL`. Override precedence per phase: for implement, task prompt `Model:` header > phase default; for review, REVIEW.md `review-model:` > phase default; for analyze/plan, phase default only (no override mechanism).

Pass `model: $PHASE_MODEL` in the `Agent` tool parameters for every phase dispatch (initial Step 5.x AND Path B/C re-invocations). Inline nit-attack sub-paths (Step 5.7) do not invoke models — they apply Edit-tool changes directly, no model selection involved.

**Model overlay resolution:** Before each phase dispatch, resolve the overlay file using `claude/model-overlays/<MODEL_SLUG>.md` where `MODEL_SLUG` is the versioned slug for `$PHASE_MODEL` (e.g., `opus-4-7` for the opus family at the current Anthropic version). Fallback chain: versioned slug (`opus-4-7.md`) → family name (`opus.md`) → generic (`claude.md`) → no overlay (no-op). When an overlay file resolves and is non-empty (≤ 2KB), read its content and substitute the `{{MODEL_OVERLAY_NOTE}}` placeholder in the phase prompt template with:

```
Model overlay (claude/model-overlays/<resolved-file>):
[contents of the overlay file]
```

When no overlay file resolves: `MODEL_OVERLAY_NOTE=""` (empty, no-op). A missing overlay is silent — backward compatible, defaults inherited from current behavior. The fallback chain ensures `claude.md` (generic) carries universal hints when no model-specific file exists; if `claude.md` itself is missing, no overlay note is emitted and behavior is identical to today.

**Charter summary resolution:** Before each phase dispatch, resolve the `{{CHARTER_SUMMARY}}` placeholder in the phase prompt template by invoking `claude.lib.pipeline.charter_summary.extract_charter_summary(charter_field)` where `charter_field` is the value of the `**Charter:**` line in `docs/pipeline-state.md`. The helper returns either the first 800 characters of the charter's `## Goal` body (hard-truncated via `text[:800]` — NOT word-bounded) or the literal string `(no charter)` when the charter is `(none)`, absent, unreadable, or lacks a `## Goal` section. Substitute the returned string literally for `{{CHARTER_SUMMARY}}` in every phase template (analyze, plan, implement, review, docs) at dispatch time — NOT at template-load time, so charter edits mid-run propagate to later phases. The helper is pure stdlib Python (no subprocess, no LLM); contract bound by `claude/lib/pipeline/tests/test_charter_summary.py`. This placeholder is the operator-trust bucket — the 800-char cap IS the length bound; the helper applies no further sanitisation because the charter is committed source. Treat as additive to the existing `**Placeholder Substitution Safety**` contract in `reference.md` (the 7 rules there continue to apply to every other `{{...}}` placeholder).

**MCP guidance resolution:** Before each phase dispatch, resolve the `{{MCP_GUIDANCE}}` placeholder in the phase prompt template by invoking `claude.lib.pipeline.mcp_guidance.extract_mcp_guidance(charter_field, phase, connected_mcps)` where `charter_field` is the same `**Charter:**` value used for `{{CHARTER_SUMMARY}}` and `phase` is the dispatching phase slug (`analyze` | `plan` | `implement` | `review` | `docs` | `uat`). The `connected_mcps` set is ESTABLISHED at Step 0.5 via the single `claude mcp list` probe and cached as `CONNECTED_MCPS` for the whole run — REUSE that cached set here (no second probe). If Step 0.5 was skipped (CLI unavailable) or `CONNECTED_MCPS` is empty, treat the connected set as empty (every phase then resolves to the no-op sentinel `(no MCP routing)`). The helper reads the charter's `## MCP Routing` section, keeps only entries whose server is BOTH declared in the charter AND in the connected set AND applies to the current `phase` (no `| phases:` clause or the literal `all` = every phase), and returns a guidance block (a preamble plus one `- <server>: <purpose>` bullet per surviving entry, hard-capped at 1500 chars) or `(no MCP routing)` when nothing applies. **Charter-first with a connected-set default fallback:** an explicit `## MCP Routing` section wins entirely (the default map is never merged); a section containing only `none`/`skip` preserves the operator opt-out (`(no MCP routing)`); when the section is ABSENT, the helper falls back to a built-in default routing map intersected with the connected set, so connected MCPs are surfaced into phases without requiring charter editing. The fallback yields `(no MCP routing)` only when the connected set is empty or the charter is `(none)`/missing. Substitute the returned string literally for `{{MCP_GUIDANCE}}` in every phase template at dispatch time (NOT at template-load time, so charter edits mid-run propagate). The helper is pure stdlib Python (no subprocess, no LLM) — the orchestrator owns the one `claude mcp list` probe; contract bound by `claude/lib/pipeline/tests/test_mcp_guidance.py`. This is a second operator-trust placeholder governed by Rule 8 of the `**Placeholder Substitution Safety**` contract in `reference.md`.

---

##### Step 5.1: Log Feature Start

Append to the feature's `### Run Log` section in the feature file (prepend a blank line before non-first entries; the first entry immediately after `### Run Log` has no leading blank line; ensure the section ends in a single `\n`):

```
**Run [YYYY-MM-DD HH:MM]:** Started pipeline
```

Then immediately fire the **TASKS panel helper (TodoWrite)** with tag `feature-start` and the **Progress beacon helper** with tag `feature-start` (see Step 5.0). This is required — without the TodoWrite seed call here, the host UI's TASKS panel stays empty for the whole feature run and the user cannot see what the pipeline is working on.

Also emit a cost-tracking start event (F23 `cost_log.py`), then call `cost_log.py end`/`start` at every phase transition (analyze → plan → implement → review → merge) so `/cost-report` can show the feature's execution trail. Every call passes `--dispatch-mode` and `--agent-id` (subagent ID from the Agent tool, or a transient `pipeline-$$-${RANDOM}-${phase}` ID inline). See `reference.md` § "Step 5.1: Cost-Tracking Event Calls — Full Details" for the per-transition bash.

Write/update `docs/pipeline-state.md`:
```markdown
# Pipeline State

**Feature file:** [path]
**Feature:** [index] / [total]
**Name:** [type/name]
**Step:** analyze
**Review cycles:** 0
**Replan count:** 0
**Path D attempted:** false
**Started:** [YYYY-MM-DD HH:MM]
**Phase Mode:** <subagent|inline>
**Last phase agent:** [subagent ID, only when Phase Mode = subagent]
**Charter:** [path to docs/charter.md, or (none) when --no-charter is set]
**Review style:** [always teams | never teams | orchestrator decides]
**Probe depth:** $(bash claude/lib/pipeline/detect_repo_class.sh --probe-depth)
**Repo class:** $(bash claude/lib/pipeline/detect_repo_class.sh --repo-class)
**MCP connected:** [comma-list of connected server names from Step 0.5, or (none)]
**MCP wired:** [comma-list of MCPs wired this run by Step 0.5, or (none)]
**Loop:** on
**Max loops:** unlimited
**Loop count:** 0
**Prev renew set:** (none)
**Loop no-progress count:** 0
```
<!-- DEFERRED: ~/.claude/rules/workflow.md § Pipeline State Schema gains two new bullets (`**Probe depth:**`, `**Repo class:**`) — out-of-repo edit (user's global rules). Advisory schema doc, not load-bearing for runtime. Tracked as follow-up in docs/progress.md ## Deferred section. -->
<!-- DEFERRED: ~/.claude/rules/workflow.md § Pipeline State Schema should also gain two new bullets (`**MCP connected:**`, `**MCP wired:**`) added by Step 0.5 (OQ-5 follow-up). Advisory schema doc; not load-bearing for runtime. Same out-of-repo advisory pattern as Probe-depth/Repo-class above. -->

Default value for new features: `subagent`. `inline` appears only in legacy state files written under the prior heuristic policy or in Path N nit-attack sub-paths.

**Charter field:** Set `**Charter:**` to the resolved charter file path when `--charter <path>` is given or when Step 0 writes `docs/charter.md`. Set to `(none)` when `--no-charter` or `--max-questions 0` is in effect. On resume (Step 3), read the saved `**Charter:**` value and restore it for the in-flight feature — do not re-run Step 0 if `**Charter:**` points to a valid existing file.

**Review style field:** Sits in the same state-file template block as `**Phase Mode:**` (the per-feature dispatch-routing field). Resolve `**Review style:**` in this priority order:
1. If `PIPELINE_TEAMS_OVERRIDE = always` → write `always teams`.
2. If `PIPELINE_TEAMS_OVERRIDE = never` → write `never teams`.
3. If `PIPELINE_TEAMS_OVERRIDE = decide` AND a charter exists at the `**Charter:**` pointer AND `docs/charter.md` contains a `## Review style` section with one of the canonical values (`always teams` / `never teams` / `orchestrator decides`): write that value verbatim.
4. Otherwise (no override, no charter, or charter section absent/unrecognized): write `orchestrator decides`.

The field is **sticky for the duration of the feature** — Path B / Path C / Retry re-reviews re-read this value at Step 5.6.0 but never recompute the heuristic mid-feature. The `**Review style:**` itself is not mutated by Path B/C/Retry. (Path C re-plan that flips `**Feature class:**` does change the next review's heuristic outcome when the style is `orchestrator decides` — this is intentional and aligned with the "decision computed at review boundary" contract.)

---

##### Step 5.2: Write Analysis File

**If Phase Mode is `subagent`:** Emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-pre`) per the helpers in Step 5.0. Dispatch this phase via the Agent tool using the prompt template from `reference.md` § "Step 5.x: Phase Subagent Dispatch — Prompt Templates" matching `<!-- PHASE: analyze -->`. Substitute placeholders with current feature values. Pass `model: opus` (the phase default from the model defaults table) in the Agent tool parameters. Capture the returned `<task-notification>` XML; on `status: completed`, read the resulting on-disk artifact (`{{ANALYSIS_PATH}}`), emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-done`), and continue. Update `docs/pipeline-state.md` `**Last phase agent:**` with the subagent ID. Skip the inline instructions below. On `status: failed`, follow the same failure handling as the inline path (log to feature run log, advance state, skip to next feature).

**Otherwise (Phase Mode is `inline`, legacy state files only — see Step 5.0):** Execute the inline instructions, which are the canonical analyze-phase spec (Versioning ladder, project-type detect, cross-feature intel injection, analysis-file template, `**Analysis:**` pointer update, validate-against-feature). Full body relocated to `reference.md` § "Step 5.2: Write Analysis File — Inline Body". Skip if `--restart-from` is `plan`/`implement`/`review`. On completion, set pipeline state step = "plan".

---

##### Step 5.3: Generate Plan + Prompts + Progress

**If Phase Mode is `subagent`:** Emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-pre`) per the helpers in Step 5.0. Dispatch this phase via the Agent tool using the prompt template from `reference.md` § "Step 5.x: Phase Subagent Dispatch — Prompt Templates" matching `<!-- PHASE: plan -->`. Substitute placeholders with current feature values. Pass `model: opus` (the phase default from the model defaults table) in the Agent tool parameters. Capture the returned `<task-notification>` XML; on `status: completed`, read the resulting on-disk artifacts (`{{PLAN_PATH}}`, `{{PROMPTS_PATH}}`), emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-done`), and continue. Update `docs/pipeline-state.md` `**Last phase agent:**` with the subagent ID. Skip the inline instructions below. On `status: failed`, follow the same failure handling as the inline path (log to feature run log, advance state, skip to next feature).

**Otherwise (Phase Mode is `inline`, legacy state files only — see Step 5.0):** Execute the inline instructions, which are the canonical plan-phase spec (plan conventions, plan-file + prompts-file templates, `docs/progress.md` pointer updates, self-review checklist). Full body relocated to `reference.md` § "Step 5.3: Generate Plan + Prompts + Progress — Inline Body". Skip if `--restart-from` is `implement`/`review`. On completion, set pipeline state step = "implement".

---

##### Step 5.4: Create Feature Branch

Skip if `--restart-from` is `implement` or `review` (branch should already exist). **Verify** the current branch matches the expected feature branch:
```bash
CURRENT=$(git branch --show-current)
EXPECTED="<type>/<feature-name>"
if [ "$CURRENT" != "$EXPECTED" ]; then
  echo "WARNING: Current branch '$CURRENT' does not match expected '$EXPECTED'. Verify you are on the correct feature branch."
fi
```
If on `$BASE` (main/master): **STOP** with "Cannot implement on $BASE. Check out the feature branch or omit --restart-from to create one."

Detect the base branch using the standard snippet from `~/.claude/rules/workflow.md` § Base Branch Detection:
```bash
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
[ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}')
[ -z "$BASE" ] && BASE="main"
git rev-parse --verify "$BASE" 2>/dev/null || echo "ERROR: Base branch '$BASE' not found locally."
```

```bash
git checkout "$BASE"
git pull origin "$BASE" 2>/dev/null || true
git checkout -b <type>/<feature-name>
```

If the branch already exists: `git checkout <type>/<feature-name>` (do not create).

---

##### Step 5.5: Implement

Skip if `--restart-from` is `review`. Optional `worker:` task-prompt header is acknowledged but ignored in this iteration (behaves as `worker: claude`; see `claude/lib/worker-provider/interface.md`).

The implement phase classifies the feature, routes by class, and (for dev features) runs paired TDD subagent dispatch. Full body — **Step 5.5.0** (classify dev vs non-dev: `--no-tdd` short-circuit, `**Type:**` override, prefix-derived class table), **Step 5.5.1** (route by class), **Step 5.5.2** (non-dev standard `<!-- PHASE: implement -->` dispatch / inline `Skill: implement-plan`), and **Step 5.5.3** (dev TDD path: per-task RED `tdd-test-writer` → GREEN `tdd-implementer` Agent calls, `model: sonnet`) — is relocated to `reference.md` § "Step 5.5: Implement — Full Details". On completion set pipeline state step = "review"; any task still `doing` → Run Log `Status: FAILED` and skip to next feature.

**Step 5.5.3a: Group tasks by phase and assess parallelisability.**

Before the per-task TDD loop (Step 5.5.3), partition `todo` tasks by phase number. For each phase with N > 1 tasks, check pairwise `Files:` overlap (per `implement-plan` SKILL.md Step 1.5). If zero overlap AND `--no-parallel` is not set: emit a single beacon line

```
PARALLEL_DISPATCH: phase=<X>, streams=<N>, branches=[<comma-separated list>]
```

then dispatch all N (tdd-test-writer → tdd-implementer) pairs in **one Agent-batch message** with `isolation: "worktree"` per pair. Each pair runs the red→green sequence inside its own worktree. The lead waits for all to complete, then squash-merges per `claude/rules/agents-worktrees.md` § Lead Merge Protocol.

If `--no-parallel` was passed OR tasks share files OR the phase has only 1 task: fall back to the per-task sequential loop in `reference.md` § "Step 5.5: Implement — Full Details".

**Step 5.5.7: Hook smoke-test gate (additive verify).**

After Step 5.5.2 / 5.5.3 complete (regardless of dev/non-dev path), before advancing to review, discover and run every hook smoke test under `claude/hooks/tests/`:

- Discover via `find claude/hooks/tests -name 'test_*.sh' -type f` (sorted).
- For each file, run `bash <file>`. On any non-zero exit, fail the verify step with `HOOK_SMOKE_FAILED: <test-path>` and skip to next feature (Run Log Status: FAILED).
- On all pass, log `HOOK_SMOKE_PASS: <N> tests`.
- If the directory is absent OR the discovery produces zero files, log `HOOK_SMOKE_NO_TESTS_FOUND` and continue (do not fail).

The gate is ADDITIVE to build/test verification already performed by `/implement-plan`. See `claude/skills/pipeline/reference.md` § "Step 5.5.7: Hook Smoke-Test Gate — Full Details" for the canonical bash body and idempotency contract; `claude/hooks/CLAUDE.md` § "Pipeline Smoke Gate" carries author-facing guidance for new smoke tests.

---

##### Step 5.6.0: Compute Teams Decision (per-feature, before Step 5.6 dispatch)

Before every Step 5.6 review dispatch (initial + Path B/C/Retry re-review), the orchestrator resolves `dispatch_with_teams` from the fresh `**Review style:**` in `docs/pipeline-state.md`: `always teams` → true; `never teams` → false; `orchestrator decides` → heuristic (`DIFF_LINES > 500` OR `DIFF_FILES > 8` OR `FEATURE_CLASS = dev`). When true it `export`s `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (symmetric unset after, preserving a pre-existing host value) so the `<!-- PHASE: review -->` template invokes `/pipeline-review` teams-on; otherwise the template passes `--no-teams`. A `**TeamsDecision …**` Run Log line records the rationale. Sticky per feature (re-read, never recomputed per cycle). Path N is exempt (Edit-tool only). Full body (state reads, heuristic bash, env-var lifecycle, stickiness + Path N exemption): `reference.md` § "Step 5.6.0: Compute Teams Decision — Full Details".

---

##### Step 5.6: Review

**`--no-review` short-circuit:** If `NO_REVIEW=true` (set by `--no-review` at Step 1), skip the review dispatch entirely. Synthesise a Path A (passed) outcome:
1. Write an empty review file at the Versioning-Convention next-version path (e.g., `docs/review-v<N+1>.md`) containing the single line `## Review skipped via --no-review (Step 5.6)`. Use Bash heredoc per § Subagent Write-Surface Convention.
2. Update the `**Review:**` pointer in `docs/progress.md` to the new path (Edit tool).
3. Emit the `phase-done` beacon as if review completed normally.
4. Proceed to Step 5.7 — path detection Row 1 (0 findings) will route to Path A.

**If Phase Mode is `subagent`:** Emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-pre`) per the helpers in Step 5.0. Dispatch this phase via the Agent tool using the prompt template from `reference.md` § "Step 5.x: Phase Subagent Dispatch — Prompt Templates" matching `<!-- PHASE: review -->`. Substitute placeholders with current feature values. Pass `model: opus` (the phase default; the `/pipeline-review` skill applies REVIEW.md `review-model:` override internally if present) in the Agent tool parameters. Capture the returned `<task-notification>` XML; on `status: completed`, read the resulting on-disk artifact (review file via `docs/progress.md` `**Review:**` pointer), emit phase transition signal (progress beacon **and** TodoWrite update, tag=`phase-done`), and continue. Update `docs/pipeline-state.md` `**Last phase agent:**` with the subagent ID. Skip the inline instructions below. On `status: failed`, follow the same failure handling as the inline path (log to feature run log, advance state, skip to next feature).

**Teams-mode dispatch-shape preflight beacon:** Immediately before the `Agent` dispatch above, the orchestrator MUST emit the following beacon to its own assistant turn (one line, verbatim):

```
TEAMS_DISPATCH_SHAPE_REMINDER: bundle all N reviewer Agent calls in this single turn
```

This beacon is a no-op for the harness — it is a self-reminder to the lead that the review subagent (which itself dispatches the 5-agent base panel when `teams_mode=true`) MUST emit those N `Agent` calls in a single assistant turn. See `claude/skills/review/SKILL.md` § Teams dispatch shape — MANDATORY for the worked example and the three F6 anti-patterns (wrap-as-one, one-per-turn, fall-back-to-inline).

**Otherwise (Phase Mode is `inline`, legacy state files only — see Step 5.0):** Execute the inline instructions below. New features always run as `subagent`; this branch is preserved only for resuming features that were already running under the previous heuristic-based policy.

Invoke `/pipeline-review` via the Skill tool. Teams mode in `/pipeline-review` is default-on as of the flag-cleanup refactor; the orchestrator's Step 5.6.0 decides whether to opt out via `--no-teams`. If `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set in the environment (orchestrator decided `dispatch_with_teams=true`), invoke with `/pipeline-review`'s teams default (no extra flag):

```
Skill: pipeline-review
```

If the env var is NOT set (orchestrator decided `dispatch_with_teams=false`), pass `--no-teams` to opt out of the new default:

```
Skill: pipeline-review --no-teams
```

Note: `/pipeline-review` is default-on for teams as of this refactor. The orchestrator decides per-feature via Step 5.6.0 whether to pass `--no-teams`. The skill was renamed from `/review` per F20 to avoid collision with the harness's built-in GitHub PR-review template; see `claude/CLAUDE.md.template` Lean Conventions for the regression target.

After completion: proceed to Step 5.7.

---

##### Step 5.7: Determine Review Path

Read `docs/progress.md` (fresh read — review may have modified it).
Read the review file from the `**Review:**` pointer in progress.md.

**Findings-leak preflight (before path detection):**

Before evaluating the path-detection table, count findings in the active review file and verify each one is accounted for via Path M / Path B reopen / Defer state transition. This preflight catches the F21 root-cause failure mode (Path M cherry-pick + prose `Defer.` remainder) before it propagates to `/ppr`.

```
TOTAL_FINDINGS = (count of `severity: blocking` entries)
               + (count of `severity: non-blocking` entries)
               + (count of `severity: nit` entries)

APPLIED_INLINE     = count of findings explicitly marked as applied inline in the review file
                     (Path M / Path N auto-fix commit — reviewer's "### Path M inline fixes (this commit)"
                     block, Step 7.5 nit auto-fix manifest, or equivalent)
REOPENED           = count of reopened tasks in `progress.md` with note `reopened: review-vN`
                     matching the current review file's N
DEFERRED_TO_TABLE  = count of new rows appended to `progress.md` `## Deferred` table
                     citing the current review file
DEFERRED_TO_FEATURE = count of new feature blocks appended to the active feature file
                      citing the current review file

ACCOUNTED = APPLIED_INLINE + REOPENED + DEFERRED_TO_TABLE + DEFERRED_TO_FEATURE
```

If `TOTAL_FINDINGS > ACCOUNTED`, halt with the canonical beacon:

```
FINDINGS_LEAK: <N> findings unaccounted for in <review-file-path>
Unaccounted IDs: <comma-separated finding identifiers extracted from the review file>
```

where `<N> = TOTAL_FINDINGS - ACCOUNTED`. The orchestrator MUST NOT advance to path selection until the operator either (a) reopens / defers / inlines the unaccounted findings via one of the Step 7.6 contracts in `claude/skills/review/SKILL.md`, or (b) explicitly overrides via manual confirmation logged in the feature Run Log. See `claude/skills/review/SKILL.md` Step 7.6 (Path M / Defer Enforcement Contract) for the upstream contract this preflight enforces.

**Path detection:**

Check conditions in order — first match wins.

| # | Condition | Path |
|---|-----------|------|
| 0 | `git diff $BASE...HEAD` is empty AND review file contains "BLOCKED", "nothing to review", "empty diff", or "implementation no-op" (case-insensitive) | **FAILED (no changes)** |
| 1 | No review file exists, OR review file has 0 blocking + 0 non-blocking + 0 nit findings | **A** (passed) |
| 1.5 | Review file has 0 blocking + 0 non-blocking + N nit findings (N>0) — nits survived `/pipeline-review` Step 7.5 auto-fix | **N** (inline nit-attack, then re-route via Step 5.7) |
| 1.7 | Review file has 0 blocking + N>0 non-blocking findings AND Path M gate predicate holds (severity ∈ {non-blocking, nit} ∧ lines_changed ≤ 5 ∧ files_changed ≤ 1 per finding ∧ total_finding_count ≤ 3 ∧ total_lines_across_findings ≤ 8 ∧ every finding has mechanical Suggestion:) | **M** (inline mini-fix, then re-route via Step 5.7) |
| 1.8 | Review file has 0 blocking + N>0 non-blocking findings that are **in-scope fixable** (concern this feature's `git diff $BASE...HEAD`; concrete bounded fix) AND the Path M gate does NOT hold (fix exceeds the mechanical/size bounds) | **B** (orchestrator reopens the relevant plan task(s) with a `reopened: review-vN` note → re-implement). See the Pre-Path-A fixable-findings sweep below. |
| 2 | Review file has blocking or non-blocking findings AND progress.md has tasks with `reopened:` notes | **B** (fixable) |
| 3 | Review file contains "beyond current scope" or all findings require re-planning | **C** (scope change) |
| 4 | Review output was "BLOCKED" (sanity gate, secrets, all agents failed) | **Retry** |

Per-row rationale for the non-obvious rows (0, 1.5, 1.7, 1.8): see reference.md § Step 5.7 Path-detection row rationale

**Pre-Path-A fixable-findings sweep (REQUIRED — defer is the exception, not the default):** Before the orchestrator may route a feature to Path A, every non-blocking finding in the review file MUST be dispositioned as either *fixed* or *legitimately deferred*. A finding is **in-scope fixable** when it concerns code or tests introduced/modified by THIS feature's `git diff $BASE...HEAD` AND has a concrete, bounded fix. In-scope fixable findings MUST be fixed before merge — never carried as deferred debt:
- meets the Path M gate predicate (small/mechanical) → **Path M** (Row 1.7);
- exceeds the Path M gate but is in-scope and bounded → **Path B** (Row 1.8): the orchestrator reopens the relevant plan task(s) in `docs/progress.md` with a `reopened: review-vN` note and re-implements via subagent.

**Defer (`## Deferred`) is reserved for findings that genuinely belong to a future iteration:** cross-feature dependencies, work requiring a separate migration/ticket, findings on code OUTSIDE this feature's diff, or items with no in-scope fix. A non-blocking finding on this feature's own diff with a known fix is NOT a defer candidate — fix it.

**Orchestrator overrides a premature defer:** if the review subagent routed an in-scope fixable finding to `## Deferred`, the orchestrator removes that premature `## Deferred` row, routes the finding to Path M or Path B per the sweep, and only proceeds to Path A once the finding is fixed (or genuinely re-classified as future-iteration work). The orchestrator's objective is a clean Path A (0 outstanding in-scope fixable findings); it **pushes toward Path A** rather than merging with avoidable debt. This sweep is a hard precondition of Path A entry (Step 5.8).

**Row 2 nit-preamble option (`PIPELINE_NIT_FIRST=1`):** When blocking/non-blocking findings exist AND nit findings also exist, the orchestrator MAY attack nits inline first as a preamble to Path B. This is opt-in via the `PIPELINE_NIT_FIRST=1` environment variable. Default off (deterministic). When enabled: run an inline nit-fix pass (same logic as Path N), commit `fix: minor code quality improvements`, then continue into Path B subagent dispatch for the blocking/non-blocking work. Rationale: nits are cheap to fix inline and reduce noise in the next review cycle's diff — but the heavy work (blockers/non-blockers) ALWAYS goes through subagent dispatch.

For **FAILED (no changes)**: append to Run Log the canonical-format failure line `- YYYY-MM-DD HH:MM: FAILED — PR #N/A merged as N/A. <class> feature. analysis-vA / plan-vP / prompts-vP / review-vR. [N] Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 0 files, +0/-0. <reason summary>.`, log to the pipeline summary as failed (not already-shipped — that category is for pre-existing work on `$BASE`), skip to the next feature.

This is the canonical format defined in `docs/analysis-v35.md` § 3.1; see `reference.md` § "Run Log Canonical Format" for the field-definitions table and should-match / should-NOT-match examples. The orchestrator MUST invoke `bash claude/lib/pipeline/format_runlog.sh validate "<candidate-line>"` before appending any Run Log entry (Path A success, Path B failure, Path C failure, FAILED-no-changes, etc.). On non-zero exit the append is aborted and `RUNLOG_FORMAT_INVALID: <reason>` is logged to stderr. The helper at `claude/lib/pipeline/format_runlog.sh` is the single source of truth for the validation regex — do not re-derive the pattern elsewhere.

For mixed findings (some fixable, some scope-change): treat as **Path B** first — fix the reopened tasks, then re-review will catch remaining issues.

**Inline-mode boundary (REQUIRED INVARIANT):** Inline tool dispatch (direct `Skill:`, direct `Edit`/`Bash` outside an Agent) is permitted ONLY in Path N, Path M, and the optional Row-2 nit preamble. Every other path — A's CI fix loop, B's re-implement, C's re-plan, Retry's re-review — dispatches via the `Agent` tool when `**Phase Mode:** = subagent` (the default), preserving context isolation. See `reference.md` § "Step 5.8: Execute Path — Full Details" for per-path dispatch detail.

---

##### Step 5.8: Execute Path

**`--no-ppr` short-circuit (Path A only):** If `NO_PPR=true` (set by `--no-ppr` at Step 1) AND the path resolved by Step 5.7 is Path A: halt the feature immediately. Append to the feature Run Log: `Status: COMPLETED (--no-ppr halt; no push/PR/merge)`. Skip Path A push/PR/CI/merge, the Post-Merge Verification Gate, and the Documentation Update Phase. Emit `feature-done` (the feature is not a failure — it completed implement+review successfully; the merge step was intentionally skipped). Advance to the next feature. This short-circuit does NOT apply to Path B, Path C, Path N, Path M, or Retry — those paths re-enter the review loop until Path A is reached, at which point the `--no-ppr` short-circuit fires.

Full per-path flows are defined in `reference.md` § "Step 5.8: Execute Path — Full Details":

- **Path A — Review Passed:** **Precondition:** the Step 5.7 Pre-Path-A fixable-findings sweep is satisfied — 0 outstanding in-scope fixable non-blocking findings (any such finding must already be fixed via Path M/B, not deferred). Then: push → create PR → CI monitor (max 3 fix attempts) → auto-merge → post-merge cleanup → CD health check → log SUCCESS. The orchestrator drives toward this state (push for Path A); it does not enter Path A while avoidable in-scope debt remains.
- **Path B — Fixable Findings:** re-implement → re-review, capped at 5 review cycles. **Always honors `**Phase Mode:**` from `docs/pipeline-state.md`** — re-implement and re-review dispatch via `Agent` tool when `Phase Mode = subagent` (the default). Optional `PIPELINE_NIT_FIRST=1` runs a Path-N-style inline nit preamble first.
- **Path C — Scope Change:** re-plan (capped at 1) → re-implement → re-review. Same `Phase Mode` honoring as Path B.
- **Path D — Fresh-context Salvage:** one-shot `general-purpose` subagent dispatch armed with the full Run Log + review history + plan/prompts + current diff. Fires only after Path C exhausts AND `**Path D attempted:**` is `false`. On any failure (subagent error, lingering findings, blocked status, budget breach mid-dispatch), proceeds directly to the feature-failed terminal — never loops back to Path B / C / N / M / Retry. See `reference.md` § "Path D — Fresh-context Salvage" for the full body and the no-infinite-loop backstop.
- **Path N — Nit-Only Inline:** Edit-tool nit fixes inline → sanity gate → commit → re-route via Step 5.7. Capped at 2 cycles. **A legitimate inline path (alongside Path M).**
- **Path M — Inline Mini-Fix:** Gate-predicate-qualified small non-blocking fixes inline via Edit tool → sanity gate → commit (`fix: address review feedback inline`) → re-route via Step 5.7. Capped at 2 inline cycles (`**Inline cycles:**` state field). Edit-tool only — snapshot-revert + Path B escalation on sanity-gate failure. See `reference.md` § Path M for full body.
- **Retry — BLOCKED:** retry /pipeline-review on transient failures only, capped at 3 attempts. Re-review honors `Phase Mode`.

**Findings-leak post-routing check:** After Path M or Path N completes its inline fix commit, re-run the Step 5.7 preflight accounting check against the same review file. If `TOTAL_FINDINGS > ACCOUNTED` after the inline path runs, emit the canonical beacon `FINDINGS_LEAK: <N> findings unaccounted for after <Path M|N> commit <sha>` (naming the unaccounted finding IDs from the review file) and halt the feature for operator review. Path B re-implement followed by re-review re-enters Step 5.7, so the preflight catches leaks at the next cycle entry naturally — no additional post-routing call needed for Path B / Path C / Retry. See `claude/skills/review/SKILL.md` Step 7.6 for the underlying Path M all-or-none contract this check enforces.

Select the path from Step 5.7, load the corresponding flow from `reference.md`, and execute. **Inline tool dispatch is forbidden in Paths A, B, C, and Retry when `Phase Mode = subagent` — those paths must use `Agent` tool dispatch with the corresponding `<!-- PHASE: ... -->` template.** Path N and Path M are the only legitimate inline paths (plus the optional Row-2 nit preamble); see § "Inline-mode boundary (REQUIRED INVARIANT)" above.

##### Path B Convergence: WTF-Likelihood Self-Regulation

See reference.md § Path B Convergence: WTF-Likelihood Self-Regulation

---

##### Step 5.9: Log Feature Complete

Append to the feature's `### Run Log` section (prepend a blank line before non-first entries; the first entry immediately after `### Run Log` has no leading blank line; ensure the section ends in a single `\n`):
```
- 2026-05-18 14:22: SUCCESS — PR #33 merged as a1b2c3d. non-dev feature. analysis-v35 / plan-v36 / prompts-v36 / review-v33. 0 Path B cycles, 0 inline cycles. 0 blocking, 0 non-blocking, 0 nits. 3 files, +145/-2. Unified Run Log format with helper script and validation regex.
```

Then emit phase transition signal — tag=`feature-done` on success, `feature-failed` on any failure path (CD halt, post-merge regression, budget halt, implementation error). The signal includes both the progress beacon AND the TodoWrite update per Step 5.0; the TodoWrite update is what flips the host UI's TASKS panel from showing the in-progress feature to showing it complete (or cancelled with reason).

> **CD halt:** If the CD health check in Step 5.8 Path A detects failing workflows on the base branch, the feature is logged as `FAILED (CD health check)` and the pipeline halts — it does NOT proceed to the next feature. This prevents building on a broken base. If `gh` is unavailable, the check is skipped with a warning (no halt).

Update pipeline state: advance to next feature.

---

### Post-Merge Verification Gate

After a feature's squash-merge lands on `main` (Path A), the pipeline runs a verification command to guard against regressions. The command resolves by precedence (`PIPELINE_POSTMERGE_CMD` → executable `docs/.pipeline-postmerge.sh` → project-type auto-detect → silent skip), gated by a **probe-block precondition**: if `Production-Probe: BEGIN` is absent from the feature's most-recent `### Run Log` entry, append `PostMerge: FAILED (probe missing)` and route to the failure handler — `POSTMERGE_OK` is NEVER appended without a probe block. On non-zero exit the gate preserves the squash SHA on a `${feature}-postmerge-failed` branch, reverts via `git reset --hard HEAD~1`, logs `PostMerge: FAILED (...)`, and continues to the next feature (no halt). On success it appends `POSTMERGE_OK: <cmd>` and dispatches a best-effort `Skill: learn`. Escape hatch `SKIP_POSTMERGE_VERIFY=1`. Full body (command-resolution precedence, timeout, escape hatch, failure semantics, backward-compat, `/learn` dispatch): `reference.md` § "Post-Merge Verification Gate — Full Details". See also `reference.md § Production-Probe block specification`.

---

### UAT Phase

Best-effort, NON-BLOCKING UAT phase between the Post-Merge Verification Gate (`POSTMERGE_OK: <cmd>` success path) and the Documentation Update Phase. Dispatches `subagent_type: uat-runner` (`model: sonnet`, `<!-- PHASE: uat -->` template) to RENDER and CLICK RBAC role flows + every button. Skips silently when no browser surface is detected (`playwright.config.*`, `@playwright/test`, or `e2e/`) — pipelinekit itself skips here. Escape hatch `PIPELINE_SKIP_UAT=1` / `--no-uat`. On FAIL the orchestrator appends rows to a `## UAT Findings` table in the feature file (`docs/features-*.md`) and writes `UAT: FAILED` to the Run Log — NEVER reverting a merged feature; the outer loop's renew collection consumes the findings. Diff-scoped by default; `--uat-full-every-feature` / loop-end forces the full sweep. Full body (web-surface detect, escape hatch, phase mode + beacon, subagent dispatch, modes, on-FAIL, non-fatal failure semantics, position invariants, run/loop-end full sweep, no-overlap boundary): `reference.md` § "UAT Phase — Full Details".

---

### Documentation Update Phase

Best-effort docs phase after the Post-Merge Verification Gate's `POSTMERGE_OK: <cmd>`. Dispatches `subagent_type: docs-writer` (`model: sonnet`, `<!-- PHASE: docs -->` template) to read the merged squash diff + `docs/progress.md`, write application docs ONLY in `documentation/`, and land a separate `docs: <feature>` commit on `$BASE` (NEVER `git commit --amend`). Escape hatch `PIPELINE_SKIP_DOCS=1` / `--no-docs`. Non-fatal: a docs failure logs `Docs: SKIPPED (subagent error)` and proceeds to `feature-done` without downgrading the feature's terminal status. Full body (execution order, escape hatch, phase mode + beacon, subagent dispatch + placeholders, output-boundary contract, non-fatal failure semantics, position invariants): `reference.md` § "Documentation Update Phase — Full Details".

---

### Step 5.10: Terminal Cleanup

Runs ONLY when the per-feature loop completed cleanly — every feature successfully merged.

**Predicate (gate the terminal write):**
```bash
if [ "${#failed_list[@]}" -eq 0 ] && [ "$features_merged" -eq "$total_features" ]; then
  TERMINAL=1
else
  TERMINAL=0
fi
```

When `TERMINAL=1`, append/replace these fields in `docs/pipeline-state.md`:

- Replace `**Step:** <phase>` with `**Step:** done`.
- Append (or replace if present) `**Completed:** $(date -u +%Y-%m-%dT%H:%M:%SZ)`.
- Append (or replace if present) `**Features merged:** $features_merged`.

When `TERMINAL=0` (any feature failed, Path C escalation stuck, Path D salvage stuck, BUDGET_EXCEEDED hit, or pipeline halted mid-flight): SKIP terminal cleanup entirely. The state file is left at its mid-flight position so a subsequent `/pipeline --restart-from <phase>` can resume cleanly.

After terminal cleanup, proceed to Step 6 Final Summary which prints the run report.

<!-- OQ-3 resolved: (d) html-archive variant — features.md → docs-source/feature-history.md, see /post-merge Step 12 + claude/lib/pipeline/features_pruner.py -->

Per-feature pruning of done blocks out of `docs/features.md` does NOT live in Step 5.10 — it runs inside `/post-merge` Step 12 (the workflow-hygiene block) via `claude/lib/pipeline/features_pruner.py`. Step 5.10 is the terminal cleanup gate; pruning is a per-feature concern that fires after each successful merge.

---

### Step 5.11: Outer Loop Control

Runs immediately after `TERMINAL=1` would fire in Step 5.10, BEFORE the terminal write, unless `**Loop:** off` (i.e. `--no-loop` was passed).

**When `**Loop:** off`:** Step 5.11 is a no-op. Fall through directly to Step 5.10's terminal write (fields + Step 6). Single-trip behaviour is preserved exactly as before this feature — AC6.

**When `**Loop:** on` (default):**

Read the current `**Loop count:**`, `**Prev renew set:**`, and `**Loop no-progress count:**` from `docs/pipeline-state.md`.

**(a) Run the existing Step 1.6 renew collection** over `FAILED ∪ Unprocessed ∪ Deferred ∪ ## UAT Findings`:
- Collect FAILED features (last Run Log entry `Status: FAILED`).
- Collect Unprocessed features (no Run Log / no status line).
- Collect Deferred items from `docs/progress.md` `## Deferred` section.
- Collect `## UAT Findings` items from the feature file if that section exists; an absent `## UAT Findings` section contributes the empty set — no error. (Reuse Step 1.6 logic; do NOT redefine `--renew` semantics.)

Let `NEW_SET_SIZE` = total count of items collected above.

**(b) CLEAN exit — empty renew-set:**
If `NEW_SET_SIZE == 0`: fall through to Step 5.10 terminal write (fields + Step 6). The pipeline terminates cleanly with an empty queue.

**(c) STALLED no-progress guard (guaranteed terminator):**
Read `PREV = **Prev renew set:**` from state (treat `(none)` as "no previous trip").
- If `PREV != (none)` and `NEW_SET_SIZE >= PREV` (renew-set did NOT strictly decrease):
  - Increment `**Loop no-progress count:**` by 1 and write to state.
  - If `**Loop no-progress count:** >= 2`: exit **STALLED**.
    - Log: `STALLED: renew-set size did not strictly decrease for 2 consecutive loops (size=$NEW_SET_SIZE). Exiting outer loop to prevent infinite cycling.`
    - Fall through to Step 5.10 terminal write + Step 6 (STALLED is a clean exit, not a failure; the state file records the reason via the log line).
- If `NEW_SET_SIZE < PREV` (set did decrease): reset `**Loop no-progress count:**` to `0`.

**(d) MAX_LOOPS ceiling (opt-in):**
If `**Max loops:**` is an integer `N` (not `unlimited`) and `**Loop count:** + 1 >= N`:
- Log: `MAX_LOOPS: outer loop ceiling reached (count=$LOOP_COUNT, max=$N). Exiting.`
- Fall through to Step 5.10 terminal write + Step 6.

**(e) Re-enter loop:**
None of the three exits fired. Proceed:
1. Write `docs/features-renewed.md` using the renew-set collected in step (a) (same format as Step 1.6 step 5).
2. Update `docs/pipeline-state.md`:
   - `**Prev renew set:**` ← `NEW_SET_SIZE`
   - `**Loop count:**` ← current value + 1
   - `**Loop no-progress count:**` ← already set in step (c) (reset to `0` if set decreased, unchanged if no previous trip)
3. Reset per-feature state: clear `**Step:**` back to `analyze`, clear `**Review cycles:**` to `0`, clear `**Replan count:**` to `0`, clear `**Path D attempted:**` to `false`. (Other fields such as `**Phase Mode:**`, `**Review style:**`, `**Feature:**`, and `**Conv guard logged:**` are re-derived / re-initialized at Step 5.1 feature-init for each feature in the renewed list, so no explicit reset is needed here.)
4. Log: `OUTER_LOOP: re-entering Step 5.1 (loop count now $LOOP_COUNT; renew-set size $NEW_SET_SIZE). Phase Mode stays subagent.`
5. **Goto Step 5.1** — this is an in-process step-machine re-entry, NOT a `/pipeline` self-invocation and NOT a subprocess spawn. Phase Mode remains `subagent` for all features in the new sweep.

**Invariants:**
- STALLED guard is the mandatory terminator; `--max-loops` is purely optional belt-and-suspenders.
- CLEAN and STALLED jointly guarantee finiteness: a renew-set that keeps strictly decreasing (including a sawtooth like `5,4,4,3,3,2,…` where each decrement resets the no-progress counter) is bounded below by `0` and so reaches the empty set → **CLEAN**; a set that stops strictly decreasing (constant or oscillating at the same size) trips the no-progress counter → **STALLED**. No infinite run is possible even without `--max-loops`.
- Renew-set contents are NOT leaked into notification payloads (200-char text cap on `**text**` field applies).
- Phase Mode stays `subagent` across all loop iterations.
- The manual `--renew` flag's meaning is unchanged — this step reuses its collection logic, it does not redefine it.

---

### Step 6: Final Summary

After all features are processed:

```
---

Pipeline complete.

  Features: [N total]
  Succeeded: [list with PR URLs]
  Failed: [list with reasons]

  Feature log: [feature file path]

---
```

**Cross-feature intel summary:**
1. If `docs/pipeline-intel.json` exists:
   a. Read and count entries where `consumed_by` is still null
   b. If unmatched entries exist, append to the summary output:
      ```
      Cross-feature intel: [N] unmatched entries (manual review recommended)
        [for each: from_feature → target_feature: note (first 80 chars)]
      ```
   c. If all entries were consumed: append "Cross-feature intel: all [N] entries consumed"
2. If no intel file exists: omit this section from the summary

---

### Notifications

When `/pipeline` encounters a halt-class state (budget breach, error, end-of-feature, permission prompt), it surfaces a push notification via native Claude Code surfaces. There is NO custom notification config file, queue, or rate limiter — Channels' built-in mechanics are authoritative. The canonical helper at `claude/hooks/notify-emit.sh` is the single emit point.

**Hook event mapping:**

| Hook event | Trigger context | Notify event_type | Surface |
|------------|-----------------|-------------------|---------|
| `Stop` | End-of-feature (Claude finishes responding) | `feature-done` | `PushNotification` (interactive) OR `terminalSequence` (fallback) |
| `PermissionRequest` | Permission prompt (Bash/Edit/AskUserQuestion) | `question` | `terminalSequence` (OSC 777) |
| `Notification` | Budget breach / error / dropped-run watcher | `error` / `budget-breach` / `dropped` | `terminalSequence` (OSC 777) |
| `PreCompact` (wired as `PostCompact` matcher in `~/.claude/settings.json`) | Context-fill (manual or auto) | `compact` | `terminalSequence` |

The Step 5.0 beacon helper's notify-class tags (`feature-failed`, `path-b-pre`, `path-c-pre`, `feature-done`) route via the beacon-mode helper invocation to `PushNotification` (interactive) or the `Notification`-hook `terminalSequence` (fallback). The non-notify beacon tags (`phase-pre`, `phase-done`, `feature-start`, `docs-pre`, `docs-done`) do not emit notifications.

**PushNotification gating:** the `PushNotification` tool (Claude Code 2.1.110+) requires an interactive session with Remote Control + "Push when Claude decides" enabled in the Claude Code mobile app preferences. When unavailable (settings disabled, or non-interactive session), the fallback chain takes over.

**Fallback chain:** `PushNotification` (interactive + Remote Control) → `Notification`-hook `terminalSequence` (terminal-attached, OSC 777 supported) → no-op (headless session or terminal without OSC 777 support).

**Opt-out:**
- Set `channelsEnabled: false` in `~/.claude/settings.json` to disable inbound Channels delivery (Claude Code 2.1.121+).
- Set `PIPELINE_NO_NOTIFICATIONS=1` in the environment per-run to short-circuit the helper for that run (no emit at all, regardless of session interactivity).

**Payload schema:** 6 fields — `feature_index`, `step`, `event_type`, `text` (≤ 200 chars, truncated with ellipsis), `action_link` (deep-link OR signal-file path; may be empty), `feature_name`. Charter / analysis / plan / review file contents MUST NOT leak into the payload — the 200-char `text` cap is hard. Full schema documented in `claude/skills/pipeline/reference.md § Notification payload schema`.

---

### Important Notes

1. **No interactive prompts.** The pipeline never asks the user for input. All decisions are mechanical based on review outcomes and loop limits.
2. **Versioning convention.** All analysis/plan/prompts files follow the convention from `~/.claude/rules/workflow.md` § Versioning Convention.
3. **Never stage workflow files.** Follow the "Never stage" canonical list from `~/.claude/rules/workflow.md` § Plan & Progress when committing.
4. **No AI attribution.** PR titles, bodies, and commit messages follow the commit hygiene rules from `~/.claude/rules/agents-worktrees.md` § Commit Message Hygiene.
5. **Base branch detection.** Use the standard snippet from `~/.claude/rules/workflow.md` § Base Branch Detection wherever the base branch is needed.
6. **Feature file is the log.** All run results are appended to the feature file — no separate log files.
7. **Context management.** Phase-as-Subagent architecture is the default — each phase runs in a fresh `Agent` context for true isolation, replacing the prior conditional `/compact` mitigation. Path N nit-attack sub-paths are the only inline-context exception, and they are bounded (max 2 cycles, Edit-tool only). The conditional `/compact` calls in Step 5.2 / 5.3 / 5.5 / 5.6 remain documented but are unreachable on a `subagent`-mode dispatch — they apply only to legacy `inline`-mode resumes.
8. **Maximum review cycles per feature.** Path B allows 5 review cycles. Path C allows 1 re-plan, which then re-enters Path B (5 more cycles). Path D adds 1 more salvage attempt after Path C exhausts (fresh-context `general-purpose` dispatch — see `reference.md` § "Path D — Fresh-context Salvage"). Theoretical maximum: 12 review iterations per feature. Retries for BLOCKED outcomes add up to 3 more attempts (transient failures only).

---

## Project Startup

See reference.md § Project Startup — commit-msg hook template

---

## Run-End Summary

See reference.md § Run-End Summary
