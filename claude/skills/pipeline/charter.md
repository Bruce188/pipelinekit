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

Required sections (10 topics in order):
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

Optional section (additive — charters without this section continue to validate):
- `## Stakeholders` (optional, populated only when multi-party scope is signaled during Step 0; captures decision-makers, blockers, reviewers; backward-compat: charters without this section continue to validate)

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

The 10 topics enumerated by the convergence check (in order):

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

## Decision Log
| Date | Question | Decision | Reason |
|------|----------|----------|--------|
```

Set `status: ratified` once the user confirms the charter is final. Leave as `draft` when writing mid-discovery or on "edit manually" escape.
