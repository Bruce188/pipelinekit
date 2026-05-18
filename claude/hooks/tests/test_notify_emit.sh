#!/usr/bin/env bash
set -euo pipefail
# test_notify_emit.sh — smoke tests for claude/hooks/notify-emit.sh
#
# Each test runs the helper in a controlled env-var setup and asserts an
# output property. Aggregate PASS/FAIL printed at end; non-zero exit on any FAIL.

# Resolve helper path relative to this script (so the test passes regardless
# of caller's cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/../notify-emit.sh"

if [ ! -x "$HELPER" ]; then
  echo "FATAL: $HELPER not executable"
  exit 2
fi

PASS=0
FAIL=0
FAILED_NAMES=()

record() {
  local name="$1" outcome="$2" detail="${3:-}"
  if [ "$outcome" = "PASS" ]; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name — $detail"
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# test_01: beacon mode emits all 6 keys
# ---------------------------------------------------------------------------
out=$(
  NOTIFY_FEATURE_INDEX="9/23" \
  NOTIFY_STEP="review" \
  NOTIFY_EVENT_TYPE="feature-done" \
  NOTIFY_TEXT="hello world" \
  NOTIFY_ACTION_LINK="claude://session/abc" \
  NOTIFY_FEATURE_NAME="feat/pipeline-mobile-notifications" \
  "$HELPER" --mode beacon
)
if python3 -c '
import json, sys
d = json.loads(sys.argv[1])
required = {"feature_index","step","event_type","text","action_link","feature_name"}
assert required <= set(d.keys()), f"missing: {required - set(d.keys())}"
' "$out" 2>/dev/null; then
  record "test_01_build_payload_6_fields" PASS
else
  record "test_01_build_payload_6_fields" FAIL "out=$out"
fi

# ---------------------------------------------------------------------------
# test_02: text truncation at 200 chars when input is 201 chars
# ---------------------------------------------------------------------------
long_text=$(printf 'x%.0s' {1..201})
out=$(
  NOTIFY_FEATURE_INDEX="9/23" \
  NOTIFY_STEP="review" \
  NOTIFY_EVENT_TYPE="feature-done" \
  NOTIFY_TEXT="$long_text" \
  NOTIFY_FEATURE_NAME="feat/x" \
  "$HELPER" --mode beacon
)
actual_text=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["text"])
' "$out")
if [ "${#actual_text}" -le 200 ] && [[ "$actual_text" == *"..." ]]; then
  record "test_02_text_truncation_200" PASS
else
  record "test_02_text_truncation_200" FAIL "len=${#actual_text} suffix=${actual_text: -3}"
fi

# ---------------------------------------------------------------------------
# test_03: text of 199 chars passes through unchanged
# ---------------------------------------------------------------------------
short_text=$(printf 'y%.0s' {1..199})
out=$(
  NOTIFY_FEATURE_INDEX="9/23" \
  NOTIFY_STEP="review" \
  NOTIFY_EVENT_TYPE="feature-done" \
  NOTIFY_TEXT="$short_text" \
  NOTIFY_FEATURE_NAME="feat/x" \
  "$HELPER" --mode beacon
)
actual_text=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["text"])
' "$out")
if [ "$actual_text" = "$short_text" ]; then
  record "test_03_text_within_200" PASS
else
  record "test_03_text_within_200" FAIL "input_len=${#short_text} out_len=${#actual_text}"
fi

# ---------------------------------------------------------------------------
# test_04: PIPELINE_NO_NOTIFICATIONS=1 short-circuit
# ---------------------------------------------------------------------------
out=$(
  PIPELINE_NO_NOTIFICATIONS=1 \
  NOTIFY_FEATURE_INDEX="9/23" \
  NOTIFY_STEP="review" \
  NOTIFY_EVENT_TYPE="feature-done" \
  NOTIFY_TEXT="hello" \
  NOTIFY_FEATURE_NAME="feat/x" \
  "$HELPER" --mode beacon
)
rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
  record "test_04_opt_out_short_circuit" PASS
