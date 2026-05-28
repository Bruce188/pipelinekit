---
description: Charter Discovery question bank and schema for Step 0 of /pipeline.
---

# Charter Question Bank

Used by `/pipeline` Step 0 (Charter Discovery) to guide the user through producing `docs/charter.md`.

## Charter File Schema

Required frontmatter:
```yaml
---
version: 1
created: YYYY-MM-DD
status: draft | ratified
---
```

Required sections (19 topics in order):
1. `## Goal`
2. `## Users`
3. `## Problem`
4. `## Success`
5. `## Non-Goals`
6. `## Constraints`
7. `## MVP Boundary`
7.5. `## Slice Strategy`
8. `## Prior Art`
9. `## Open Questions`
10. `## Deployment target`
11. `## Review style`
12. (Optional) AI Layer subsections — written under a new `## AI Layer` H2 when answered:
    - Topic 12: AI Champion
    - Topic 13: LSP / symbol search MCP
    - Topic 14: Codebase Map (root CLAUDE.md)

Optional section (additive — charters without this section continue to validate):
- `## Stakeholders` (optional, populated only when multi-party scope is signaled during Step 0; captures decision-makers, blockers, reviewers; backward-compat: charters without this section continue to validate)
- `## MCP Routing` (optional, per-project; declares which MCP servers the pipeline should surface into phase subagents and what to use each for. Pure charter-driven — absent section means NO MCP guidance is injected. Resolved at dispatch time by `claude/lib/pipeline/mcp_guidance.py`, intersected with the live `claude mcp list` connected set. One MCP per bullet: `- <server>: <purpose text> | phases: <comma-list>`. The `| phases:` clause is optional; absent (or literal `all`) applies the entry to every phase. Valid phase tokens: `analyze`, `plan`, `implement`, `review`, `docs`, `uat`. Backward-compat: charters without this section continue to validate.)

Required table (appended after the 9 sections):
```markdown
## Decision Log
| Date | Question | Decision | Reason |
|------|----------|----------|--------|
```

## Convergence Check Prompt

After each topic round, display:

```
Charter so far covers: [list of completed topics]
Remaining: [list of pending topics]

Ready to ship? Choose:
  A) Ship the charter now — write docs/charter.md with what we have
  B) Continue to next topic
  C) Go deeper on the current topic (follow-up questions)
  D) Edit manually — write current draft and pause (resume via /pipeline --charter docs/charter.md)
```

The 19 topics enumerated by the convergence check (in order):

- Topic 1 — Goal
- Topic 2 — Users
- Topic 3 — Problem
- Topic 4 — Success
- Topic 5 — Non-Goals
- Topic 6 — Constraints
- Topic 7 — MVP Boundary
- Topic 7.5 — Slice Strategy
- Topic 8 — Prior Art
- Topic 9 — Open Questions
- Topic 10 — Deployment target
- Topic 11 — Review style
- Topic 12 — AI Champion
- Topic 13 — LSP / symbol search MCP
- Topic 14 — Codebase Map confirmation
- Topic 15 — Production-readiness probe depth
- Topic 16 — Risk class
- Topic 17 — Effort budget
- Topic 18 — Failure tolerance
- Topic 19 — Charter applicability

The user must see this choice after every topic, including the last. "Ship the charter now" is always available.

## Escape-Hatch Convention

Every round's choice list MUST end with a "ship the charter now" option. The label may vary (e.g., "Ship the charter now", "I've answered enough — write the charter", "Done — ship it"), but the intent must be unambiguous: the user can exit charter discovery at any point and accept whatever has been gathered so far.

## Question Bank

### Topic 1: Goal

> "What is the single thing this feature/project must accomplish? Complete the sentence: 'When this ships, users will be able to...'"

Options:
- A) `[User provides free-form answer]`
- B) `Help me draft it — I'll describe the problem`
- C) `Ship the charter now with what we have`

