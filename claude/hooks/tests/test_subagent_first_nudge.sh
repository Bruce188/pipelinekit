#!/usr/bin/env bash
# test_subagent_first_nudge.sh — 4-AC hook smoke test for once-per-session cap.
#
# ACs:
#   1. 3 consecutive calls → 1 banner emission (calls 2 + 3 silent).
#   2. Deleting marker → next call re-emits.
#   3. PIPELINE_NO_SUBAGENT_NUDGE=1 suppresses regardless of marker state.
#   4. Hook script's own --selftest still passes.
#
# Sandboxes HOME via mktemp -d so the real ~/.claude/.subagent-nudge-fired
# is never touched. Trap-cleans on EXIT.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../subagent-first-nudge.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d)
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Call helper. $1 = prompt, $2 (optional) = extra env (e.g. "PIPELINE_NO_SUBAGENT_NUDGE=1").
call_hook() {
  local prompt="$1"
  local extra_env="${2:-}"
  if [ -n "$extra_env" ]; then
    HOME="$SANDBOX" env "$extra_env" bash -c "printf '%s' '{\"prompt\":\"$prompt\",\"session_id\":\"test\"}' | bash '$HOOK' 2>/dev/null"
  else
    HOME="$SANDBOX" bash -c "printf '%s' '{\"prompt\":\"$prompt\",\"session_id\":\"test\"}' | bash '$HOOK' 2>/dev/null"
  fi
}

MARKER="$SANDBOX/.claude/.subagent-nudge-fired"

# ─── AC1: 3 consecutive calls → 1 banner ──────────────────────────────────────
rm -f "$MARKER"
OUT1=$(call_hook "implement feature X")
OUT2=$(call_hook "implement feature Y")
OUT3=$(call_hook "implement feature Z")

if echo "$OUT1" | grep -q "DEFAULT MODE"; then
  pass "AC1a_call1_emits_banner"
else
  fail "AC1a_call1_emits_banner" "expected DEFAULT MODE in call 1 output, got: $OUT1"
fi

if [ -z "$OUT2" ]; then
  pass "AC1b_call2_silent"
else
  fail "AC1b_call2_silent" "expected empty stdout on call 2, got: $OUT2"
fi

if [ -z "$OUT3" ]; then
  pass "AC1c_call3_silent"
else
  fail "AC1c_call3_silent" "expected empty stdout on call 3, got: $OUT3"
fi

if [ -f "$MARKER" ]; then
  pass "AC1d_marker_created_after_first_emit"
else
  fail "AC1d_marker_created_after_first_emit" "expected marker at $MARKER"
fi

# ─── AC2: delete marker → next call re-emits ──────────────────────────────────
rm -f "$MARKER"
OUT4=$(call_hook "implement feature W")

if echo "$OUT4" | grep -q "DEFAULT MODE"; then
  pass "AC2_reemit_after_marker_deleted"
else
  fail "AC2_reemit_after_marker_deleted" "expected DEFAULT MODE after rm marker, got: $OUT4"
fi

# ─── AC3: kill switch suppresses regardless of marker state ───────────────────
# 3a: kill switch with marker absent → silent.
rm -f "$MARKER"
OUT5=$(call_hook "implement X" "PIPELINE_NO_SUBAGENT_NUDGE=1")
if [ -z "$OUT5" ]; then
  pass "AC3a_kill_switch_silent_marker_absent"
else
  fail "AC3a_kill_switch_silent_marker_absent" "expected empty stdout, got: $OUT5"
fi

# Kill-switch must NOT create the marker (it short-circuits before the gate).
if [ ! -f "$MARKER" ]; then
  pass "AC3b_kill_switch_does_not_touch_marker"
else
  fail "AC3b_kill_switch_does_not_touch_marker" "marker created unexpectedly"
fi

# 3c: kill switch with marker present → still silent.
mkdir -p "$(dirname "$MARKER")"
: > "$MARKER"
OUT6=$(call_hook "implement X" "PIPELINE_NO_SUBAGENT_NUDGE=1")
if [ -z "$OUT6" ]; then
  pass "AC3c_kill_switch_silent_marker_present"
else
  fail "AC3c_kill_switch_silent_marker_present" "expected empty stdout, got: $OUT6"
fi

# ─── AC4: existing --selftest still passes ────────────────────────────────────
# The hook's own selftest runs 7 cases. Run it in its own sandboxed HOME.
SELFTEST_SANDBOX=$(mktemp -d)
if HOME="$SELFTEST_SANDBOX" bash "$HOOK" --selftest >/dev/null 2>&1; then
  pass "AC4_hook_selftest_passes"
else
  fail "AC4_hook_selftest_passes" "hook --selftest exited non-zero"
fi
rm -rf "$SELFTEST_SANDBOX"

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
