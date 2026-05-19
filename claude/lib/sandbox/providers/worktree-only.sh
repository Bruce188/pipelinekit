#!/usr/bin/env bash
# claude/lib/sandbox/providers/worktree-only.sh — No-op default sandbox provider.
#
# This provider is selected when:
#   - PIPELINE_NO_SANDBOX=1 (escape hatch — unconditional short-circuit, overrides any SANDBOX_PROVIDER)
#   - SANDBOX_PROVIDER is unset (dispatcher default; no behavior change from pre-sandbox pipelinekit)
#   - SANDBOX_PROVIDER=worktree-only (explicit opt-in)
#   - SANDBOX_PROVIDER=auto AND neither podman nor docker is available on PATH (discovery fallback)
#
# Public interface (implements the SandboxProvider contract):
#   sandbox_enter <worktree-path> <command...>   — cd into worktree and exec the command
#   sandbox_exit  <session-id>                    — no-op; no container session to clean up
#
# PIPELINE_NO_SANDBOX=1: respected upstream in provider_detect(); this file implements
#   the same no-op behaviour regardless of that flag.
#
# This file is sourced, never executed directly.

# sandbox_enter <worktree-path> <command...>
#   Changes into the worktree directory and execs the command directly.
#   No sandbox boundary — the command runs in the current process environment.
sandbox_enter() {
  local wt="$1"; shift
  (cd "$wt" && exec "$@")
}

# sandbox_exit <session-id>
#   No-op. There is no container session to clean up for the worktree-only provider.
sandbox_exit() {
  # Nothing to do — worktree-only does not start any persistent session.
  return 0
}
