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

## Charter Mode

Charter Mode is the default-on front-loaded alignment phase added in Step 0 of `/pipeline`. Before the pipeline processes features, it asks the user a structured set of questions to produce `docs/charter.md`. Downstream phases (`/analyze`, `/create-plan`, `/implement-plan`, `/review`, `/ppr`) read this charter to scope their work.

### When it runs

Step 0 runs by default on every interactive `/pipeline` invocation, unless one of the following opt-out conditions is met (checked in order):

1. `--no-charter` flag is present → skip entirely (legacy autonomous flow restored).
2. `--charter <path>` flag is present → adopt the existing charter at `<path>`, skip discovery.
3. `--max-questions 0` → treated as `--no-charter` (alias).
4. `docs/charter.md` exists AND `progress.md` `**Charter:**` pointer is valid → skip (already chartered for this run).

### Opt-out flags

| Flag | Effect |
|------|--------|
| `--no-charter` | Skip Step 0; restore legacy autonomous behavior |
| `--charter <path>` | Adopt an existing charter file; skip discovery loop |
| `--max-questions <N>` | Cap total `AskUserQuestion` calls at `N`; `0` = `--no-charter` alias |

`--no-charter` and `--charter` are mutually exclusive. Using both together stops the pipeline with: `ERROR: --no-charter and --charter are mutually exclusive.`

Providing `--charter <path>` with a missing file stops the pipeline with: `ERROR: --charter path not found: <path>`

### Subprocess-mode constraint

**`AskUserQuestion` is interactive-session-only.** Charter Discovery cannot run inside a subprocess driver (`claude -p` or equivalent). If you re-introduce a subprocess driver in a fork:

- The driver MUST check for an existing charter before launching any phase.
- If `docs/charter.md` is absent AND neither `--no-charter` nor `--charter <path>` is set, the driver MUST exit non-zero with:

  ```
  ERROR: subprocess mode cannot run Charter Discovery (AskUserQuestion is interactive-only). Run /pipeline interactively first, or pass --no-charter.
  ```

### Charter file shape

`docs/charter.md` contains 9 required sections (in order):

1. **Goal** — what the feature/iteration achieves
2. **Users** — who it serves
3. **Problem** — the pain being solved
4. **Success** — measurable outcomes
5. **Non-Goals** — explicit exclusions
6. **Constraints** — hard technical or process limits
7. **MVP Boundary** — what is "In" vs "Out" for this iteration
8. **Prior Art** — existing work this relates to or supersedes
9. **Open Questions** — unresolved items for future decisions

Plus frontmatter (`version`, `created`, `status`) and an optional **Decision Log** table.

Versioning follows the same convention as `plan.md` and `analysis.md` — see `claude/rules/workflow.md` § Versioning Convention.

### How downstream phases consume the charter

| Phase | Charter usage |
|-------|--------------|
| `/analyze` | Scopes investigation to MVP Boundary; flags Non-Goal areas without deep traversal |
| `/create-plan` | Gates tasks against Non-Goals and MVP Boundary; defers out-of-scope items |
| `/implement-plan` | Prepends charter Goal + Constraints to each task subagent's context |
| `/review` | Classifies findings as in-scope or out-of-scope per charter; defers out-of-scope findings |
| `/ppr` | Derives PR `## Summary` opening line from charter Goal |

## What was removed in the portable build

- `orchestrate.sh` (out-of-process driver). The in-process Skill is the only entry point.
- `claude -p` subprocess invocations. Phase dispatch is always via the `Agent` tool with subagent isolation.

If you need maximum context isolation for long unattended runs, re-introduce a subprocess driver in your fork — the upstream design is documented in `rules/workflow.md` § Pipeline Entry Points but intentionally not shipped.
