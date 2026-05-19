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

## Relationship to native /goal

`/pipeline` charter goals and the native `/goal` feature coexist independently — they serve different lifecycle scopes and have no integration today.

Charter goals (written to `docs/charter.md` during Step 0 and referenced in `docs/pipeline-state.md`) are **feature-bound**: they persist across session restarts, survive `/compact` and context resets, and are re-evaluated once per pipeline phase by the phase subagent. Native `/goal` conditions are **session-bound**: the model re-evaluates the goal predicate on every turn, and the goal is lost when the session ends.

| Use /pipeline charter goals when… | Use /goal when… |
| --- | --- |
| Work spans multiple phases or sessions (feature-bound, multi-phase lifecycle) | Completion can be checked in the current session without persistence (session-bound, ephemeral) |
| Goal state must survive resume — stored in `docs/charter.md` and `docs/pipeline-state.md` | Goal lives in-memory only — no on-disk artifact |
| Evaluation is structured per-phase with explicit Acceptance Criteria | Evaluation is a per-turn model self-check with no structured AC format |

F15 historically considered native `/goal` integration as a pipeline-level stop condition. The current integration surface is none — `/pipeline` charter goals and `/goal` coexist independently.

## Documentation Update Phase

After a feature's squash-merge passes the **Post-Merge Verification Gate**
(`claude/skills/pipeline/SKILL.md` § Post-Merge Verification Gate), the pipeline
runs a best-effort documentation update phase. The phase dispatches the
`docs-writer` subagent to read the merged diff and update files in `documentation/`
(the committed application-docs directory, distinct from `docs/` which is
workflow-only). The doc update lands as a separate `docs: <feature description>`
commit on the base branch — the merge commit stays clean.

**Execution order (Path A success):**
1. Squash-merge lands on `$BASE`.
2. Post-merge cleanup + `git pull origin "$BASE"` (Path A step 7).
3. **Post-Merge Verification Gate** runs — on failure, revert; on success, append `POSTMERGE_OK: <cmd>`.
4. **Documentation Update Phase** — dispatches `docs-writer` via Agent tool; emits beacon `docs-pre` before dispatch and `docs-done` on success.
5. **Step 5.9** emits `feature-done`.

**Opt-out:** Set `PIPELINE_SKIP_DOCS=1` to skip the docs phase. Default is "phase runs"
(mirrors `SKIP_POSTMERGE_VERIFY=1` semantics — opt-out, not opt-in). When skipped, the
Run Log gets `Docs: SKIPPED (PIPELINE_SKIP_DOCS=1)` and neither `docs-pre` nor
`docs-done` is emitted.

**Failure semantics (best-effort):** A docs-writer subagent failure does NOT downgrade
`feature-done` to `feature-failed`. The Run Log gets `Docs: SKIPPED (subagent error)`
and the feature still completes with terminal status `SUCCESS`. Docs are a tail step,
not load-bearing.

**Subprocess-mode constraint:** The out-of-process `orchestrate.sh` is not shipped in
pipelinekit (see § What was removed in the portable build). If `orchestrate.sh` is
ever introduced, it would need its own docs-phase parallel — record as a deferred
dependency.

## Worker Delegation

The implement phase of `/pipeline` dispatches each plan task to a worker. The default
worker is **ClaudeWorker** — the in-session Agent-tool worktree fan-out documented
in `claude/skills/implement-plan/SKILL.md` § Step 1.5. ClaudeWorker is always
available and requires no external runtime.

Plan task prompts MAY include an optional `worker:` header to request a different
worker class (for example, an external worker class for long-running parallel work).
When the header is absent or set to `worker: claude`, pipelinekit dispatches via
ClaudeWorker. Routing logic for non-default worker classes is **not wired in this
build** — see Phase 3 of the worker-delegation initiative (deferred).

### Worker classes

| Class    | Status                          | Dispatch mechanism                                |
|----------|---------------------------------|---------------------------------------------------|
| `claude` | default; always available       | In-session Agent tool + worktree isolation        |

Per-class implementation specs live in `claude/lib/worker-provider/<class>.md`.
The contract every worker class implements is documented in
`claude/lib/worker-provider/interface.md`. The per-task spec schema that every
worker reads from `.claude/tasks/<task-id>/spec.md` is documented in
`claude/lib/worker-provider/task-spec.md`.

### Opt-in format

Add a `worker:` line to a plan task prompt's header block:

```
### Task 1.1: Build the thing
> Model: sonnet | Effort: medium | Agent: none | worker: claude
```

In this build, the header is acknowledged but ignored — every task dispatches via
ClaudeWorker regardless. The header reservation lets plan authors begin annotating
plans today; routing arrives in a future iteration.

## Sandbox Provider

`/pipeline` runs each phase's command stream inside a sandbox provider chosen by
`claude/lib/sandbox/SandboxProvider.sh`. The provider selection ladder is:

1. `SANDBOX_PROVIDER=podman` | `docker` | `worktree-only` — explicit override.
2. `SANDBOX_PROVIDER=auto` (default) — **engine-when-present**: prefer `podman`,
   else `docker`, else fall back to `worktree-only`. The fallback keeps the
   pipeline runnable on hosts without a container engine; on engines-available
   hosts the container provider is selected automatically.
3. `PIPELINE_NO_SANDBOX=1` — short-circuit to `worktree-only` regardless of
   detected engines.

