#!/usr/bin/env bash
# test_pre_edit_protect.sh — smoke test for pre-edit-protect.sh.
#
# ACs:
#   1. Edit on .env → block exit 2.
#   2. Edit on credentials.json → block exit 2.
#   3. Edit on host.pem → block exit 2.
#   4. Edit on id_rsa.key → block exit 2 (.key suffix).
#   5. Edit on .claude/settings.json → block exit 2.
#   6. Edit on .claude/settings.local.json → block exit 2.
#   7. Edit on README.md → allow exit 0.
#   8. Edit on .env.example → allow exit 0 (only exact .env blocked).
#
# Hermetic; no filesystem state needed — hook reads only the JSON stdin.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../pre-edit-protect.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-pre-edit-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

call_hook() {
  local path="$1"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'file_path': sys.argv[1]}}))" "$path")
  HOME="$SANDBOX" printf '%s' "$payload" | bash "$HOOK" 2>/dev/null
}

assert_block() {
  local name="$1"; local path="$2"
  local EXIT=0
  call_hook "$path" >/dev/null || EXIT=$?
  if [ "$EXIT" -eq 2 ]; then
    pass "$name"
  else
    fail "$name" "expected exit 2 for path=$path, got $EXIT"
  fi
}

assert_allow() {
  local name="$1"; local path="$2"
  local EXIT=0
  call_hook "$path" >/dev/null || EXIT=$?
  if [ "$EXIT" -eq 0 ]; then
    pass "$name"
  else
    fail "$name" "expected exit 0 for path=$path, got $EXIT"
  fi
}

# ─── Negative cases (block) ───────────────────────────────────────────────────
assert_block "AC1_dotenv_blocked"             "/abs/path/.env"
assert_block "AC2_credentials_json_blocked"   "/abs/path/credentials.json"
assert_block "AC3_pem_blocked"                "/abs/path/host.pem"
assert_block "AC4_key_blocked"                "/abs/path/id_rsa.key"
assert_block "AC5_claude_settings_blocked"    "/repo/.claude/settings.json"
assert_block "AC6_claude_settings_local_blocked" "/repo/.claude/settings.local.json"

# ─── Positive cases (allow) ───────────────────────────────────────────────────
assert_allow "AC7_readme_allowed"             "/abs/path/README.md"
assert_allow "AC8_dotenv_example_allowed"     "/abs/path/.env.example"

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
