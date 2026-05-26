#!/usr/bin/env bash
# test_block_stage_sensitive.sh — smoke test for block-stage-sensitive.sh.
#
# ACs:
#   1. `git add .env` blocks with exit 2.
#   2. `git add README.md` allows with exit 0.
#   3. `git add -A` blocks (outside .claude/worktrees/).
#   4. `git add docs/progress.md` blocks (matches docs/progress.md never-stage entry).
#   5. Missing never-stage.txt config defaults to deny (exit 2).
#
# Sandboxes HOME via mktemp -d so the real ~/.claude/config is never touched.
# Trap-cleans on EXIT.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../block-stage-sensitive.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-block-stage-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# Mirror the project never-stage.txt into the sandboxed HOME so the hook
# resolves $HOME/.claude/config/never-stage.txt locally.
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
mkdir -p "$SANDBOX/home/.claude/config"
cp "$REPO_ROOT/claude/config/never-stage.txt" "$SANDBOX/home/.claude/config/never-stage.txt"

# Also need the helper scripts to resolve via the hook's own dirname.
# Hook references "$(dirname "$0")/_pathguard.py" — invoking the hook
# directly from its real path resolves correctly.

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Invoke hook with a tool_input.command JSON envelope.
# HOME must be exported to the bash subshell so the hook's $HOME resolution
# uses the sandboxed home. Putting HOME=... before printf only env-prefixes
# printf — bash itself inherits the parent shell's HOME. Use a subshell.
call_hook() {
  local cmd="$1"
  local extra_home="${2:-$SANDBOX/home}"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'command': sys.argv[1]}}))" "$cmd")
  HOME="$extra_home" bash -c 'printf "%s" "$1" | bash "$2"' _ "$payload" "$HOOK"
}

# ─── AC1: git add .env blocks ─────────────────────────────────────────────────
EXIT=0
OUT=$(call_hook "git add .env" 2>&1) || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC1_git_add_dotenv_blocked"
else
  fail "AC1_git_add_dotenv_blocked" "expected exit 2, got $EXIT; out=$OUT"
fi

# ─── AC2: git add README.md allows ────────────────────────────────────────────
EXIT=0
OUT=$(call_hook "git add README.md" 2>&1) || EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  pass "AC2_git_add_readme_allowed"
else
  fail "AC2_git_add_readme_allowed" "expected exit 0, got $EXIT; out=$OUT"
fi

# ─── AC3: git add -A blocks (outside worktrees) ───────────────────────────────
EXIT=0
OUT=$(call_hook "git add -A" 2>&1) || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC3_git_add_dash_A_blocked"
else
  fail "AC3_git_add_dash_A_blocked" "expected exit 2, got $EXIT; out=$OUT"
fi

# ─── AC4: docs/progress.md blocks ─────────────────────────────────────────────
EXIT=0
OUT=$(call_hook "git add docs/progress.md" 2>&1) || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC4_git_add_progress_md_blocked"
else
  fail "AC4_git_add_progress_md_blocked" "expected exit 2, got $EXIT; out=$OUT"
fi

# ─── AC5: missing config defaults to deny ─────────────────────────────────────
EMPTY_HOME="$SANDBOX/empty-home"
mkdir -p "$EMPTY_HOME/.claude/config"  # parent dirs exist but no file
EXIT=0
OUT=$(call_hook "git add somefile.txt" "$EMPTY_HOME" 2>&1) || EXIT=$?
if [ "$EXIT" -eq 2 ]; then
  pass "AC5_missing_config_default_deny"
else
  fail "AC5_missing_config_default_deny" "expected exit 2 default-deny, got $EXIT; out=$OUT"
fi

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