else
  record "test_04_opt_out_short_circuit" FAIL "rc=$rc out=$out"
fi

# ---------------------------------------------------------------------------
# test_05: hook-mode OSC 777 escape sequence shape
# ---------------------------------------------------------------------------
out=$(
  NOTIFY_FEATURE_INDEX="9/23" \
  NOTIFY_STEP="review" \
  NOTIFY_EVENT_TYPE="error" \
  NOTIFY_TEXT="something happened" \
  NOTIFY_FEATURE_NAME="feat/x" \
  "$HELPER"
)
# python3 json output contains the escape bytes as  and  in the JSON string.
if echo "$out" | grep -qE '\\u001b\]777;notify;Claude Code;'; then
  record "test_05_osc_777_shape" PASS
else
  record "test_05_osc_777_shape" FAIL "out=$out"
fi

# ---------------------------------------------------------------------------
# test_06: event_type routing — all 6 canonical values
# ---------------------------------------------------------------------------
test_06_failures=0
for et in question error dropped human-review budget-breach feature-done; do
  out=$(
    NOTIFY_FEATURE_INDEX="9/23" \
    NOTIFY_STEP="review" \
    NOTIFY_EVENT_TYPE="$et" \
    NOTIFY_TEXT="t" \
    NOTIFY_FEATURE_NAME="feat/x" \
    "$HELPER" --mode beacon
  )
  got=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["event_type"])
' "$out")
  if [ "$got" != "$et" ]; then
    test_06_failures=$((test_06_failures + 1))
  fi
done
if [ "$test_06_failures" -eq 0 ]; then
  record "test_06_event_type_routing" PASS
else
  record "test_06_event_type_routing" FAIL "$test_06_failures of 6 event_types misrouted"
fi

# ---------------------------------------------------------------------------
# test_07: helper does NOT read docs/*.md (structural grep)
# ---------------------------------------------------------------------------
docs_refs=$(grep -c 'docs/plan\|docs/charter\|docs/review\|docs/analysis' "$HELPER" || true)
if [ "$docs_refs" = "0" ]; then
  record "test_07_no_docs_reads" PASS
else
  record "test_07_no_docs_reads" FAIL "found $docs_refs docs references"
fi

# ---------------------------------------------------------------------------
# test_08: human-review event_type round-trips through beacon mode (F10 contract)
# ---------------------------------------------------------------------------
out=$(
  NOTIFY_FEATURE_INDEX="10/23" \
  NOTIFY_STEP="merge" \
  NOTIFY_EVENT_TYPE="human-review" \
  NOTIFY_TEXT="Approve squash-merge of feat/integrate-openhuman?" \
  NOTIFY_ACTION_LINK="signal-file:///abs/path/.claude/openhuman/feat-x-1234.json" \
  NOTIFY_FEATURE_NAME="feat/integrate-openhuman" \
  "$HELPER" --mode beacon
)
got=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["event_type"])
' "$out")
if [ "$got" = "human-review" ]; then
  record "test_08_human_review_event_type" PASS
else
  record "test_08_human_review_event_type" FAIL "got=$got"
fi

# ---------------------------------------------------------------------------
# test_09: human-review action_link signal-file URI round-trips byte-for-byte (F10 contract)
# ---------------------------------------------------------------------------
link="signal-file:///abs/path/.claude/openhuman/feat-x-1234.json"
out=$(
  NOTIFY_FEATURE_INDEX="10/23" \
  NOTIFY_STEP="merge" \
  NOTIFY_EVENT_TYPE="human-review" \
  NOTIFY_TEXT="Approve squash-merge?" \
  NOTIFY_ACTION_LINK="$link" \
  NOTIFY_FEATURE_NAME="feat/integrate-openhuman" \
  "$HELPER" --mode beacon
)
got=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["action_link"])
' "$out")
if [ "$got" = "$link" ]; then
  record "test_09_human_review_action_link" PASS
else
  record "test_09_human_review_action_link" FAIL "got=$got"
fi

# ---------------------------------------------------------------------------
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
