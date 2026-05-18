#!/usr/bin/env bash
# claude/skills/pipeline/orchestrate.sh — OPTIONAL out-of-process pipeline driver.
#
# Status: optional fork extension. The canonical entry point for /pipeline is
# the in-process Skill (`~/.claude/skills/pipeline/SKILL.md`). This subprocess
# driver exists for unattended runs outside an interactive Claude Code session
# — e.g., long-running CI cron, scheduled batch processing, or operators who
# need maximum context isolation between phases.
#
# Public interface:
#   run_phase <phase-name> <prompt-file> <worktree-path>
#     — Reads the prompt from <prompt-file>, wraps a `claude -p` invocation in
#       sandbox_enter / sandbox_exit, and dispatches it inside the sandbox
#       provider selected by claude/lib/sandbox/SandboxProvider.sh.
#
# Per-phase prompt templates live in:
#   ~/.claude/skills/pipeline/reference.md
# Each phase (analyze, plan, implement, review) has its own template block; a
# subprocess driver that re-implements the full pipeline must honor that
# contract.
#
# Constraints:
#   - Charter Discovery (Step 0) CANNOT run under a subprocess driver because
#     `AskUserQuestion` is interactive-session-only. For unattended runs, pass
#     `--no-charter` to the pipeline invocation that produced the prompt files.
#   - This stub demonstrates the wrapping contract for a SINGLE phase. A full
#     driver would iterate over phases and features, persist pipeline-state.md
#     between phases, and handle Path A/B/C transitions per the SKILL.md
#     contract.

set -uo pipefail

# Resolve paths relative to this file so the stub works whether sourced from
# the repo root, an absolute path, or a `claude/` overlay.
ORCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
LIB_DIR="$(cd "$ORCH_DIR/../../lib/sandbox" && pwd)"

# shellcheck source=../../lib/sandbox/SandboxProvider.sh
. "$LIB_DIR/SandboxProvider.sh"

# Resolve and source the selected provider so sandbox_enter / sandbox_exit
# come from the active backend (podman.sh / docker.sh / worktree-only.sh).
__provider="$(provider_detect)"
case "$__provider" in
  podman|docker|worktree-only)
    # shellcheck disable=SC1090
    . "$LIB_DIR/providers/${__provider}.sh"
    ;;
  *)
    echo "orchestrate.sh: unknown provider '$__provider'" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# run_phase <phase-name> <prompt-file> <worktree-path>
#
# Reads a phase prompt from <prompt-file> and dispatches `claude -p` inside
# the sandbox provider. The phase name is informational (logged to stderr);
# the actual phase routing is determined by the prompt content.
#
# Arguments:
#   $1 — phase name (e.g., analyze | plan | implement | review)
#   $2 — path to a file containing the phase prompt
#   $3 — absolute path to the worktree to enter
#
# Exit code: forwarded from `claude -p` after sandbox_exit runs.
# ---------------------------------------------------------------------------
run_phase() {
  local phase="${1:?phase name required}"
  local prompt_file="${2:?prompt file path required}"
  local worktree="${3:?worktree path required}"
  local prompt rc

  if [ ! -f "$prompt_file" ]; then
    echo "orchestrate.sh: prompt file not found: $prompt_file" >&2
    return 1
  fi
  if [ ! -d "$worktree" ]; then
    echo "orchestrate.sh: worktree not found: $worktree" >&2
    return 1
  fi

  prompt="$(cat "$prompt_file")"
  echo "orchestrate.sh: phase=$phase provider=$__provider worktree=$worktree" >&2

  sandbox_enter "$worktree" claude -p "$prompt"
  rc=$?
  sandbox_exit "$phase-$$" || true
  return "$rc"
}

# When invoked directly with --help, print usage and exit. When sourced, this
# block is skipped so callers can use run_phase as a library function.
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  case "${1:-}" in
    --help|-h|help|"")
      cat <<'USAGE'
orchestrate.sh — OPTIONAL out-of-process pipeline driver (stub).

Usage (as a library):
  source claude/skills/pipeline/orchestrate.sh
  run_phase analyze prompt.txt /path/to/worktree

Usage (directly):
  claude/skills/pipeline/orchestrate.sh run_phase <phase> <prompt-file> <worktree>

Environment:
  SANDBOX_PROVIDER     auto|podman|docker|worktree-only (default: auto)
  PIPELINE_NO_SANDBOX  1 → short-circuit to worktree-only

Constraints:
  - Charter Discovery (Step 0) cannot run under a subprocess driver;
    pass --no-charter when generating phase prompts for unattended runs.
  - This is a stub. A full driver must iterate phases + features per the
    contract in ~/.claude/skills/pipeline/reference.md.
USAGE
      ;;
    run_phase)
      shift
      run_phase "$@"
      ;;
    *)
      echo "orchestrate.sh: unknown command '$1' (try --help)" >&2
      exit 2
      ;;
  esac
fi
