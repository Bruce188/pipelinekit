# /review cost profile

`/review` dispatches up to 6 parallel agents per invocation (medium and large tiers).

### Planning the budget

<div data-snippet="cost-calculator"></div>

### Watching live spend

<div data-snippet="cost-budget-meter" data-spent-usd="3.40" data-max-usd="10" data-spent-turns="220" data-max-turns="500"></div>

## Per-agent default model and relative cost

| Agent             | Default model | Relative cost |
|-------------------|---------------|---------------|
| code-reviewer     | opus          | 1.0×          |
| security-auditor  | opus          | 1.0×          |
| symbol-verifier | opus          | 1.0×          |
| test-engineer     | sonnet        | 0.25×         |
| performance-tuner | sonnet        | 0.25×         |
| spec-tracer       | haiku         | 0.05×         |

Sum: ~3.55× a single opus call. Adding symbol-verifier (Agent 6) moved this from ~2.55× to ~3.55× — a ~20% increase over the prior 5-agent lineup. Paid on every medium- or large-tier `/review`; no opt-in flag.

## Small-tier exclusion

Small-tier diffs (< 500 lines, per `SMALL_DIFF_THRESHOLD` in `claude/skills/review/SKILL.md`) still spawn only 2 agents: `code-reviewer` + `spec-tracer`. symbol-verifier is deliberately excluded from small tier — the cost vs. detection trade-off is unfavourable for sub-500-line diffs. A small diff that imports a hallucinated symbol receives only code-reviewer + spec-tracer review; this is a known trade-off. Future-iteration mitigations: drop threshold to 250 lines, or run karpathy in symbol-only degraded mode on small tier.

## REVIEW.md override

A project-root `REVIEW.md` (or `.claude/REVIEW.md`) with `review-model: sonnet` drops all six agents to sonnet, cutting cost ~70% at the price of detection rate on subtle bugs. See `claude/skills/review/SKILL.md` Step 3a. Valid values: `sonnet`, `opus`, `haiku`. Applies uniformly to all six reviewers.

## Pipeline cost implication

`/pipeline` Step 5.7 Path B re-runs `/review` per fix iteration. A 5-cycle Path B convergence on a medium-tier diff costs ~17.75× a single opus call (5 × 3.55×) before Path C escalation fires. Budget `--max-usd` accordingly.