Follow-up (if answer is vague):
> "Is there a measurable outcome? What does 'done' look like to you?"

---

### Topic 2: Users

> "Who are the primary users? Describe their role, expertise level, and how frequently they interact with this."

Options:
- A) `[User provides free-form answer]`
- B) `Solo developer / small team`
- C) `Large enterprise team`
- D) `Ship the charter now`

---

### Stakeholders (conditional probe)

**Trigger criteria:** After each topic answer, scan the user's response for any of these tokens: `teammate`, `customer segment`, `upstream`, `downstream`, `external service`. On first match, fire the conditional prompt below; a **once-per-run latch** ensures it fires at most once per Step 0 run. No new round is added to the happy-path topic sequence — Stakeholders is NOT a numbered topic.

**Counts toward `--max-questions`:** The conditional Stakeholders prompt counts toward the `--max-questions` cap, so `--max-questions 0` (effectively `--no-charter`) skips it.

**Conditional prompt text** (mirror Topic 2 "Users" shape):
> "Who are the decision-makers, blockers, or reviewers for this work? (one short line per stakeholder; skip if none apply)"

Options:
- A) `[User provides free-form answer]`
- B) `Skip — no stakeholders to capture`
- C) `Ship the charter now`

---

### Topic 3: Problem

> "What pain does this solve today? What's the workaround users currently use, and what does that cost them?"

Options:
- A) `[User provides free-form answer]`
- B) `There is no workaround — they're blocked`
- C) `They use a manual process that is error-prone`
- D) `Ship the charter now`

---

### Topic 4: Success

> "How will you know this succeeded? Name 2–3 measurable outcomes (user behavior, metric, or observable system state)."

Options:
- A) `[User provides free-form answer]`
- B) `Help me define success criteria`
- C) `Ship the charter now`

---

### Topic 5: Non-Goals

> "What is explicitly out of scope for this iteration? Naming non-goals now prevents scope creep during planning."

Options:
- A) `[User provides free-form answer]`
- B) `Nothing is explicitly out of scope yet`
- C) `Ship the charter now`

---

### Topic 6: Constraints

> "What constraints must the implementation respect? (technology choices, performance requirements, integration limits, deployment environment, etc.)"

Options:
- A) `[User provides free-form answer]`
- B) `No hard constraints beyond the existing stack`
- C) `Ship the charter now`

---

### Topic 7: MVP Boundary

> "What is the minimum set of things that must ship in v1 (In), and what can wait (Out)?"

Format the answer as two lists:
```
**In:** [what ships in v1]
**Out (deferred):** [what waits]
```

Options:
- A) `[User provides free-form answer]`
- B) `Help me distinguish In vs Out`
- C) `Ship the charter now`

---

### Topic 7.5: Slice Strategy

> "How should implementation work be sliced? (a) **Vertical** — each task touches all layers thinly (database + API + UI), tracer-bullet style, fast end-to-end feedback. (b) **Horizontal** — phase 1 is all database, phase 2 is all API, etc. Requires explicit justification. (c) **Flexible** — planner picks per-task based on analysis."

The answer feeds the Decomposition Compliance gate in `/create-plan` Step 4.6:
- `vertical` → every plan task must include a `**Touches:**` line listing ≥2 architectural layers.
- `horizontal` → plan Overview must include a justification paragraph (Pocock's "reprimand" rule).
- `flexible` (default) → gate auto-PASSes the slice-strategy axis; planner picks per task.

Default when the user skips this topic: `flexible`.

Options:
- A) `vertical`
- B) `horizontal`
- C) `flexible` (default)
- D) `[User provides free-form answer]`
- E) `Ship the charter now`

---

### Topic 8: Prior Art

> "Is there existing work this builds on — internal tools, prior iterations, competitor implementations — that the plan should reference?"

Options:
- A) `[User provides free-form answer]`
- B) `No relevant prior art`
- C) `Ship the charter now`

---

### Topic 9: Open Questions

