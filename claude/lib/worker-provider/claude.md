# ClaudeWorker

The default `WorkerProvider` implementation. Always available; requires no
external runtime. ClaudeWorker is a documentation alias for the existing
in-session Agent-tool worktree fan-out described in
`claude/skills/implement-plan/SKILL.md` § Step 1.5 — Parallel Execution.
Phase 1 of the worker-delegation initiative names that existing behavior
and pins its contract; no new code is introduced.

ClaudeWorker is what runs when:

- the plan task prompt has no `worker:` header, OR
- the plan task prompt has `worker: claude`, OR
- `WORKER_CLASS=auto` or `WORKER_CLASS` is unset, OR
- `PIPELINE_NO_WORKER_ROUTING=1` is set.

Until Phase 3 of the worker-delegation initiative wires routing, every
dispatch in the portable build is ClaudeWorker regardless of header.

---

## Method mapping

The five `WorkerProvider` methods in `interface.md` map to the existing
`/implement-plan` Step 1.5 lifecycle as follows:

| Method                | ClaudeWorker realization                                                                    |
|-----------------------|---------------------------------------------------------------------------------------------|
| `prepare_workspace`   | Create a git worktree at `.claude/worktrees/agent-<task-id>` with the working branch.       |
| `dispatch`            | Invoke the `Agent` tool with `isolation: "worktree"` and the assembled task prompt.         |
| `collect_artifacts`   | Parse the `<task-notification>` XML from the agent's final response; locate the worktree commit. |
| `verify_completion`   | Run the pre-merge TDD red-commit gate (Testable tasks) and the task's Verification step.    |
| `cleanup`             | Delete the worktree branch and `.claude/worktrees/agent-<task-id>` directory after a successful squash-merge. |

These steps are the literal Step 1.5 numbered items 1–5 from
`claude/skills/implement-plan/SKILL.md`; ClaudeWorker does not change them
— it names them.

---

## Required artifacts (ClaudeWorker)

Every ClaudeWorker dispatch MUST produce, before `verify_completion` returns
true:

1. A `wip: <task name>` commit on the worktree branch.
   Source: `claude/rules/agents-worktrees.md` § Worktree Agent Prompt Requirement.
2. A `<task-notification>` XML block at the END of the agent's final
   response (so the lead can regex-extract it unambiguously).
   Source: `claude/rules/agents-worktrees.md` § Worktree Agent Task-Notification XML.
3. For Testable tasks: a `test:` commit on the worktree branch preceding
   any `feat:`/`fix:`/`refactor:`/`perf:` commit (the red-then-green
   ordering enforced by Step 1.5's pre-merge TDD gate).

Missing commit, missing/malformed XML, or wrong commit ordering all fail
verification.

---

## Cross-worker scratchpad

ClaudeWorker dispatches all participate in the shared scratchpad at
`.claude/scratchpad/<phase-id>/`. Sibling workers leave notes named
`<your-stream>-to-<sibling-stream>.md` to communicate without sharing
file contents. The scratchpad lifecycle is documented in
`claude/rules/agents-worktrees.md` § Cross-Worker Scratchpad — ClaudeWorker
inherits it unchanged.

---

## Fan-out cap

Per `/implement-plan` Step 1.5 item a-cap: ClaudeWorker fan-out is capped
at 8 simultaneous workers per batch. Batches larger than 8 are partitioned
and run sequentially (one complete Step 1.5 cycle per batch). The cap is
the Anthropic community ceiling and is not configurable in this build.

---

## Subprocess mode

The pipelinekit portable build dispatches in-session via the `Agent` tool.
The `claude/host-adapters/claude.sh` shell adapter exists as the
subprocess dispatch surface for a future out-of-process driver (not
shipped). When a fork re-introduces a subprocess driver, ClaudeWorker's
out-of-process variant SHOULD shell out via
`claude/host-adapters/claude.sh <prompt-file> <output-file>` rather than
invoking `claude -p` directly, so the host-adapter contract is the only
process boundary.

---

## Always-available default — no external runtime

ClaudeWorker requires:

- a git checkout (worktree support — git ≥ 2.5)
- the `Agent` tool (built into the Claude Code session host)
- nothing else.

There is no daemon, no port, no Docker image, no remote endpoint, no
extra binary. This is the baseline that every pipelinekit consumer can
run today — every other worker class is opt-in on top of this default.

---

## See also

- `claude/lib/worker-provider/interface.md` — the contract this file
  implements.
- `claude/lib/worker-provider/task-spec.md` — the per-task spec schema
  ClaudeWorker will read once Phase 3 materialization is wired.
- `claude/skills/implement-plan/SKILL.md` § Step 1.5 — the canonical
  worktree fan-out behavior ClaudeWorker names.
- `claude/rules/agents-worktrees.md` — worktree-agent and
  task-notification conventions.
- `claude/host-adapters/claude.sh` — the future subprocess dispatch
  surface (not currently invoked).
