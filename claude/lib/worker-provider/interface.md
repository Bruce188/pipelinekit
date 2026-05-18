# WorkerProvider

The contract every worker class implements to dispatch a single plan task to
its execution environment and return committed artifacts to the lead.

Mirrors the structural pattern of `claude/lib/sandbox/SandboxProvider.sh` —
a top-level interface + per-class implementations in sibling files
(`claude.md`, future `<other>.md`). Phase 1 of the worker-delegation
initiative ships this interface as documentation only — no routing code is
wired. ClaudeWorker (see `claude.md`) is the always-available default.

---

## Methods

Every WorkerProvider implementation MUST document the following five methods.

### `prepare_workspace(task_spec) -> workspace_path`

Materialize a working directory for the task. For ClaudeWorker, this is a
git worktree at `.claude/worktrees/agent-<task-id>` with the working branch
checked out. For other classes, this may be a container, a remote tmpfs, or
another isolated filesystem boundary.

The returned `workspace_path` is the directory the worker writes into.

### `dispatch(workspace_path, task_spec) -> dispatch_handle`

Hand the task off to the worker runtime. For ClaudeWorker, this is an
`Agent` tool invocation with the prompt assembled from `task_spec`. For
other classes, this may shell out via `claude/host-adapters/<class>.sh` to
a subprocess.

Returns an opaque `dispatch_handle` used by `collect_artifacts` and
`verify_completion` to locate the worker's output.

### `collect_artifacts(dispatch_handle) -> artifact_set`

Wait for the worker to finish, then gather its output. Returns at minimum:

- the `<task-notification>` XML block (see § Required artifacts below)
- the worker's commit hash on its worktree branch (if applicable)
- any side-effect file paths the worker reports it wrote

### `verify_completion(artifact_set) -> bool`

Apply the contract checks defined in § Failure semantics below. Returns
true on a successful task; false on missing artifacts, malformed XML,
missing commit, or `status: failed`.

### `cleanup(dispatch_handle)`

Tear down the worker's workspace. For ClaudeWorker, this removes the
worktree branch and directory after a successful squash-merge.

---

## Required artifacts

Every worker, regardless of class, MUST produce the following before
`verify_completion` returns true:

1. A `<task-notification>` XML block as the LAST content in the worker's
   final response, conforming to the schema in
   `claude/rules/agents-worktrees.md` § Worktree Agent Task-Notification XML.
2. At least one commit on the worker's branch with a non-empty subject.
   For testable tasks under the TDD doctrine, the commit history MUST
   contain a `test:` commit preceding any implementation commit (the
   red-then-green gate in `/implement-plan` Step 1.5).
3. Any file paths listed in the `<files>` element of the task-notification
   MUST exist on disk after `collect_artifacts` returns.

---

## Failure semantics

`verify_completion` returns false on any of:

- `<task-notification>` block missing or malformed (parser cannot extract
  `status`, `task-id`, `summary`).
- `<status>` is `failed` or `blocked`.
- No commits on the worker's branch (uncommitted changes are lost on
  cleanup, so an absent commit means lost work).
- For Testable tasks: no `test:` commit, or non-test commit precedes the
  first `test:` commit (red-then-green ordering violated).
- File path in `<files>` does not resolve on disk.

On false return, the lead leaves the task `todo` in `docs/progress.md`,
does NOT squash-merge the worker's branch, and reports the specific
failure mode to the run log. Other parallel workers continue normally.

---

## Env-var resolution

The resolution order for which `WorkerProvider` class to load is analogous
to `SandboxProvider.sh`:

1. `PIPELINE_NO_WORKER_ROUTING=1` → unconditional `claude` (ClaudeWorker)
2. `worker:` header on the per-task plan prompt → that worker class, if
   `claude/lib/worker-provider/<class>.md` exists; else log to stderr and
   fall back to `claude`
3. `WORKER_CLASS=<name>` env var → that class; same fallback rule
4. `WORKER_CLASS=auto` or unset → `claude` (the always-available default)

**Phase 1 reservation:** This resolution order is documented for the
future Phase 3 routing implementation. In the current build, no routing
logic is wired; `WORKER_CLASS` and the `worker:` header are acknowledged
but ignored — every dispatch goes through ClaudeWorker.

---

## See also

- `claude/lib/worker-provider/claude.md` — ClaudeWorker default
  implementation (the always-available baseline).
- `claude/lib/worker-provider/task-spec.md` — the per-task spec schema
  every worker reads.
- `claude/lib/sandbox/SandboxProvider.sh` — sibling library providing the
  optional sandbox boundary that workers compose with via
  `task_spec.routing.sandbox`.
- `claude/rules/agents-worktrees.md` — the worktree-agent and
  task-notification conventions ClaudeWorker uses.