> "What is still unresolved? List the decisions you expect to make during implementation or that depend on user feedback after shipping."

Options:
- A) `[User provides free-form answer]`
- B) `No open questions — the charter is clear`
- C) `Ship the charter now`

---

### Topic 10: Deployment target

**Probe:** Which deployment target will this project ship to?

**Follow-up 1:** Is there an existing provider config file in the repo (`vercel.json`, `railway.toml`, `render.yaml`, `.do/app.yaml`)? If so, the pipeline can pre-fill this topic from the detected provider and ask only for confirmation.

**Follow-up 2:** If you don't deploy from this repo (library / pure backend / data pipeline), choose `none` — the pipeline will skip the deployment phase entirely.

**Classification note:** When the review classifier encounters a
finding that names a provider OTHER than this slug, it tags the
finding `scope: out` (advisory deferral). A value of `none` skips
this classification entirely. See
`claude/skills/review/SKILL.md` § Step 7.8 "Deployment-target
mismatch (Topic 10)" for the provider-token lookup table.

**Example values:** `vercel`, `railway`, `render`, `digitalocean`, `none`.

Options:
- A) `[User provides free-form answer]`
- B) `vercel`
- C) `railway`
- D) `render`
- E) `digitalocean`
- F) `none` — no deployment from this repo
- G) `Ship the charter now`

### follow-up: free-form provider

**Follow-up: free-form provider** — If the user picks option A and supplies
a provider slug NOT in the {`vercel`, `railway`, `render`, `digitalocean`,
`none`} set (e.g. `fly.io`, `netlify`, `self-hosted`, `kubernetes`):

- Record the free-form value verbatim in the charter under `## Deployment target`.
- Skip the deploy classifier described above (the `scope: out` provider-mismatch
  tagger at `claude/skills/review/SKILL.md § Step 7.8`) — without a recognized
  provider slug, the classifier has no lookup-table entry and would emit no-ops
  anyway. Logging `DEPLOY_CLASSIFIER_SKIPPED_FREE_FORM: <slug>` makes the
  bypass explicit.
- The deployment-engineer sub-agent (vercel / railway / render / digitalocean)
  is NOT dispatched. The user is on their own for deploy operations.

---

### Topic 11: Review style

**Probe:** When the pipeline reaches the review phase, should it always use Agent Teams (richer cross-agent communication, higher token cost), never use teams (faster, lighter), or decide per-feature based on diff size and feature class?

**Follow-up:** Default is `orchestrator decides` — the heuristic picks `--teams` when the diff is large (>500 lines or >8 files) or the feature class is `dev`. Choose `always teams` for richer reviews on every feature regardless of size. Choose `never teams` to suppress the heuristic entirely.

**Example values:** `always teams`, `never teams`, `orchestrator decides`.

Options:
- A) `[User provides free-form answer]`
- B) `always teams`
- C) `never teams`
- D) `orchestrator decides` (default)
- E) `Ship the charter now`

---

### Topic 12: AI Champion

**Probe:** Does the project have a designated AI Champion (per `documentation/governance.html`)? An AI Champion is the named owner for AI-workflow decisions on this codebase.

**Follow-up:** If yes, capture the champion's name and tenure under `## AI Layer` in the charter.

**Invocation:** Pipeline issues an `AskUserQuestion` with the four options above; the answer is recorded under `## AI Layer` in the charter.

Options:
- A) `yes` (follow-up: name + tenure)
- B) `no`
- C) `not sure`
- D) `Ship the charter now`

---

### Topic 13: LSP / symbol search MCP

**Probe:** Which symbol-navigation MCP do you want wired into the harness for cross-file refs and symbol graphs?

**Follow-up:** `serena` is the recommended LSP-based option; `claude-context` provides semantic RAG over the codebase via Milvus. Pick `none / skip` if neither is needed.

**Invocation:** Pipeline issues an `AskUserQuestion` with the five options above; the answer is recorded under `## AI Layer` in the charter.

