#!/usr/bin/env bash
# test_block_push_main.sh — smoke test for block-push-main.sh.
#
# ACs:
#   1. `git push origin main` blocks with exit 2.
#   2. `git push origin HEAD:main` blocks with exit 2.
#   3. `git push --force origin main` blocks with exit 2.
#   4. `git push origin master` blocks with exit 2.
#   5. `git push origin feature/x` allows with exit 0.
#   6. `git push -u origin main` blocks with exit 2.
#   7. Non-push command (`git status`) allows silently.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../block-push-main.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-block-push-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

call_hook() {
  local cmd="$1"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'command': sys.argv[1]}}))" "$cmd")
  HOME="$SANDBOX" printf '%s' "$payload" | bash "$HOOK" 2>/dev/null
}

# ─── AC1: push origin main → block ────────────────────────────────────────────
EXIT=0
call_hook "git push origin main" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC1_push_origin_main_blocked"
else
  fail "AC1_push_origin_main_blocked" "expected exit 2, got $EXIT"
fi

# ─── AC2: push HEAD:main → block ──────────────────────────────────────────────
EXIT=0
call_hook "git push origin HEAD:main" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC2_push_HEAD_main_blocked"
else
  fail "AC2_push_HEAD_main_blocked" "expected exit 2, got $EXIT"
fi

# ─── AC3: push --force origin main → block ────────────────────────────────────
EXIT=0
call_hook "git push --force origin main" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC3_push_force_main_blocked"
else
  fail "AC3_push_force_main_blocked" "expected exit 2, got $EXIT"
fi

# ─── AC4: push origin master → block ──────────────────────────────────────────
EXIT=0
call_hook "git push origin master" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC4_push_origin_master_blocked"
else
  fail "AC4_push_origin_master_blocked" "expected exit 2, got $EXIT"
fi

# ─── AC5: push origin feature/x → allow ───────────────────────────────────────
EXIT=0
call_hook "git push origin feature/x" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  pass "AC5_push_feature_branch_allowed"
else
  fail "AC5_push_feature_branch_allowed" "expected exit 0, got $EXIT"
fi

# ─── AC6: push -u origin main → block ─────────────────────────────────────────
EXIT=0
call_hook "git push -u origin main" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC6_push_dash_u_main_blocked"
else
  fail "AC6_push_dash_u_main_blocked" "expected exit 2, got $EXIT"
fi

# ─── AC7: non-push command → allow ────────────────────────────────────────────
EXIT=0
call_hook "git status" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  pass "AC7_git_status_allowed"
else
  fail "AC7_git_status_allowed" "expected exit 0, got $EXIT"
fi

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
