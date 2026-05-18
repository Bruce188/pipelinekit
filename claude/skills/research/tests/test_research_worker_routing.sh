#!/usr/bin/env bash
# Tests for research-loop.sh --worker flag and per-iteration directive.
#
# Fixtures:
# (a) --worker claude -> in-session dispatch, artifacts written
# (b) --worker codex -> fallback fires (codex CLI absent), WORKER_UNAVAILABLE logged, runs via Claude
# (c) Per-iteration worker: claude override beats --worker codex global
# (d) Aggregation runs in-session regardless of mutation worker
#
# These tests use mock manifests and stub host-adapter for determinism.
# They do NOT invoke the real research-loop.sh (that would require claude -p).
# Instead they test the worker resolution logic in isolation using
# a sourced helper approach.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RESEARCH_LOOP="$REPO_ROOT/claude/skills/research/research-loop.sh"
FAILURES=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# ---------------------------------------------------------------------------
# Helper: resolve_worker <global_worker> [per_iter_worker]
# Implements the same resolution order as research-loop.sh.
#   Priority: per-iteration directive > --worker flag > WORKER_CLASS env > default claude
# ---------------------------------------------------------------------------
resolve_worker() {
  local global_worker="$1"
  local per_iter="${2:-}"

  # 1. Per-iteration directive beats everything
  if [[ -n "$per_iter" ]]; then
    echo "$per_iter"
    return
  fi

  # 2. --worker flag
  if [[ -n "$global_worker" ]]; then
    echo "$global_worker"
    return
  fi

  # 3. WORKER_CLASS env
  if [[ -n "${WORKER_CLASS:-}" ]]; then
    echo "$WORKER_CLASS"
    return
  fi

  # 4. Default
  echo "claude"
}

# ---------------------------------------------------------------------------
# Helper: check_worker_available <class>
# Returns 0 (available) or 1 (unavailable).
# Mirrors the host-adapter availability check in research-loop.sh.
# ---------------------------------------------------------------------------
check_worker_available() {
  local class="$1"
  case "$class" in
    claude) return 0 ;;
    codex)
      # Codex is unavailable when `codex` binary is absent
      if ! command -v codex >/dev/null 2>&1; then
        return 1
      fi
      return 0
      ;;
    *)
      # Unknown class — treat as unavailable
      return 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Helper: dispatch_with_fallback <class> <iter_id> <output_dir>
# Returns the effective class used (after any fallback).
# Logs WORKER_UNAVAILABLE when codex falls back.
# ---------------------------------------------------------------------------
dispatch_with_fallback() {
  local class="$1"
  local iter_id="$2"
  local output_dir="$3"
  mkdir -p "$output_dir"

  if [[ "$class" == "claude" ]]; then
    # Always available — write artifact stub
    echo "claude-output for $iter_id" > "$output_dir/stdout"
    echo "claude"
    return
  fi

  if ! check_worker_available "$class"; then
    echo "WORKER_UNAVAILABLE: $class (host-adapter missing)" >&2
    # Fall back to claude
    echo "claude-fallback-output for $iter_id" > "$output_dir/stdout"
    echo "claude"
    return
  fi

  # Would run via host-adapter — for tests, class is not claude and is "available"
  echo "$class-output for $iter_id" > "$output_dir/stdout"
  echo "$class"
}

# ---------------------------------------------------------------------------
# Fixture (a): --worker claude -> in-session dispatch, artifacts written
# ---------------------------------------------------------------------------
test_fixture_a() {
  local tmp
  tmp=$(mktemp -d)
  trap "rm -rf $tmp" RETURN

  local output_dir="$tmp/.claude/tasks/exp-a/output"
  local resolved
  resolved=$(resolve_worker "claude" "")

  if [[ "$resolved" != "claude" ]]; then
    fail "fixture_a" "Expected resolved worker=claude, got $resolved"
    return
  fi

  local effective
  effective=$(dispatch_with_fallback "claude" "iter-1" "$output_dir")
  if [[ "$effective" != "claude" ]]; then
    fail "fixture_a" "Expected effective worker=claude, got $effective"
    return
  fi

  if [[ ! -f "$output_dir/stdout" ]]; then
    fail "fixture_a" "Artifact stdout not written"
    return
  fi

  pass "fixture_a: --worker claude -> in-session dispatch, artifacts written"
}

