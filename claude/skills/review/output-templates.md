# Review Skill Output Templates

"What's Next" output templates for each review outcome.
Referenced from `SKILL.md` Step 10.

---

## Sanity gate FAILED

```
---

BLOCKED -- tests failing.

[error output]

Fix the failing tests, then run /review again.

---
```

## Secrets detected

```
---

BLOCKED -- secrets detected in diff.

[findings]

Remove the exposed secrets, then run /review again.

---
```

## Review BLOCKED (all agents failed)

```
---

BLOCKED -- all review agents failed or timed out.

Re-run /review. If this persists, check agent availability.

---
```

## No findings (or all nits auto-fixed)

```
---

Review passed.
  Sanity gate: [passed | skipped (no test framework detected) | inherited from implement (<sha> at <time>)]
  Review tier: [small | medium | large] ([N] agents[, teams mode])
  Agents: [list of spawned agents for this tier]
  Findings: 0 [or "N nits auto-fixed"]
  [If cross-feature intel captured: "Cross-feature intel: [N] notes captured"]
  [If auto-scope active: "NOTE: Re-review scoped to [N] files from fixed tasks."]
  [If large diff: "Note: diff was [N] lines — consider --scope for targeted reviews"]
  [If adjacent > 0: "Adjacent advisory: [N] finding(s) — near-charter, surfaced for awareness."]

Next: Run /compact, then /ppr to push and open the PR.

---
```

## Findings exist, no scope change

```
---

Review complete.
  Sanity gate: [passed | skipped (no test framework detected) | inherited from implement (<sha> at <time>)]
  Review tier: [small | medium | large] ([N] agents[, teams mode])
  [If agents incomplete: "WARNING: [N] agent(s) incomplete ([names])"]
  [If auto-scope active: "NOTE: Re-review scoped to [N] files from fixed tasks."]
  Findings: [N blocking, M non-blocking, P nits] -> [review filename]
  [If cross-feature intel captured: "Cross-feature intel: [N] notes captured"]
  [If adjacent > 0: "Adjacent advisory: [N] finding(s) — near-charter, surfaced for awareness."]

Reopened tasks in progress.md:
  [list]

Next: Run /clear, then /implement-plan to address findings.
  After fixes: /clear -> /review again.

---
```

## Mixed findings (some fixable, some require scope change)

```
---

Review complete — mixed findings.
  Sanity gate: [passed | skipped (no test framework detected) | inherited from implement (<sha> at <time>)]
  Review tier: [small | medium | large] ([N] agents[, teams mode])
  [If agents incomplete: "WARNING: [N] agent(s) incomplete ([names])"]
  [If auto-scope active: "NOTE: Re-review scoped to [N] files from fixed tasks."]
  Findings: [N blocking, M non-blocking, P nits] -> [review filename]
  [If cross-feature intel captured: "Cross-feature intel: [N] notes captured"]
  [If adjacent > 0: "Adjacent advisory: [N] finding(s) — near-charter, surfaced for awareness."]

Fixable findings — reopened tasks in progress.md:
  [list]

Scope-change findings (noted in review file, not reopened):
  [list with brief descriptions]

Next: Run /clear, then /implement-plan to address fixable findings.
  After fixes: /clear -> /review again.
  Scope-change findings will need /create-plan in a future iteration.

---
```

## Findings require scope change

```
---

Review found issues beyond current scope.
  Sanity gate: [passed | skipped (no test framework detected) | inherited from implement (<sha> at <time>)]
  Review tier: [small | medium | large] ([N] agents[, teams mode])
  Findings require re-planning -- [brief summary].
  Findings saved -> [review filename]
  [If cross-feature intel captured: "Cross-feature intel: [N] notes captured"]

Next: Run /clear, then /create-plan to revise the plan with review findings as input.

---
```
