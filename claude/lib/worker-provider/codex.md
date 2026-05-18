# CodexWorker

A `WorkerProvider` implementation that delegates task dispatch to the Codex
CLI via the `claude/host-adapters/codex.sh` host adapter. CodexWorker is an
opt-in alternative to the always-available ClaudeWorker; it is active when:

- the plan task prompt has `worker: codex`, OR
- `WORKER_CLASS=codex` is set in the environment.

When the Codex CLI binary is absent from PATH, `codex.sh` exits 2 and
CodexWorker falls back to ClaudeWorker automatically — the pipeline does not
halt. The fallback path is the canonical test path for this build because the
Codex CLI is not installed on the host.

CodexWorker workspace preparation and artifact collection follow the same
worktree lifecycle as ClaudeWorker. The only difference is in the `dispatch`
method: instead of an in-session `Agent` tool invocation, CodexWorker shells
out to `claude/host-adapters/codex.sh`.

---

## Overview

CodexWorker materializes a git worktree for the task (identical to
ClaudeWorker's `prepare_workspace`), then hands the assembled task spec to
`codex.sh` which calls `codex exec`. Stdout is captured to
`.claude/tasks/<task-id>/output/stdout`; stderr to `.../stderr`; the process
exit code to `.../exit`. On exit 0, `collect_artifacts` reads stdout as the
artifacts list per the WorkerProvider contract. On exit 2 (Codex CLI absent),
CodexWorker logs `WORKER_UNAVAILABLE: codex (host-adapter missing)` and
re-dispatches the task through ClaudeWorker.

CodexWorker is functionally equivalent to ClaudeWorker for the lead's merge
loop — it produces the same worktree branch, the same `<task-notification>`
XML, and the same commit structure. The lead squash-merges and cleans up the
same way regardless of which worker class executed the task.

---

## Methods

| Method               | CodexWorker realization                                                                               |
|----------------------|-------------------------------------------------------------------------------------------------------|
| `prepare_workspace`  | Create a git worktree at `.claude/worktrees/agent-<task-id>` with the working branch checked out. Inherits the `.worktreeinclude` bind-mount behavior from `claude/rules/agents-worktrees.md` § Env handoff. |
| `dispatch`           | Shell out to `claude/host-adapters/codex.sh <prompt-file> <output-file>` with the worktree path mounted; capture stdout/stderr/exit code into `.claude/tasks/<task-id>/output/`. On exit 2: log `WORKER_UNAVAILABLE: codex (host-adapter missing)`, re-dispatch via ClaudeWorker. |
| `collect_artifacts`  | Read stdout from `.claude/tasks/<task-id>/output/stdout` as the artifacts list per the WorkerProvider contract in `interface.md`. |
| `verify_completion`  | Enforce all Phase-1 required artifacts: `<task-notification>` XML as last content; at least one commit on the worker branch with non-empty subject; all paths in `<files>` exist on disk. Fan-out cap of 8 per `/implement-plan` Step 1.5 a-cap. |
| `cleanup`            | Delete the worktree branch and `.claude/worktrees/agent-<task-id>` directory after a successful squash-merge and test run — identical to ClaudeWorker cleanup. |

---

## Required artifacts

Every CodexWorker dispatch MUST produce, before `verify_completion` returns
true:

1. A `wip: <task name>` commit on the worktree branch.
   Source: `claude/rules/agents-worktrees.md` § Worktree Agent Prompt Requirement.
2. A `<task-notification>` XML block at the END of the worker's final
   response (so the lead can regex-extract it unambiguously).
   Source: `claude/rules/agents-worktrees.md` § Worktree Agent Task-Notification XML.
3. For Testable tasks: a `test:` commit on the worktree branch preceding
   any `feat:`/`fix:`/`refactor:`/`perf:` commit (the red-then-green
   ordering enforced by Step 1.5's pre-merge TDD gate).

Missing commit, missing/malformed XML, or wrong commit ordering all fail
verification — identical contract to ClaudeWorker.

---

## Failure semantics

Two distinct failure cases apply to CodexWorker:

**Case A — Codex CLI absent from PATH:**
`codex.sh` detects that `codex` is not on PATH, writes
`WORKER_UNAVAILABLE: codex (host-adapter missing)` to stderr, and exits 2.
CodexWorker catches the exit-2 signal, logs the `WORKER_UNAVAILABLE` line to
the run log, and re-dispatches the task via ClaudeWorker. The pipeline does
not halt; no task is marked failed by the fallback itself.

**Case B — `codex exec` runs but the task fails:**
`codex.sh` passes the exit code through. The `<task-notification>` XML in the
captured stdout carries `status: failed` or `status: blocked`. `verify_completion`
returns false, the lead leaves the task as `todo` in `docs/progress.md`, and
reports the specific failure mode. This is the standard `interface.md`
§ Failure semantics flow — CodexWorker adds no special handling.

---

## Env-var resolution

CodexWorker participates in the same resolution order defined in
`claude/lib/worker-provider/interface.md` § Env-var resolution:

1. `PIPELINE_NO_WORKER_ROUTING=1` — unconditional `claude` (ClaudeWorker); CodexWorker is never reached.
2. `worker: codex` header on the per-task plan prompt — CodexWorker selected.
3. `WORKER_CLASS=codex` env var — CodexWorker selected.
4. `WORKER_CLASS=auto` or unset — `claude` (ClaudeWorker, the always-available default).

No other resolution logic is introduced here. The four-step order is
authoritative in `interface.md`; this file reproduces it verbatim for
reference only.

---

## Cross-worker scratchpad

CodexWorker dispatches participate in the shared scratchpad at
`.claude/scratchpad/<phase-id>/`. Sibling workers (whether ClaudeWorker or
CodexWorker instances) leave notes named
`<your-stream>-to-<sibling-stream>.md` to communicate without sharing file
contents. The scratchpad lifecycle is documented in
`claude/rules/agents-worktrees.md` § Cross-Worker Scratchpad — CodexWorker
inherits it unchanged.

---

## See also

- `claude/lib/worker-provider/interface.md` — the contract this file implements.
- `claude/lib/worker-provider/task-spec.md` — the per-task spec schema.
- `claude/lib/worker-provider/claude.md` — ClaudeWorker, the always-available default.
- `claude/host-adapters/codex.sh` — the shell adapter this worker dispatches through.
- `claude/host-adapters/README.md` — host-adapter interface contract and exit-code semantics.