### Shell-injection hardening (exec-style argv)

Sandbox providers (`podman.sh`, `docker.sh`) dispatch the inner command as
**exec-style argv**, never as a shell string. The env-scrub prefix is read via
`env-scrub.py --prefix-args` (one token per line: `env`, then alternating
`-u VAR` pairs), loaded into a bash array with `mapfile -t prefix`, and
passed alongside the user's argv:

```bash
mapfile -t prefix < <(python3 "${claude_home}/hooks/env-scrub.py" --prefix-args)
podman run --rm ... "$image" "${prefix[@]}" "$@"
```

This eliminates the shell-injection surface that `sh -c "$scrubbed"` would
expose if a caller ever passed AI-generated text containing shell
metacharacters. Provider authors **must not** reintroduce `sh -c` for
command dispatch — `claude/lib/sandbox/tests/test_no_shell_injection.sh`
guards against regression.

The `sandbox_enter` API surface is unchanged: callers still invoke
`sandbox_enter "$wt" cmd arg1 arg2 ...` exactly as before.

### Build & Pull

The sandbox base image is built locally from `scripts/sandbox/Containerfile`
via the wrapper script:

```bash
bash scripts/sandbox/build.sh
export PIPELINEKIT_SANDBOX_TAG=pipelinekit/sandbox-base:<git-short-sha>
```

The build script auto-detects `podman` (preferred) or `docker`, applies the
`pipelinekit/sandbox-base:latest` alias locally (suppress with `--no-latest`),
and prints the exact `export` line for the resolved tag on success.

The image is **local-only**: there is no `push` step in `build.sh` and no
registry hostname appears in the recipe. Do not publish this image to a
public registry — the namespace is unclaimed and the recipe omits any
registry-pin or signature step that would make a public publish safe.

Size budget: the slim base + apt cache cleanup keeps the compressed image
under 1 GB. Enforcing that ceiling in CI (assert `<engine> image inspect`
size) is a follow-up; today it is a soft target verified by inspection.

WSL2 storage hygiene: layered worktrees and npm caches can balloon on
Windows-hosted Linux. Reclaim space with `podman system prune` or
`docker system prune` after pipeline runs accumulate unused layers.

## Optional subprocess driver

`claude/skills/pipeline/orchestrate.sh` ships as an **OPTIONAL** out-of-process
driver stub. The in-process `/pipeline` Skill remains the canonical entry
point for interactive sessions. The stub exists for unattended runs (CI cron,
scheduled batch processing) where maximum context isolation between phases
matters more than the convenience of the in-process Skill.

The stub exposes a single library function:

```bash
. claude/skills/pipeline/orchestrate.sh
run_phase analyze prompt.txt /path/to/worktree
```

`run_phase` reads the phase prompt from a file, then dispatches `claude -p`
**inside** the sandbox provider chosen by `claude/lib/sandbox/SandboxProvider.sh`
— i.e., the subprocess invocation participates in the same `sandbox_enter` /
`sandbox_exit` isolation boundary used by the in-process Skill.

**Charter Discovery constraint.** A subprocess driver cannot run Step 0
Charter Discovery because `AskUserQuestion` is interactive-session-only. When
generating phase prompts for unattended runs, pass `--no-charter` to the
`/pipeline` invocation that produced the prompt files (or adopt a pre-built
charter with `--charter <path>`).

**Stub scope.** `orchestrate.sh` demonstrates the per-phase wrapping contract.
A full driver must iterate over phases and features, persist
`docs/pipeline-state.md` between phases, and handle Path A/B/C transitions
per the contract in `~/.claude/skills/pipeline/reference.md`. Forks are
expected to extend the stub; the upstream stub deliberately does not
re-implement the full pipeline loop.

**Wrap surface (multi-callsite).** `orchestrate.sh` exposes three wrap helpers: `run_phase` (wraps `claude -p`), `run_host_adapter` (wraps `host-adapters/<host>.sh`), and `run_mcp` (wraps an MCP-server launch — interface-first scaffolding, no consumer ships using it today). All three dispatch via the public `sandbox_wrap <task-id> <worktree> <command...>` helper, which emits `SANDBOX_ENTER: provider=<X>, task=<task-id>, image=<image>` to stderr at wrap time. Forks adding new external-subprocess entry points should reuse `sandbox_wrap`.

**Worktree-only delegation (in-process Skill).** When `provider_detect` resolves to `worktree-only`, the in-process Skill should prefer the native `EnterWorktree` tool (Claude Code `>= 2.1.143`) with `worktree.bgIsolation` and `worktree.baseRef` settings, instead of bash worktree plumbing. The subprocess driver itself remains bash-only (the legacy `(cd "$wt" && exec "$@")` body in `providers/worktree-only.sh`) — this delegation note is for the in-process Skill path. See the [Claude Code changelog](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md) for the `worktree.bgIsolation` (2.1.143) and `worktree.baseRef` (2.1.133) entries. Actual delegation in the in-process Skill is deferred to a follow-up feature.

## What was removed in the portable build

- `claude -p` subprocess invocations as the **primary** phase-dispatch mechanism.
  Phase dispatch in the in-process Skill is always via the `Agent` tool with
  subagent isolation. The optional `orchestrate.sh` stub (see above) is the
  only place `claude -p` still appears in shipped code.
