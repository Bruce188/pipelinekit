#!/usr/bin/env bash
# Tests for research-loop.sh sandbox wrapping (_sandbox_wrap helper).
#
# Five test functions covering the dispatch-brief cases a-e:
#   1. test_sandbox_enter_log_format         — SANDBOX_ENTER: line format (AC5, AC10a)
#   2. test_task_id_propagates_iter          — task= field reflects iter arg (AC10b)
#   3. test_default_is_worktree_only         — unset SANDBOX_PROVIDER → worktree-only (AC7, AC10c)
#   4. test_no_sandbox_env_forces_worktree_only — PIPELINE_NO_SANDBOX=1 overrides podman (AC6, AC10d)
#   5. test_wrapped_command_actually_runs    — wrapped command stdout captured (AC9, AC10e)
#
# Uses sourced-helper style: sets RESEARCH_LOOP_NO_RUN=1 before sourcing
# research-loop.sh so the script exposes helper functions without running
# the main loop. Requires Task 1.2 to add the RESEARCH_LOOP_NO_RUN sentinel
# to research-loop.sh. All 5 tests MUST FAIL against unmodified
# research-loop.sh (red gate).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RESEARCH_LOOP="$REPO_ROOT/claude/skills/research/research-loop.sh"
FAILURES=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# ---------------------------------------------------------------------------
# Source research-loop.sh in unit-test mode so _sandbox_wrap and its
# dependencies are available without executing the main loop.
# RESEARCH_LOOP_NO_RUN=1 is the sentinel added by Task 1.2.
# ---------------------------------------------------------------------------
_source_loop() {
  # Reset any prior sandbox state so tests are isolated.
  unset SANDBOX_PROVIDER PIPELINE_NO_SANDBOX __provider 2>/dev/null || true

  RESEARCH_LOOP_NO_RUN=1 . "$RESEARCH_LOOP"
}

# Source once for all tests.
_source_loop

# ---------------------------------------------------------------------------
# test_sandbox_enter_log_format
# Set SANDBOX_PROVIDER unset/empty. Call _sandbox_wrap with a simple command.
# Assert stderr contains exactly the expected SANDBOX_ENTER: line.
# Covers AC5, AC10(a).
# ---------------------------------------------------------------------------
test_sandbox_enter_log_format() {
  local tmpdir
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' RETURN

  # Re-resolve provider with no SANDBOX_PROVIDER set.
  unset SANDBOX_PROVIDER PIPELINE_NO_SANDBOX 2>/dev/null || true
  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$REPO_ROOT/claude/lib/sandbox/providers/${__provider}.sh"
      ;;
  esac

  local stderr_out
  stderr_out=$(
    _sandbox_wrap "research-iter-1" "$(pwd)" /bin/echo hello 2>&1 >/dev/null
  )

  if echo "$stderr_out" | grep -qF "SANDBOX_ENTER: provider=worktree-only, task=research-iter-1, image=none"; then
    pass "test_sandbox_enter_log_format"
  else
    fail "test_sandbox_enter_log_format" \
      "expected 'SANDBOX_ENTER: provider=worktree-only, task=research-iter-1, image=none' in stderr; got: $stderr_out"
  fi
}

# ---------------------------------------------------------------------------
# test_task_id_propagates_iter
# Call _sandbox_wrap with task id "research-iter-7". Assert stderr contains
# "task=research-iter-7". Proves the ${iter} interpolation point.
# Covers AC10(b).
# ---------------------------------------------------------------------------
test_task_id_propagates_iter() {
  unset SANDBOX_PROVIDER PIPELINE_NO_SANDBOX 2>/dev/null || true
  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$REPO_ROOT/claude/lib/sandbox/providers/${__provider}.sh"
      ;;
  esac

  local stderr_out
  stderr_out=$(
    _sandbox_wrap "research-iter-7" "$(pwd)" /bin/true 2>&1 >/dev/null
  )

  if echo "$stderr_out" | grep -qF "task=research-iter-7"; then
    pass "test_task_id_propagates_iter"
  else
    fail "test_task_id_propagates_iter" \
      "expected 'task=research-iter-7' in stderr; got: $stderr_out"
  fi
}

