#!/usr/bin/env bash
# test_block_dangerous_commands.sh — smoke test for block-dangerous-commands.sh.
#
# ACs:
#   1. `git remote add upstream <url>` blocks with exit 2.
#   2. `git config --global user.email x@y.z` blocks with exit 2.
#   3. `docker run --privileged ubuntu` emits ASK JSON on stdout, exits 0.
#   4. `git reset --hard HEAD~5` emits ASK JSON on stdout, exits 0.
#   5. `git branch -D feature/x` hard blocks with exit 2.
#   6. `ls -la` allows with exit 0 (irrelevant command).
#   7. `git status` allows with exit 0.
#
# Sandboxes HOME so denial-log writes don't pollute. Trap-cleans on EXIT.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../block-dangerous-commands.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-block-danger-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Invoke hook; returns "exit:STDOUT" string.
# Stdout is suppressed-into-var; stderr discarded.
call_hook() {
  local cmd="$1"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'command': sys.argv[1]}}))" "$cmd")
  HOME="$SANDBOX" printf '%s' "$payload" | bash "$HOOK" 2>/dev/null
}

# ─── AC1: git remote add → block exit 2 ───────────────────────────────────────
EXIT=0
STDOUT=$(call_hook "git remote add upstream https://example.com/r.git") || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC1_remote_add_blocked"
else
  fail "AC1_remote_add_blocked" "expected exit 2, got $EXIT; stdout=$STDOUT"
fi

# ─── AC2: git config --global → block exit 2 ──────────────────────────────────
EXIT=0
STDOUT=$(call_hook "git config --global user.email x@y.z") || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC2_git_config_global_blocked"
else
  fail "AC2_git_config_global_blocked" "expected exit 2, got $EXIT; stdout=$STDOUT"
fi

# ─── AC3: docker --privileged → ASK JSON on stdout, exit 0 ────────────────────
EXIT=0
STDOUT=$(call_hook "docker run --privileged ubuntu echo hi") || EXIT=$?
if [ "$EXIT" -eq 0 ] && echo "$STDOUT" | grep -q '"permissionDecision": "ask"'; then
  pass "AC3_docker_privileged_ask_json"
else
  fail "AC3_docker_privileged_ask_json" "expected exit 0 + ask JSON, got exit=$EXIT stdout=$STDOUT"
fi

# ─── AC4: git reset --hard → ASK JSON on stdout, exit 0 ───────────────────────
EXIT=0
STDOUT=$(call_hook "git reset --hard HEAD~5") || EXIT=$?
if [ "$EXIT" -eq 0 ] && echo "$STDOUT" | grep -q '"permissionDecision": "ask"'; then
  pass "AC4_git_reset_hard_ask_json"
else
  fail "AC4_git_reset_hard_ask_json" "expected exit 0 + ask JSON, got exit=$EXIT stdout=$STDOUT"
fi

# ─── AC5: git branch -D → hard block exit 2 ───────────────────────────────────
EXIT=0
STDOUT=$(call_hook "git branch -D feature/x") || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC5_git_branch_force_delete_blocked"
else
  fail "AC5_git_branch_force_delete_blocked" "expected exit 2, got $EXIT; stdout=$STDOUT"
fi

# ─── AC6: ls -la → allow exit 0 ───────────────────────────────────────────────
EXIT=0
STDOUT=$(call_hook "ls -la") || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDOUT" ]; then
  pass "AC6_ls_allowed_silent"
else
  fail "AC6_ls_allowed_silent" "expected exit 0 + empty stdout, got exit=$EXIT stdout=$STDOUT"
fi

# ─── AC7: git status → allow exit 0 ───────────────────────────────────────────
EXIT=0
STDOUT=$(call_hook "git status") || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ -z "$STDOUT" ]; then
  pass "AC7_git_status_allowed_silent"
else
  fail "AC7_git_status_allowed_silent" "expected exit 0 + empty stdout, got exit=$EXIT stdout=$STDOUT"
fi

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
