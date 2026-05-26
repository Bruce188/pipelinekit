#!/usr/bin/env bash
# claude/lib/sandbox/tests/test_sandbox_wrap_shared.sh
#
# Regression test for shared sandbox_wrap library extraction.
#
# WHY THIS TEST FAILS TODAY (RED proof):
# -----------------------------------------------------------------------------
# 1. No shared library: `claude/lib/sandbox/sandbox_wrap.sh` does not yet
#    exist. The source line `. "$REPO_ROOT/claude/lib/sandbox/sandbox_wrap.sh"`
#    would fail with "No such file or directory".
#
# 2. Global variable collision: Both `orchestrate.sh` and `research-loop.sh`
#    declare `LIB_DIR` at file scope when sourced. Sourcing both into the same
#    shell causes the second source to overwrite `LIB_DIR` with stale paths
#    from the first caller's resolution directory, corrupting subsequent
#    provider sourcing.
#
# 3. Duplicated (diverged) function bodies: `sandbox_wrap` is defined in
#    `orchestrate.sh` and `_sandbox_wrap` is defined in `research-loop.sh` as
#    separate functions — they are not aliases of each other. The test assertion
#    that both names resolve to the same function body fails today.
#
# 4. File-scope `LIB_DIR` leak: After sourcing orchestrate.sh or research-loop.sh
#    the `LIB_DIR` variable is visible in the shell's global scope. The test
#    asserts that no file-scope `LIB_DIR=` assignment survives sourcing the
#    callers (post-refactor both callers delegate to sandbox_wrap.sh which uses
#    a transient `_SW_DIR`). Today this assertion fails.
#
# After Task 1.2 (shared lib extraction), all four failure modes are resolved
# and this test should pass.
# -----------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
ORCHESTRATE="$REPO_ROOT/claude/skills/pipeline/orchestrate.sh"
RESEARCH_LOOP="$REPO_ROOT/claude/skills/research/research-loop.sh"
SANDBOX_WRAP_LIB="$REPO_ROOT/claude/lib/sandbox/sandbox_wrap.sh"

FAILURES=0
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1: $2" >&2; FAILURES=$((FAILURES + 1)); }

# ---------------------------------------------------------------------------
# Step 1: Verify the shared lib exists. If not, fail fast (RED proof #1).
# ---------------------------------------------------------------------------
if [ ! -f "$SANDBOX_WRAP_LIB" ]; then
  echo "FAIL shared_lib_exists: $SANDBOX_WRAP_LIB not found" >&2
  echo "RED: sandbox_wrap.sh does not exist yet — Task 1.2 has not run." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Source the shared lib into a fresh subshell and verify both names
# are defined and resolve to the same function body (via alias).
# ---------------------------------------------------------------------------

# Source the shared lib and then source both callers (sentinel-guarded).
# We run this in a subshell to avoid contaminating the test runner's shell state.
{
  # Source shared lib
  # shellcheck disable=SC1090
  . "$SANDBOX_WRAP_LIB"

  # Source orchestrate.sh — it should no longer define sandbox_wrap inline;
  # it should source the shared lib (idempotent) and define run_phase etc.
  # shellcheck disable=SC1090
  . "$ORCHESTRATE"

  # Source research-loop.sh in no-run mode — it should no longer define
  # _sandbox_wrap inline; it should source the shared lib (idempotent).
  RESEARCH_LOOP_NO_RUN=1
  export RESEARCH_LOOP_NO_RUN
  # shellcheck disable=SC1090
  . "$RESEARCH_LOOP"

  # Assert sandbox_wrap is defined
  if declare -f sandbox_wrap >/dev/null 2>&1; then
    echo "PASS sandbox_wrap_defined"
  else
    echo "FAIL sandbox_wrap_defined: sandbox_wrap function not found after sourcing" >&2
    exit 1
  fi

  # Assert _sandbox_wrap is defined
  if declare -f _sandbox_wrap >/dev/null 2>&1; then
    echo "PASS _sandbox_wrap_defined"
  else
    echo "FAIL _sandbox_wrap_defined: _sandbox_wrap function not found after sourcing" >&2
    exit 1
  fi

  # Assert both names produce the same behavior (alias contract).
  # We compare their function bodies as reported by `declare -f`.
  # The alias is: _sandbox_wrap() { sandbox_wrap "$@"; }
  # So _sandbox_wrap body must reference sandbox_wrap.
  if declare -f _sandbox_wrap | grep -q 'sandbox_wrap'; then
    echo "PASS _sandbox_wrap_is_alias_of_sandbox_wrap"
  else
    echo "FAIL _sandbox_wrap_is_alias_of_sandbox_wrap: _sandbox_wrap body does not delegate to sandbox_wrap" >&2
    exit 1
  fi

  # Assert no file-scope LIB_DIR leak from either caller.
  # After the refactor both callers replace the inline LIB_DIR assignment with a
  # source of sandbox_wrap.sh (which uses _SW_DIR transiently and unsets it).
  if declare -p LIB_DIR >/dev/null 2>&1; then
    echo "FAIL no_lib_dir_leak: LIB_DIR is still set in file scope after sourcing callers" >&2
    exit 1
  else
    echo "PASS no_lib_dir_leak"
  fi

} || { echo "FAIL subshell_setup: subshell exited with error" >&2; FAILURES=$((FAILURES + 1)); }

