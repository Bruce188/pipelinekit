#!/usr/bin/env bash
# Tests for research-loop.sh --restart-from-iter flag.
#
# Three test functions covering the spec's 3 cases:
#   1. test_skip_iters_initializes_counter  — happy path skip iters 1..N-1
#   2. test_restart_from_iter_1_equivalent_to_no_flag — N=1 skips TSV-row check
#   3. test_error_cases — non-int, N>cap, missing TSV row
#
# Uses --dry-run to short-circuit before real claude -p invocations.
# Runs research-loop.sh from a tmp dir so TSV_PATH resolves correctly.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RESEARCH_LOOP="$REPO_ROOT/claude/skills/research/research-loop.sh"
FAILURES=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# TSV header matching the LOCKED constant in research-loop.sh
TSV_HEADER=$'commit\tmetric\tmemory\tstatus\tdescription'

# ---------------------------------------------------------------------------
# test_skip_iters_initializes_counter
# Stage TSV header + 2 data rows. Invoke with --restart-from-iter 3 --dry-run.
# Assert exit 0 + stdout contains "restart-from-iter = 3".
# ---------------------------------------------------------------------------
test_skip_iters_initializes_counter() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp/docs/research-results.tsv"
  printf 'abc123\t1.0\t\tkeep\thypothesis 1\n' >> "$tmp/docs/research-results.tsv"
  printf 'def456\t1.1\t\tkeep\thypothesis 2\n' >> "$tmp/docs/research-results.tsv"

  local out
  out=$(cd "$tmp" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter 3 \
    --dry-run 2>&1) || {
    fail "test_skip_iters_initializes_counter" "exit non-zero, output: $out"
    return
  }

  if echo "$out" | grep -q "restart-from-iter = 3"; then
    pass "test_skip_iters_initializes_counter"
  else
    fail "test_skip_iters_initializes_counter" "stdout missing 'restart-from-iter = 3'; got: $out"
  fi
}

# ---------------------------------------------------------------------------
# test_restart_from_iter_1_equivalent_to_no_flag
# Stage TSV with header only (0 data rows). Invoke with --restart-from-iter 1 --dry-run.
# Assert exit 0 + stdout contains "restart-from-iter = 1".
# No TSV-row check fires when N == 1.
# ---------------------------------------------------------------------------
test_restart_from_iter_1_equivalent_to_no_flag() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp/docs/research-results.tsv"

  local out
  out=$(cd "$tmp" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter 1 \
    --dry-run 2>&1) || {
    fail "test_restart_from_iter_1_equivalent_to_no_flag" "exit non-zero, output: $out"
    return
  }

  if echo "$out" | grep -q "restart-from-iter = 1"; then
    pass "test_restart_from_iter_1_equivalent_to_no_flag"
  else
    fail "test_restart_from_iter_1_equivalent_to_no_flag" "stdout missing 'restart-from-iter = 1'; got: $out"
  fi
}

# ---------------------------------------------------------------------------
# test_error_cases
# Three sub-cases:
#   (a) --restart-from-iter 10 --max-iterations 5 -> exit 2 + stderr "max-iterations"
#   (b) --restart-from-iter 3 with 0 data rows   -> exit 2 + stderr "requires TSV row for iter 2"
#   (c) --restart-from-iter abc                  -> exit 2 + stderr "must be a positive integer"
# ---------------------------------------------------------------------------
test_error_cases() {
  # Sub-case (a): N > max-iterations cap
  local tmp_a
  tmp_a=$(mktemp -d)
  trap 'rm -rf "$tmp_a"' RETURN

  mkdir -p "$tmp_a/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp_a/docs/research-results.tsv"
  printf 'abc123\t1.0\t\tkeep\thypothesis 1\n' >> "$tmp_a/docs/research-results.tsv"
  printf 'def456\t1.1\t\tkeep\thypothesis 2\n' >> "$tmp_a/docs/research-results.tsv"

  local err_a rc_a
  rc_a=0
  err_a=$(cd "$tmp_a" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter 10 \
    --max-iterations 5 \
    --dry-run 2>&1) || rc_a=$?

  if [[ "$rc_a" -eq 2 ]] && echo "$err_a" | grep -q "max-iterations"; then
    pass "test_error_cases (a) N>cap"
  else
    fail "test_error_cases (a) N>cap" "expected exit 2 + 'max-iterations' in stderr; got rc=$rc_a out: $err_a"
  fi

  # Sub-case (b): N=3 but TSV has 0 data rows (only header)
  local tmp_b
  tmp_b=$(mktemp -d)
  trap 'rm -rf "$tmp_b"' RETURN

  mkdir -p "$tmp_b/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp_b/docs/research-results.tsv"

  local err_b rc_b
  rc_b=0
  err_b=$(cd "$tmp_b" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter 3 \
    --dry-run 2>&1) || rc_b=$?

  if [[ "$rc_b" -eq 2 ]] && echo "$err_b" | grep -q "requires TSV row for iter 2"; then
    pass "test_error_cases (b) missing TSV row"
  else
    fail "test_error_cases (b) missing TSV row" "expected exit 2 + 'requires TSV row for iter 2'; got rc=$rc_b out: $err_b"
  fi

  # Sub-case (c): non-integer value
  local tmp_c
  tmp_c=$(mktemp -d)
  trap 'rm -rf "$tmp_c"' RETURN

  mkdir -p "$tmp_c/docs"

  local err_c rc_c
  rc_c=0
  err_c=$(cd "$tmp_c" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter abc \
    --dry-run 2>&1) || rc_c=$?

  if [[ "$rc_c" -eq 2 ]] && echo "$err_c" | grep -q "must be a positive integer"; then
    pass "test_error_cases (c) non-integer"
  else
    fail "test_error_cases (c) non-integer" "expected exit 2 + 'must be a positive integer'; got rc=$rc_c out: $err_c"
  fi
}