# ---------------------------------------------------------------------------
# test_default_is_worktree_only
# Unset SANDBOX_PROVIDER. Re-run provider_detect. Assert provider=worktree-only
# in SANDBOX_ENTER line.
# Covers AC7, AC10(c).
# ---------------------------------------------------------------------------
test_default_is_worktree_only() {
  unset SANDBOX_PROVIDER PIPELINE_NO_SANDBOX 2>/dev/null || true
  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$REPO_ROOT/claude/lib/sandbox/providers/${__provider}.sh"
      ;;
  esac

  local stderr_out
  stderr_out=$(
    _sandbox_wrap "research-iter-3" "$(pwd)" /bin/true 2>&1 >/dev/null
  )

  if echo "$stderr_out" | grep -qF "provider=worktree-only"; then
    pass "test_default_is_worktree_only"
  else
    fail "test_default_is_worktree_only" \
      "expected 'provider=worktree-only' in stderr; got: $stderr_out"
  fi
}

# ---------------------------------------------------------------------------
# test_no_sandbox_env_forces_worktree_only
# Set PIPELINE_NO_SANDBOX=1 AND SANDBOX_PROVIDER=podman.
# Assert SANDBOX_ENTER still shows provider=worktree-only (escape hatch).
# Covers AC6, AC10(d).
# ---------------------------------------------------------------------------
test_no_sandbox_env_forces_worktree_only() {
  export PIPELINE_NO_SANDBOX=1
  export SANDBOX_PROVIDER=podman

  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$REPO_ROOT/claude/lib/sandbox/providers/${__provider}.sh"
      ;;
  esac

  local stderr_out rc
  rc=0
  stderr_out=$(
    _sandbox_wrap "research-iter-1" "$(pwd)" /bin/true 2>&1 >/dev/null
  ) || rc=$?

  unset PIPELINE_NO_SANDBOX SANDBOX_PROVIDER 2>/dev/null || true

  if echo "$stderr_out" | grep -qF "provider=worktree-only" && [[ "$rc" -eq 0 ]]; then
    pass "test_no_sandbox_env_forces_worktree_only"
  else
    fail "test_no_sandbox_env_forces_worktree_only" \
      "expected provider=worktree-only and exit 0; got rc=$rc stderr: $stderr_out"
  fi
}

# ---------------------------------------------------------------------------
# test_wrapped_command_actually_runs
# Call _sandbox_wrap with /bin/echo "sentinel-payload". Capture stdout.
# Assert stdout contains "sentinel-payload" (envelope does not swallow command).
# Covers AC9, AC10(e).
# ---------------------------------------------------------------------------
test_wrapped_command_actually_runs() {
  unset SANDBOX_PROVIDER PIPELINE_NO_SANDBOX 2>/dev/null || true
  __provider="$(provider_detect)"
  case "$__provider" in
    podman|docker|worktree-only)
      # shellcheck disable=SC1090
      . "$REPO_ROOT/claude/lib/sandbox/providers/${__provider}.sh"
      ;;
  esac

  local out
  out=$(_sandbox_wrap "research-iter-1" "$(pwd)" /bin/echo "sentinel-payload" 2>/dev/null)

  if echo "$out" | grep -qF "sentinel-payload"; then
    pass "test_wrapped_command_actually_runs"
  else
    fail "test_wrapped_command_actually_runs" \
      "expected 'sentinel-payload' in stdout; got: $out"
  fi
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_sandbox_enter_log_format
test_task_id_propagates_iter
test_default_is_worktree_only
test_no_sandbox_env_forces_worktree_only
test_wrapped_command_actually_runs

echo ""
echo "Results: $FAILURES failure(s)"
[[ "$FAILURES" -eq 0 ]]
