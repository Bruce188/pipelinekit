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

# Source the shared sandbox_wrap library (provides sandbox_wrap + _sandbox_wrap
# + all provider infrastructure). Replaces the former inline LIB_DIR / provider
# sourcing block and inline sandbox_wrap() definition.
# shellcheck source=../../lib/sandbox/sandbox_wrap.sh
. "$ORCH_DIR/../../lib/sandbox/sandbox_wrap.sh"

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
  echo "orchestrate.sh: phase=$phase provider=$(provider_detect) worktree=$worktree" >&2

  sandbox_wrap "$phase-$$" "$worktree" claude -p "$prompt"
  rc=$?
  return "$rc"
}

# ---------------------------------------------------------------------------
# run_host_adapter <host> <worktree> <prompt-file> <output-file> [args...]
#
# Resolves claude/host-adapters/<host>.sh relative to this stub, validates
# presence (stderr error + exit 2 if missing), and wraps the adapter
# invocation in sandbox_wrap. The adapter contract is documented in
# claude/host-adapters/README.md.
#
# Exit codes:
#   2 — host adapter file not found
#   1 — worktree directory not found
#   * — forwarded from the adapter
# ---------------------------------------------------------------------------
run_host_adapter() {
  local host="${1:?host name required}"
  local worktree="${2:?worktree path required}"
  local prompt_file="${3:?prompt file required}"
  local output_file="${4:?output file required}"
  shift 4
  local adapter_path="$ORCH_DIR/../../host-adapters/${host}.sh"
  if [ ! -f "$adapter_path" ]; then
    echo "orchestrate.sh: host adapter not found: $adapter_path" >&2
    return 2
  fi
  if [ ! -d "$worktree" ]; then
    echo "orchestrate.sh: worktree not found: $worktree" >&2
    return 1
  fi
  sandbox_wrap "host:${host}:$$" "$worktree" \
    "$adapter_path" "$prompt_file" "$output_file" "$@"
}

# ---------------------------------------------------------------------------
# run_mcp <server-name> <worktree> <command...>
#
# Wraps an MCP-server launch in sandbox_wrap. SCAFFOLDING ONLY — no
# pipelinekit consumer ships using this helper today; MCP servers are
# launched by the Claude Code host. Forks that spawn MCP servers from a
# subprocess driver should use this entry point.
#
# Exit codes:
#   1 — worktree directory not found
#   * — forwarded from the wrapped command
# ---------------------------------------------------------------------------
run_mcp() {
  local server="${1:?server name required}"
  local worktree="${2:?worktree path required}"
  shift 2
  if [ ! -d "$worktree" ]; then
    echo "orchestrate.sh: worktree not found: $worktree" >&2
    return 1
  fi
  sandbox_wrap "mcp:${server}:$$" "$worktree" "$@"
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
