#!/usr/bin/env bash
# claude/lib/sandbox/sandbox_wrap.sh — Shared sandbox envelope helper.
#
# Exposes two names to callers:
#   sandbox_wrap  <task-id> <worktree> <command...>   (primary)
#   _sandbox_wrap <task-id> <worktree> <command...>   (alias — preserves the
#       underscore-prefix contract used by research-loop.sh and its tests)
#
# This file is SOURCED, never executed directly. It sources SandboxProvider.sh
# at source time (idempotent — function redefinitions are harmless) so that
# provider_detect is available when sandbox_wrap is called.
#
# No set -euo pipefail at file scope: callers set their own pipefail flags;
# a sourced lib must not override the caller's shell flags.
#
# Internal variables (LIB_DIR, __provider, image, rc) are declared local
# inside sandbox_wrap so that no file-scope globals leak into the caller's
# shell environment.

# Resolve this file's directory once at source time, then unset.
_SW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=SandboxProvider.sh
. "$_SW_DIR/SandboxProvider.sh"
unset _SW_DIR

# ---------------------------------------------------------------------------
# sandbox_wrap <task-id> <worktree> <command...>
#
# Public wrap helper: emits the SANDBOX_ENTER log line, calls sandbox_enter,
# captures the exit code, then calls sandbox_exit. All formerly file-scope
# variables (LIB_DIR, __provider, image, rc) are local to this function so
# that sourcing sandbox_wrap.sh leaves no global side-effects.
#
# SANDBOX_ENTER log line format (byte-identical to the pre-extraction copies):
#   SANDBOX_ENTER: provider=<X>, task=<task-id>, image=<image>
# Where <image> is resolved via:
#   SANDBOX_PODMAN_IMAGE → SANDBOX_DOCKER_IMAGE → PIPELINEKIT_SANDBOX_TAG
# or the literal "none" when the resolved provider is worktree-only.
# ---------------------------------------------------------------------------
sandbox_wrap() {
  local task_id="${1:?task id required}"
  local worktree="${2:?worktree path required}"
  shift 2
  local LIB_DIR
  LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local __provider
  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$LIB_DIR/providers/${__provider}.sh"
      ;;
    *)
      echo "sandbox_wrap: unknown provider '$__provider'" >&2
      return 2
      ;;
  esac
  local image
  if [ "$__provider" = "worktree-only" ]; then
    image="none"
  else
    image="${SANDBOX_PODMAN_IMAGE:-${SANDBOX_DOCKER_IMAGE:-${PIPELINEKIT_SANDBOX_TAG:-none}}}"
  fi
  echo "SANDBOX_ENTER: provider=$__provider, task=$task_id, image=$image" >&2
  sandbox_enter "$worktree" "$@"
  local rc=$?
  sandbox_exit "$task_id" || true
  return "$rc"
}

# Underscore alias — preserves the _sandbox_wrap call convention used by
# research-loop.sh (line 537) and its test suite (test_research_loop_sandboxing.sh).
_sandbox_wrap() { sandbox_wrap "$@"; }
