# Task Spec

The schema for the per-task spec artifact that every WorkerProvider reads
to dispatch one plan task. The pipeline serializes one task spec per `todo`
task into `.claude/tasks/<task-id>/spec.md` before dispatch; the worker
reads its own spec file and writes its output (commits + task-notification)
back into the worktree.

This schema is documentation only in Phase 1 of the worker-delegation
initiative; no on-disk materialization happens yet. Phase 3 will wire the
pipeline implement-phase to write `.claude/tasks/<task-id>/spec.md` files
before dispatching workers.

---

## Schema

| Field                    | Type        | Required | Description                                                                  |
|--------------------------|-------------|----------|------------------------------------------------------------------------------|
| `id`                     | string      | yes      | Plan task ID (e.g. `1.1`, `2.3`).                                            |
| `objective`              | string      | yes      | One-sentence objective copied verbatim from the plan task's Objective field. |
| `inputs`                 | string list | yes      | Absolute paths the worker reads but does NOT modify. May be empty.           |
| `files_in_scope`         | string list | yes      | Absolute paths the worker is permitted to create or modify.                  |
| `expected_outputs`       | string list | yes      | Absolute paths the worker MUST produce. Verified post-dispatch.              |
| `verification`           | string      | yes      | The plan task's Verification command, copied verbatim.                       |
| `routing.worker_class`   | string      | no       | Worker class name (default `claude`). See `interface.md` § Env-var resolution. |
| `routing.sandbox`        | string      | no       | Optional sandbox provider name (`worktree-only`, `podman`, `docker`).         |

### Example (YAML rendering)

```yaml
id: "1.1"
objective: "Create claude/lib/worker-provider/interface.md per plan v20."
inputs:
  - /home/bruce/pipelinekit/claude/lib/sandbox/SandboxProvider.sh
files_in_scope:
  - /home/bruce/pipelinekit/claude/lib/worker-provider/interface.md
expected_outputs:
  - /home/bruce/pipelinekit/claude/lib/worker-provider/interface.md
verification: "grep -q '^# WorkerProvider' claude/lib/worker-provider/interface.md"
routing:
  worker_class: claude
  sandbox: worktree-only
```

---

## Materialization

The pipeline writes one spec file per task to:

```
.claude/tasks/<task-id>/spec.md
```

The directory is created on demand at implement-phase entry. The format on
disk is a markdown front-matter block followed by free-form `## Section`
bodies (objective in prose, then file lists as fenced bash, then routing
as fenced YAML). Workers locate their spec via the env var
`WORKER_TASK_SPEC` pointing at the absolute path.

Materialization is reserved for Phase 3 wiring; in the current build, no
spec file is written. ClaudeWorker today assembles its prompt directly
from the plan + prompts files via `/implement-plan` Step 1.5.

---

## Routing defaults

When `routing.worker_class` is omitted (or set to `claude`), the pipeline
dispatches via ClaudeWorker — the in-session Agent-tool worktree fan-out
documented in `claude/lib/worker-provider/claude.md`. The default for
`routing.worker_class` is `claude`.

When `routing.sandbox` is omitted, the pipeline uses the SandboxProvider
resolution order from `claude/lib/sandbox/SandboxProvider.sh` (env-var
driven: `PIPELINE_NO_SANDBOX=1` → worktree-only; `SANDBOX_PROVIDER=<name>`
→ that provider with fallback; auto → podman → docker → worktree-only).

---

## See also

- `claude/lib/worker-provider/interface.md` — the WorkerProvider contract.
- `claude/lib/worker-provider/claude.md` — ClaudeWorker default impl.
- `claude/lib/sandbox/SandboxProvider.sh` — sandbox provider library.