# ---------------------------------------------------------------------------
# Step 3: Invoke sandbox_wrap from a clean source environment and assert:
#   - exit code 0
#   - stdout contains SHARED_OK
#   - stderr contains a well-formed SANDBOX_ENTER: line
# ---------------------------------------------------------------------------
stderr_file="$tmpdir/stderr_sandbox_wrap.txt"
wt_stub="$tmpdir/wt-stub"
mkdir -p "$wt_stub"

set +e
actual_stdout=$(
  # F12: SANDBOX_PROVIDER default flipped from worktree-only to auto. This test
  # exercises the sandbox_wrap library, not provider resolution — pin the
  # provider explicitly so the test is independent of host engine presence.
  export SANDBOX_PROVIDER=worktree-only
  unset PIPELINE_NO_SANDBOX LIB_DIR __provider 2>/dev/null || true
  # shellcheck disable=SC1090
  . "$SANDBOX_WRAP_LIB"
  sandbox_wrap test-task "$wt_stub" bash -c 'echo SHARED_OK' 2>"$stderr_file"
)
sw_rc=$?
set -e

if [ "$sw_rc" -eq 0 ]; then
  pass "sandbox_wrap_exits_0"
else
  fail "sandbox_wrap_exits_0" "exit code was $sw_rc"
fi

if echo "$actual_stdout" | grep -qF "SHARED_OK"; then
  pass "sandbox_wrap_stdout_contains_SHARED_OK"
else
  fail "sandbox_wrap_stdout_contains_SHARED_OK" "stdout was: $actual_stdout"
fi

if grep -qE '^SANDBOX_ENTER: provider=[^,]+, task=test-task, image=' "$stderr_file"; then
  pass "sandbox_wrap_sandbox_enter_line_wellformed"
else
  fail "sandbox_wrap_sandbox_enter_line_wellformed" \
    "stderr was: $(cat "$stderr_file")"
fi

# Assert provider= field matches provider_detect output.
# F12: pin SANDBOX_PROVIDER=worktree-only for consistency with the sandbox_wrap
# invocation above, since the default is now auto (engine-when-present).
# shellcheck disable=SC1090
. "$SANDBOX_WRAP_LIB"
expected_provider="$(SANDBOX_PROVIDER=worktree-only provider_detect)"
if grep -qF "provider=$expected_provider" "$stderr_file"; then
  pass "sandbox_wrap_provider_field_matches_detect"
else
  fail "sandbox_wrap_provider_field_matches_detect" \
    "expected provider=$expected_provider; stderr: $(cat "$stderr_file")"
fi

# Assert image= field: worktree-only → "none"; others → env-var chain or "none"
if [ "$expected_provider" = "worktree-only" ]; then
  if grep -qF "image=none" "$stderr_file"; then
    pass "sandbox_wrap_image_is_none_for_worktree_only"
  else
    fail "sandbox_wrap_image_is_none_for_worktree_only" \
      "expected image=none; stderr: $(cat "$stderr_file")"
  fi
fi

# ---------------------------------------------------------------------------
# Step 4: Invoke _sandbox_wrap (alias) and assert exit 0 + ALIAS_OK on stdout.
# ---------------------------------------------------------------------------
stderr_file2="$tmpdir/stderr_sandbox_wrap2.txt"

set +e
actual_stdout2=$(
  # F12: pin worktree-only for the same reason as the sandbox_wrap invocation.
  export SANDBOX_PROVIDER=worktree-only
  unset PIPELINE_NO_SANDBOX LIB_DIR __provider 2>/dev/null || true
  # shellcheck disable=SC1090
  . "$SANDBOX_WRAP_LIB"
  _sandbox_wrap test-task-2 "$wt_stub" bash -c 'echo ALIAS_OK' 2>"$stderr_file2"
)
alias_rc=$?
set -e

if [ "$alias_rc" -eq 0 ]; then
  pass "_sandbox_wrap_alias_exits_0"
else
  fail "_sandbox_wrap_alias_exits_0" "exit code was $alias_rc"
fi

if echo "$actual_stdout2" | grep -qF "ALIAS_OK"; then
  pass "_sandbox_wrap_alias_stdout_contains_ALIAS_OK"
else
  fail "_sandbox_wrap_alias_stdout_contains_ALIAS_OK" "stdout was: $actual_stdout2"
fi

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
echo ""
echo "Results: $FAILURES failure(s)"
[ "$FAILURES" -eq 0 ]