# ---------------------------------------------------------------------------
# test_restart_from_iter_zero_accepted_as_off
# Invoke with --restart-from-iter 0 --dry-run.
# The guard short-circuits on "0" (RESTART_FROM_ITER != "0" is false).
# Assert: exit 0, stdout contains "restart-from-iter = 0", no error about
# "must be a positive integer".
# ---------------------------------------------------------------------------
test_restart_from_iter_zero_accepted_as_off() {
  local T="zero_accepted_as_off"
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp/docs/research-results.tsv"

  local out stderr_out rc
  rc=0
  stderr_out=$(mktemp)
  out=$(cd "$tmp" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter 0 \
    --dry-run 2>"$stderr_out") || rc=$?

  local combined="$out$(cat "$stderr_out")"
  rm -f "$stderr_out"

  if [[ "$rc" -ne 0 ]]; then
    fail "$T" "exit non-zero ($rc), output: $combined"
    return
  fi

  if echo "$combined" | grep -q "must be a positive integer"; then
    fail "$T" "unexpected validation error; output: $combined"
    return
  fi

  if echo "$out" | grep -q "restart-from-iter = 0"; then
    pass "$T"
  else
    fail "$T" "stdout missing 'restart-from-iter = 0'; got: $out"
  fi
}

# ---------------------------------------------------------------------------
# test_restart_from_iter_empty_string_accepted_as_off
# Invoke with --restart-from-iter "" --dry-run.
# The guard short-circuits on empty string (-n "" is false).
# Assert: exit 0, the run proceeds, no validation-error line in stderr.
# ---------------------------------------------------------------------------
test_restart_from_iter_empty_string_accepted_as_off() {
  local T="empty_string_accepted_as_off"
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/docs"
  printf '%s\n' "$TSV_HEADER" > "$tmp/docs/research-results.tsv"

  local out stderr_out rc
  rc=0
  stderr_out=$(mktemp)
  out=$(cd "$tmp" && bash "$RESEARCH_LOOP" \
    --goal "test goal" \
    --target-file "src/x.py" \
    --benchmark-cmd "echo bench" \
    --metric-regex "metric=([0-9.]+)" \
    --restart-from-iter "" \
    --dry-run 2>"$stderr_out") || rc=$?

  local stderr_content
  stderr_content=$(cat "$stderr_out")
  rm -f "$stderr_out"

  if [[ "$rc" -ne 0 ]]; then
    fail "$T" "exit non-zero ($rc), stderr: $stderr_content"
    return
  fi

  if echo "$stderr_content" | grep -q "must be a positive integer"; then
    fail "$T" "unexpected validation error; stderr: $stderr_content"
    return
  fi

  if echo "$out" | grep -q "DRY-RUN"; then
    pass "$T"
  else
    fail "$T" "dry-run did not proceed; got: $out"
  fi
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
test_skip_iters_initializes_counter
test_restart_from_iter_1_equivalent_to_no_flag
test_error_cases
test_restart_from_iter_zero_accepted_as_off
test_restart_from_iter_empty_string_accepted_as_off

echo ""
echo "Results: $FAILURES failure(s)"
[[ "$FAILURES" -eq 0 ]]