**MCP Routing seed:** When the answer names a real server (`serena` or `claude-context`, not `none`/`not sure`), ALSO append a corresponding bullet to the optional `## MCP Routing` section so the pipeline surfaces it into phase subagents — e.g. `- serena: symbol navigation and cross-file refs | phases: analyze, implement`. This is the only topic that auto-seeds `## MCP Routing`; the user adds further servers (`context7`, `agentmemory`, `local-rag`, project-specific MCPs) by editing the section directly (or via the "edit manually" escape). `## MCP Routing` stays absent — and no MCP guidance is injected — until at least one server is declared.

Options:
- A) `serena (recommended)`
- B) `claude-context (semantic RAG)`
- C) `none / skip`
- D) `not sure`
- E) `Ship the charter now`

---

### Topic 14: Codebase Map confirmation

**Probe:** Confirm the root `CLAUDE.md` Codebase Map is up to date for this repo.

**Follow-up:** This is a pure `AskUserQuestion` probe — no `grep` pre-fill (per feature constraint 4). If the project does not yet ship a root `CLAUDE.md`, pick `n/a`.

**Invocation:** Pipeline issues an `AskUserQuestion` with the four options above; the answer is recorded under `## AI Layer` in the charter.

Options:
- A) `confirmed`
- B) `needs update`
- C) `n/a (project does not use root CLAUDE.md yet)`
- D) `Ship the charter now`

---

### Topic 15: Production-readiness probe depth

**Probe:** How deep should the production-probe agent verify each merged feature?

**Follow-up:** Determines which probes 1-7 the production-probe agent runs at Path A step 0.5. Light = boot + log only. Standard = boot + golden + failure + console + log. Paranoid = all 10 probes (1-7 + log + honesty contract + anti-pattern refusal check).

**Invocation:** Pipeline issues an `AskUserQuestion` with the four options below; the answer is recorded under `## Production-readiness probe depth` in the charter.

Options:
- A) `light — probes 1+8 only (boot + log evidence). Fastest. Good for read-only docs/config repos.`
- B) `standard — probes 1, 2, 3, 4, 8 (boot + golden path + failure path + console/network + log). Default.`
- C) `paranoid — all 10 probes (1-7 + 8 log + 9 honesty + 10 anti-pattern refusal check). Slowest. Good for money-loop / live-user-facing surfaces.`
- D) `Ship the charter now`

---

### Topic 16: Risk class

**Probe:** What is the risk profile of this work? Higher risk routes
through stricter review and (when wired) auto-dispatches the
security-auditor agent.

**Follow-up:** `security-sensitive` answer is intended to route downstream
review through the `security-auditor` agent automatically. Wiring lands in
a follow-up feature; for now the answer is recorded in the charter as a
documented expectation.

**Example values:** `routine`, `security-sensitive`, `data-migration`,
`breaking-change`.

Options:
- A) `routine`
- B) `security-sensitive`
- C) `data-migration`
- D) `breaking-change`
- E) `[User provides free-form answer]`
- F) `Ship the charter now`

---

### Topic 17: Effort budget

**Probe:** What is the expected scope of file changes for this work?
Drives plan task granularity and review effort scaling.

**Follow-up:** Used by `/create-plan` to right-size task decomposition.
`XL` features should be split into sub-features at the feature-file level
before reaching `/pipeline`.

**Example values:** `S (1 file)`, `M (≤5 files)`, `L (≤20 files)`, `XL`.

Options:
- A) `S (1 file)`
- B) `M (≤5 files)`
- C) `L (≤20 files)`
- D) `XL`
- E) `[User provides free-form answer]`
- F) `Ship the charter now`

---

### Topic 18: Failure tolerance

**Probe:** When a phase fails (review blockers, test failures, budget
breach), how should the pipeline respond?

**Follow-up:** `strict` halts on first hard failure. `lenient` continues
past non-blocking findings and logs a deferred-item entry.
`retry-once-then-skip` retries the failing phase once, then defers the
feature and continues with the next feature in the queue.