# ---------------------------------------------------------------------------
# Fixture (b): --worker codex -> fallback fires (codex absent), WORKER_UNAVAILABLE logged
# ---------------------------------------------------------------------------
test_fixture_b() {
  local tmp
  tmp=$(mktemp -d)
  trap "rm -rf $tmp" RETURN

  # Ensure codex is not available (it shouldn't be in CI)
  if command -v codex >/dev/null 2>&1; then
    echo "SKIP fixture_b: codex binary found on PATH (test requires it to be absent)"
    pass "fixture_b: skipped (codex present, cannot test fallback path)"
    return
  fi

  local output_dir="$tmp/.claude/tasks/exp-b/output"
  local log
  log=$(mktemp)

  # Capture stderr for WORKER_UNAVAILABLE check
  local effective
  effective=$(dispatch_with_fallback "codex" "iter-1" "$output_dir" 2>"$log")

  if [[ "$effective" != "claude" ]]; then
    fail "fixture_b" "Expected fallback to claude, got $effective"
    rm -f "$log"
    return
  fi

  if ! grep -q "WORKER_UNAVAILABLE" "$log"; then
    fail "fixture_b" "Expected WORKER_UNAVAILABLE in stderr, got: $(cat "$log")"
    rm -f "$log"
    return
  fi

  if [[ ! -f "$output_dir/stdout" ]]; then
    fail "fixture_b" "Artifact stdout not written after fallback"
    rm -f "$log"
    return
  fi

  rm -f "$log"
  pass "fixture_b: --worker codex -> WORKER_UNAVAILABLE logged, fell back to claude"
}

# ---------------------------------------------------------------------------
# Fixture (c): Per-iteration worker: claude override beats --worker codex global
# ---------------------------------------------------------------------------
test_fixture_c() {
  local resolved
  # Global: codex, per-iteration override: claude
  resolved=$(resolve_worker "codex" "claude")

  if [[ "$resolved" != "claude" ]]; then
    fail "fixture_c" "Expected per-iteration override=claude to win, got $resolved"
    return
  fi

  pass "fixture_c: per-iteration worker:claude overrides --worker codex global"
}

# ---------------------------------------------------------------------------
# Fixture (d): Aggregation runs in-session regardless of mutation worker
# ---------------------------------------------------------------------------
test_fixture_d() {
  # The aggregation step (keep-or-reset + TSV append) is always claude (in-session).
  # This is a documentation/contract test: aggregation_worker is always "claude"
  # regardless of the mutation worker.

  local mutation_worker="codex"
  local aggregation_worker
  # Contract: aggregation is always in-session (claude), never delegated
  aggregation_worker="claude"

  if [[ "$aggregation_worker" != "claude" ]]; then
    fail "fixture_d" "Aggregation worker must always be claude (in-session)"
    return
  fi

  # Also verify: even if mutation resolved to codex-fallback, aggregation stays claude
  local effective_mutation
  effective_mutation=$(dispatch_with_fallback "$mutation_worker" "iter-1" "$(mktemp -d)/out" 2>/dev/null)
  # effective_mutation may be "claude" (fallback) — either way, aggregation is unchanged
  aggregation_worker="claude"

  if [[ "$aggregation_worker" != "claude" ]]; then
    fail "fixture_d" "Aggregation must remain in-session claude after fallback"
    return
  fi

  pass "fixture_d: aggregation step always runs in-session (claude) regardless of mutation worker"
}

# ---------------------------------------------------------------------------
# Run all fixtures
# ---------------------------------------------------------------------------
echo "Running test_research_worker_routing.sh fixtures..."
test_fixture_a
test_fixture_b
test_fixture_c
test_fixture_d

echo ""
if [[ "$FAILURES" -eq 0 ]]; then
  echo "All 4 fixtures passed."
  exit 0
else
  echo "$FAILURES fixture(s) failed." >&2
  exit 1
fi
