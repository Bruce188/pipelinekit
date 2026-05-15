# /pipeline

In-process feature pipeline. Single entry point. No subprocess driver (`orchestrate.sh` was removed for the portable build).

## Invocation

```
/pipeline                  # uses docs/features.md in current project
/pipeline path/to/features.md
/pipeline --plan           # ingest most recent ~/.claude/plans/*.md
/pipeline --from "free text seed for feature generation"
/pipeline --renew          # rebuild from deferred + failed features
/pipeline --max-usd 5      # halt at phase boundary if cumulative cost > $5
/pipeline --max-turns 100  # halt at phase boundary if cumulative sub-agent turns > 100
/pipeline --no-parallel    # force sequential implementation
```

## Feature file (`docs/features.md`)

```markdown
# Features

## feat/user-auth
**Description:** Add session-based auth with email + password.
**Constraints:** Use bcrypt, do not break existing /api/me endpoint.
**Acceptance Criteria:**
1. POST /api/login returns 200 + session cookie on valid creds
2. POST /api/login returns 401 on invalid creds
3. Existing /api/me continues to work

## docs/onboarding-guide
**Description:** Write `documentation/onboarding.md` for new contributors.
**Constraints:** Keep under 400 words.

## chore/dep-bump
**Description:** Bump express 4.18 → 4.19.
```

## TDD routing (dev vs non-dev)

The pipeline derives a routing class from the feature's H2 prefix:

| Prefix | Class | Implementation phase |
|--------|-------|----------------------|
| `feat`, `fix`, `refactor`, `perf`, `test` | **dev** | tdd-test-writer → tdd-implementer (paired, context-isolated) |
| `docs`, `chore`, `style`, `build`, `ci`, `content`, `ops`, `research` | **non-dev** | Standard `implement-plan` Agent dispatch |

Override the auto-derivation with a per-feature line:

```markdown
## chore/critical-migration
**Type:** dev
**Description:** Behavior-critical migration; want TDD even though the prefix is chore.
```

Valid override values: `dev`, `non-dev`.

## Phases

Per feature, the pipeline runs:

1. **Analyze** — context-gather, key-file identification, MCP doc lookups
2. **Plan** — task breakdown with parallel-execution annotations
3. **Branch** — `/new-branch <feature-name>`
4. **Implement** — `dev` → TDD pair; `non-dev` → standard implement
5. **Review** — multi-agent: code-reviewer, security-auditor, test-engineer, performance-tuner, spec-tracer
6. **Path A / B / C** — A: merge clean; B: fix findings (≤5 cycles); C: replan

State persists in `docs/pipeline-state.md` per run. Resume by re-invoking `/pipeline`.

## What was removed in the portable build

- `orchestrate.sh` (out-of-process driver). The in-process Skill is the only entry point.
- `claude -p` subprocess invocations. Phase dispatch is always via the `Agent` tool with subagent isolation.

If you need maximum context isolation for long unattended runs, re-introduce a subprocess driver in your fork — the upstream design is documented in `rules/workflow.md` § Pipeline Entry Points but intentionally not shipped.