**Example values:** `strict`, `lenient`, `retry-once-then-skip`.

Options:
- A) `strict`
- B) `lenient`
- C) `retry-once-then-skip`
- D) `[User provides free-form answer]`
- E) `Ship the charter now`

---

### Topic 19: Charter applicability

**Probe:** Should this charter apply to every feature in the queue, only
to features above a size threshold, or be re-derived per feature?

**Follow-up:** `apply to all` reuses the same charter for every feature
(default). `skip for <5 LOC diff` short-circuits charter loading for
trivial features. `charter-per-feature` re-runs Step 0 at the start of
every feature loop (expensive — use only when features genuinely diverge
in goal).

**Example values:** `apply to all`, `skip for <5 LOC diff`,
`charter-per-feature`.

Options:
- A) `apply to all` (default)
- B) `skip for <5 LOC diff`
- C) `charter-per-feature`
- D) `[User provides free-form answer]`
- E) `Ship the charter now`

---

## Charter File Template

After all topics are gathered (or user chooses "ship now"), write `docs/charter.md` using this template:

```markdown
---
version: 1
created: YYYY-MM-DD
status: draft
---

# Charter — [Goal one-liner]

> [One-sentence context / framing sentence]

## Goal
[Goal content]

## Users
[Users content]

<!-- ## Stakeholders — OPTIONAL, populated only when Step 0 detects
     multi-party scope (mentions of teammate / customer segment / upstream /
     downstream system). Omit the entire H2 if no stakeholders apply. -->

## Problem
[Problem content]

## Success
[Success content]

## Non-Goals
[Non-Goals content]

## Constraints
[Constraints content]

## MVP Boundary
[MVP Boundary content]

## Slice Strategy
[Either `vertical`, `horizontal`, or `flexible` (default).]

## Prior Art
[Prior Art content]

## Open Questions
[Open Questions content]

## Deployment target
[Provider slug, e.g. `vercel`, `railway`, `render`, `digitalocean`, or `none`.]

## Review style
[Either `always teams`, `never teams`, or `orchestrator decides` (default).]

## Production-readiness probe depth
[Production-readiness probe depth content]

## Risk class
[Either `routine`, `security-sensitive`, `data-migration`, or `breaking-change`.]

## Effort budget
[Either `S (1 file)`, `M (≤5 files)`, `L (≤20 files)`, or `XL`.]

## Failure tolerance
[Either `strict`, `lenient`, or `retry-once-then-skip`.]

## Charter applicability
[Either `apply to all` (default), `skip for <5 LOC diff`, or `charter-per-feature`.]

## AI Layer
- **AI Champion:** [name + tenure, or `none` / `not sure`]
- **LSP / symbol-search MCP:** [`serena` | `claude-context` | `none` | `not sure`]
- **Self-reflection (Stop hook):** [`enabled` | `disabled` | `not sure`]
- **Codebase Map (root CLAUDE.md):** [`confirmed` | `needs update` | `n/a`]

<!-- OPTIONAL additive section — omit entirely when no MCP is wired. Resolved into {{MCP_GUIDANCE}} per phase. Format: `- <server>: <purpose> | phases: <comma-list>`; omit the `| phases:` clause (or use `all`) to apply to every phase.
## MCP Routing
- context7: resolve-library-id then query-docs for framework/library API verification | phases: analyze, plan, implement, review
- serena: symbol navigation and cross-file refs | phases: analyze, implement
- agentmemory: memory_recall for prior context at phase start; memory_save for durable findings | phases: all
- local-rag: query_documents for niche/ingested docs | phases: analyze, implement
-->

## Decision Log
| Date | Question | Decision | Reason |
|------|----------|----------|--------|
```

Set `status: ratified` once the user confirms the charter is final. Leave as `draft` when writing mid-discovery or on "edit manually" escape.
