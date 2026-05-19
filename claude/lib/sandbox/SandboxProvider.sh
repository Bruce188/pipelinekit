#!/usr/bin/env bash
# claude/lib/sandbox/SandboxProvider.sh — Pluggable sandbox boundary for Claude Code pipelines.
#
# Public interface (all providers MUST implement):
#   sandbox_enter <worktree-path> <command...>   # exec command inside the sandbox boundary
#   sandbox_exit  <session-id>                    # cleanup; no-op for worktree-only
#   provider_detect                               # echo the resolved provider name to stdout
#
# Resolution order:
#   1. PIPELINE_NO_SANDBOX=1            → worktree-only (unconditional short-circuit)
#   2. SANDBOX_PROVIDER=<name>          → use that provider if binary exists; else log to stderr
#                                          and fall back to worktree-only
#   3. SANDBOX_PROVIDER=auto            → try podman → docker → worktree-only
#      SANDBOX_PROVIDER unset           → worktree-only (no behavior change from pre-sandbox default)
#
# Sourcing pattern (callers):
#   source "$CLAUDE_HOME/lib/sandbox/SandboxProvider.sh"
#   PROVIDER=$(provider_detect)
#   source "$CLAUDE_HOME/lib/sandbox/providers/${PROVIDER}.sh"
#   sandbox_enter "$WORKTREE" claude -p "$PROMPT"
#
# PIPELINE_NO_SANDBOX=1: unconditional short-circuit to worktree-only regardless of
#   SANDBOX_PROVIDER. Set this to disable all container isolation (e.g. in CI or
#   environments where container runtimes are unavailable or unwanted).
#
# This file is sourced, never executed directly.
#
# Env vars:
#   SANDBOX_PROVIDER        — provider name: worktree-only | podman | docker | auto (default: worktree-only)
#   PIPELINE_NO_SANDBOX     — set to 1 to unconditionally skip container isolation
#   SANDBOX_PODMAN_IMAGE    — per-engine image override for the podman provider
#                             (highest precedence). Default fallback path:
#                             SANDBOX_PODMAN_IMAGE → PIPELINEKIT_SANDBOX_TAG →
#                             localhost/pipelinekit/sandbox-base:latest.
#   SANDBOX_DOCKER_IMAGE    — per-engine image override for the docker provider
#                             (highest precedence). Default fallback path:
#                             SANDBOX_DOCKER_IMAGE → PIPELINEKIT_SANDBOX_TAG →
#                             pipelinekit/sandbox-base:latest.
#   PIPELINEKIT_SANDBOX_TAG — cross-engine default tag consumed by both providers
#                             when no per-engine override is set. The build script
#                             scripts/sandbox/build.sh prints the export line for
#                             this var on success.

# ---------------------------------------------------------------------------
# provider_detect
#   Echoes the resolved provider name to stdout. Does not source the provider.
# ---------------------------------------------------------------------------
provider_detect() {
  # Escape hatch: PIPELINE_NO_SANDBOX=1 unconditionally resolves to worktree-only.
  if [ "${PIPELINE_NO_SANDBOX:-0}" = "1" ]; then
    echo worktree-only
    return 0
  fi

  local req="${SANDBOX_PROVIDER:-worktree-only}"
  case "$req" in
    worktree-only)
      echo worktree-only
      ;;
    podman)
      if command -v podman >/dev/null 2>&1; then
        echo podman
      else
        echo "sandbox: requested provider podman unavailable, falling back to worktree-only" >&2
        echo worktree-only
      fi
      ;;
    docker)
      if command -v docker >/dev/null 2>&1; then
        echo docker
      else
        echo "sandbox: requested provider docker unavailable, falling back to worktree-only" >&2
        echo worktree-only
      fi
      ;;
    auto)
      if command -v podman >/dev/null 2>&1; then
        echo podman
      elif command -v docker >/dev/null 2>&1; then
        echo docker
      else
        echo worktree-only
      fi
      ;;
    *)
      echo "sandbox: unknown SANDBOX_PROVIDER '$req', falling back to worktree-only" >&2
      echo worktree-only
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Default no-op implementations (worktree-only behaviour).
# The sourced provider file will override these when a container provider
# is selected.  They are defined here so that callers that source only
# SandboxProvider.sh (without then sourcing a provider file) get safe
# defaults rather than "command not found" errors.
# ---------------------------------------------------------------------------

# sandbox_enter <worktree-path> <command...>
#   Change into the worktree directory and exec the command.
#   No isolation boundary — this is the worktree-only default.
sandbox_enter() {
  local wt="$1"; shift
  (cd "$wt" && exec "$@")
}

# sandbox_exit <session-id>
#   Cleanup hook. No-op for the worktree-only default.
sandbox_exit() {
  return 0
}
