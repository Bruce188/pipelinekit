# implement-plan — Reference

Appendix material consulted by `SKILL.md` but not executed inline. Each section is cited from the corresponding step via a `See reference.md § <heading>` pointer. Step anchors in `SKILL.md` (e.g. `Step 1.5`, `Step 2c`, `Step 2d`, `Step 2e.5`) are NOT renumbered here — this file only holds the verbose boilerplate, rationale, and worked detail extracted from those steps.

---

## WorkerProvider & Mixed-Worker Batches

Cited from **Step 1.5: Parallel Execution**.

**WorkerProvider contract (operational):** The worktree fan-out described in Step 1.5 items 1–5 IS the reference implementation of the `ClaudeWorker` class documented in `claude/lib/worker-provider/claude.md`. The five worktree-agent lifecycle steps (prepare worktree → dispatch → collect artifacts → verify completion → cleanup) map directly to the five `WorkerProvider` methods in `claude/lib/worker-provider/interface.md`. Per-task `worker:` header routing is active — see `5.a.routing` in SKILL.md. ClaudeWorker remains the default when no routing override is in effect.

**Mixed-worker batches:** A single phase's parallel tasks may dispatch to heterogeneous worker classes. The lifecycle (5.a prepare → 5.f.5 squash-merge) is provider-agnostic by design — the lead does not need to know which class each worktree agent used. Contract:

- A single phase may contain tasks with different `worker:` classes (e.g., `worker: claude` or any registered class in `claude/lib/worker-provider/`). Each task resolves its class independently via `5.a.routing`.
- Cross-worker scratchpad notes (`*-to-*.md`) route across worker classes because they are plain markdown files on disk at `$SCRATCHPAD`. Any task, regardless of class, can read and write notes there.
- The lead **squash-merges all worktree branches** — regardless of their origin class — into ONE conventional commit on the working branch. Worker-class names MUST NOT appear in the merge commit message.
- The beacon line at dispatch emits `worker=<class>` per task so the run log captures which class handled each task. This is the only place where the class is surfaced.
- If a non-default class's host-adapter is unavailable (exit 2), `WORKER_UNAVAILABLE: <class>` is logged and ClaudeWorker handles that task. If the adapter exits other non-zero, `WORKER_FALLBACK: <task-id> <class> -> claude (<reason>)` is logged and ClaudeWorker retries once — see `claude/lib/worker-provider/interface.md` § Fallback semantics.

**Acceptance criteria for mixed-class batches:**
1. One squash commit on the working branch after all workers complete.
2. Per-task beacon lines with `worker=<class>` in the run log.
3. Scratchpad cross-class routing works (any task can read any note regardless of its class).

See `claude/skills/research/tests/test_mixed_worker_fanout.sh` for the smoke fixture.

---

## Worker-Class Routing & Fan-out Cap

Cited from **Step 1.5** sub-steps `a.routing` and `a-cap`.

**`a.routing` — full resolution order** (mirrors `claude/lib/worker-provider/interface.md` § Env-var resolution). For each task, resolve the worker class before constructing the agent prompt:
1. If `PIPELINE_NO_WORKER_ROUTING=1` is set → `claude` (ClaudeWorker, unconditional).
2. Read the task's optional `worker:` header from the prompts file. If present and the class file `claude/lib/worker-provider/<class>.md` exists → that class.
3. If `WORKER_CLASS=<name>` env var is set → that class (same existence check).
4. `WORKER_CLASS=auto` or unset → `claude` (ClaudeWorker, the always-available default).

Store the resolved class as `$WORKER` for use in the beacon and prompt construction. Apply the two-tier fallback policy (one fallback attempt max — second failure marks task `failed`):
- Host-adapter exits **2** (runtime absent): log `WORKER_UNAVAILABLE: <class> (host-adapter missing)` and re-dispatch via ClaudeWorker — do not halt the pipeline.
- Host-adapter exits **other non-zero** (runtime present, execution failed): log `WORKER_FALLBACK: <task-id> <class> -> claude (exit <rc>)` and re-dispatch via ClaudeWorker once. Second failure marks the task `failed`.

See `claude/lib/worker-provider/interface.md` § Fallback semantics for the authoritative contract.

**`a-cap` — fan-out cap rationale.** Cap parallel fan-out at 8 worktree agents per batch. Per the Anthropic community ceiling, more than 8 simultaneous worktree agents reliably saturates the lead's merge loop and increases conflict probability. If `len(parallelizable_tasks_in_phase) > 8`, partition into batches of 8 (final batch may be smaller). Run each batch as a complete Step 1.5 cycle — construct prompts (5.a), spawn agents (5.b), wait (5.d), run the merge loop (5.e), surface scratchpad notes (5.f.5), clean up (5.f) — before starting the next batch. The scratchpad is per-batch (each batch creates its own `$PHASE_ID` directory). Tasks waiting for a later batch remain marked `todo` until their batch runs.

---

## tdd-test-writer Subagent Prompt

Cited from **Step 2c: TDD Red Phase**. Spawn the `tdd-test-writer` agent as a context-isolated subagent (NOT Agent Teams) with the Agent tool:

```
Agent tool parameters:
  model: sonnet
  prompt: |
    [CHARTER_CONTEXT — insert verbatim if non-empty, omit if empty]

    Task: [task name]
    Objective: [from task prompt]
    Tests: [from plan's Tests: section]
    Files: [file list from plan]
    Project test command: [detected test command]

    You are a test writer. Write failing tests that define the expected behavior
    based on the spec above. Do NOT implement any production code.

    Rules:
    1. Write test files that capture the expected behavior
    2. If the test runner cannot import modules that don't exist yet, create a
       minimal empty module (just `pass` or `export {}`) so assertions can run
    3. Run the test suite to confirm your new tests FAIL (red phase)
    4. If tests already pass, they are not asserting new behavior — revise them
    5. Commit your test files: git add <test-files> && git commit -m "test: red phase for [task name]"
    6. Report: which tests were written, which assertions they make, confirmation they fail
```

If the current task prompt specifies a `Model:` header (e.g., `Model: opus`), use that model instead of `sonnet` for the tdd-test-writer subagent.

**For reopened/new tasks from review** (tasks with `reopened: review-vN` or `new: review-vN` notes): replace the Tests section with the **Review Tests:** section from the task prompt:
- test-engineer findings: the finding IS the test spec — pass it directly
- security-auditor findings: instruct the test-writer to exercise the vulnerable path
- Non-unit-testable findings (nit-level style, naming): skip TDD, note "TDD skipped: finding not unit-testable"

Wait for the agent to complete. Do NOT pass the agent's reasoning to subsequent steps — only the files on disk matter.

---

## tdd-implementer Subagent Prompt

Cited from **Step 2d: TDD Green Phase**. Spawn the `tdd-implementer` agent as a context-isolated subagent:

```
Agent tool parameters:
  model: sonnet
  prompt: |
    Task: [task name]
    Objective: [from task prompt]
    Test files: [TEST_FILES from Step 2c.5]
    Source files: [file list from plan]
    Constraints: [from task prompt]

    Failing tests exist. Write the minimum production code to make them pass.

    Rules:
    1. Read the failing test files to understand expected behavior
    1.5. Prefer `mcp__serena__find_symbol` / `mcp__serena__find_referencing_symbols` for locating symbols and their callers before editing; fall back to Grep when serena is unavailable.
    2. Implement production code to make all failing tests pass
    3. Do NOT modify any test files — if a test seems wrong, report it as a finding
    4. Run the full test suite to confirm ALL tests pass (green phase)
    5. Commit: git add <source-files> && git commit -m "<type>: [task name]"
       Use feat: for new features, fix: for bug fixes, refactor: for restructuring
```

If the current task prompt specifies a `Model:` header (e.g., `Model: opus`), use that model instead of `sonnet` for the tdd-implementer subagent.

The implementer does NOT receive the test-writer's reasoning — only the test files on disk and the task spec.

If the task prompt specifies `Agent: [other-agent-name]` instead of using TDD subagents:
- Spawn the named agent with the task description as the prompt
- Wait for the agent's result before verifying

If the task prompt specifies `Agent: none` AND TDD was skipped:
- Execute directly in the current session

Wait for the agent to complete.

---

## Test-Run Inner Loop — Detail

Cited from **Step 2e.5: Test-Run Inner Loop**.

**Detect helper.** The detect helper lives at `claude/lib/pipeline/test_runner_detect.py`. It is pure stdlib, never `eval`/`exec`s, and returns one of `"pytest"`, `"npm test"`, `"go test ./..."`, `"make test"`, or `None`. First-match-wins probe order: pytest (pyproject.toml | setup.py) → npm test (package.json with non-empty scripts.test) → go test (go.mod) → make test (Makefile with `^test:` target). Auto-detection is best-effort — projects using `tox`, `nox`, `cargo test`, `dotnet test`, `mix test`, etc. fall through to `NO_TEST_RUNNER_DETECTED` and the loop is skipped.

**Output capping.** Combined stdout+stderr is truncated to the last 4 KB before being passed to the fix subagent. Larger outputs would overrun the subagent context budget; the tail almost always contains the actionable failure.

**Budget accounting.** Each `run(CMD)` is a subprocess invocation, not an LLM call — it does NOT consume `--max-usd` tokens directly. The fix-retry subagent dispatches ARE counted by the existing `--max-usd` / `--max-turns` accounting. The orchestrator's existing phase-boundary budget check (`/pipeline` Step 1.46) suffices; no new budget plumbing.

**Path B escalation contract.** A 4th-retry failure (i.e. `RETRY > 3`) returns failure to the orchestrator using the same exit semantics as any other implement-phase failure. `/pipeline` Step 5.7 routes implement-phase failures to Path B (re-implement under review feedback) by default. The TEST_LOOP_EXHAUSTED log line + the captured 4 KB tail surface in the orchestrator's run log so Path B receives the failing-test context.

**Parallel path inheritance.** When `/implement-plan` runs in parallel mode (Step 1.5 worktree fan-out), each worktree agent inherits this Step 2e.5 contract by reference — the per-task loop runs inside the worktree before the agent reports done. The lead does NOT re-run Step 2e.5 after squash-merge; it only re-runs the plan's verification step (Step 1.5 sub-step 5.e). Per-worktree TEST_LOOP_EXHAUSTED escalations surface via the worktree agent's `<task-notification>` `<status>failed</status>`.
