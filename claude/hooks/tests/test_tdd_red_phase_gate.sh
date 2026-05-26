#!/usr/bin/env bash
# test_tdd_red_phase_gate.sh — smoke test for tdd-red-phase-gate.sh.
#
# ACs:
#   1. Non-Bash tool call exits 0 silently.
#   2. Bash command without `git commit` exits 0 silently.
#   3. Missing docs/progress.md → exits 0 silently (no warning).
#   4. Progress.md with `doing` task **Testable:** yes AND no `test:` commit in
#      window → emits WARNING on stderr (still exits 0 — advisory).
#   5. Same fixture but with `test:` commit in window → no warning, exits 0.
#
# Scratch git repo built fresh; trap cleans on exit.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../tdd-red-phase-gate.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-tdd-red-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Build the scratch repo with a docs/progress.md + prompts file.
REPO="$SANDBOX/repo"
mkdir -p "$REPO/docs"
(
  cd "$REPO"
  git init -b main >/dev/null 2>&1
  git config user.email "t@t.test"
  git config user.name "test"
  git commit --allow-empty -m "init: empty" >/dev/null 2>&1
  git checkout -b feature/x >/dev/null 2>&1
) || { echo "FAIL: scratch repo init"; exit 1; }

cat > "$REPO/docs/progress.md" <<'PROG'
**Plan:** docs/plan.md
**Prompts:** docs/prompts.md

| Task | Name | Status | Notes |
|------|------|--------|-------|
| 1.1  | sample | doing | x |
PROG

cat > "$REPO/docs/prompts.md" <<'PROMPTS'
### Task 1.1: sample

**Testable:** yes

Body.
PROMPTS

call_hook_in_repo() {
  local payload="$1"
  ( cd "$REPO" && printf '%s' "$payload" | bash "$HOOK" )
}

# ─── AC1: non-Bash tool → silent exit 0 ───────────────────────────────────────
EXIT=0
PAYLOAD='{"tool_name":"Read","tool_input":{"file_path":"x.txt"}}'
STDERR=$(call_hook_in_repo "$PAYLOAD" 2>&1 >/dev/null) || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDERR" ]; then
  pass "AC1_non_bash_silent"
else
  fail "AC1_non_bash_silent" "exit=$EXIT stderr=$STDERR"
fi

# ─── AC2: Bash but not git commit → silent ────────────────────────────────────
EXIT=0
PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"ls -la"}}'
STDERR=$(call_hook_in_repo "$PAYLOAD" 2>&1 >/dev/null) || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDERR" ]; then
  pass "AC2_bash_non_commit_silent"
else
  fail "AC2_bash_non_commit_silent" "exit=$EXIT stderr=$STDERR"
fi

# ─── AC4: testable:yes + no test: commit → WARNING emitted ────────────────────
# Note we test AC4 before AC5 so we don't mutate fixture upward.
EXIT=0
PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"git commit -m feat:x"}}'
STDERR=$(call_hook_in_repo "$PAYLOAD" 2>&1 >/dev/null) || EXIT=$?
if [ "$EXIT" -eq 0 ] && echo "$STDERR" | grep -q "WARNING: TDD red-phase gate"; then
  pass "AC4_warning_on_missing_test_commit"
else
  fail "AC4_warning_on_missing_test_commit" "exit=$EXIT stderr=$STDERR"
fi

# ─── AC5: same fixture + a test: commit on this branch → no warning ────────────
(
  cd "$REPO" || exit
  git commit --allow-empty -m "test: add red phase for 1.1" >/dev/null 2>&1
)
EXIT=0
STDERR=$(call_hook_in_repo "$PAYLOAD" 2>&1 >/dev/null) || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDERR" ]; then
  pass "AC5_no_warning_when_test_commit_present"
else
  fail "AC5_no_warning_when_test_commit_present" "exit=$EXIT stderr=$STDERR"
fi

# ─── AC3: missing progress.md → silent ────────────────────────────────────────
rm "$REPO/docs/progress.md"
EXIT=0
STDERR=$(call_hook_in_repo "$PAYLOAD" 2>&1 >/dev/null) || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDERR" ]; then
  pass "AC3_missing_progress_silent"
else
  fail "AC3_missing_progress_silent" "exit=$EXIT stderr=$STDERR"
fi

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
