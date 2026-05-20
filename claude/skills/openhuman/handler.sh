#!/usr/bin/env bash
set -euo pipefail
# PreToolUse handler for openhuman skill — fires on Bash(git merge --squash *) when PIPELINE_HUMAN_REVIEW is set.
#
# Behavior:
#   1. Read hook stdin JSON; extract tool_input.command.
#   2. Defensive double-check: command must match '^git merge --squash'. Else passthrough allow.
#   3. Env gate: PIPELINE_HUMAN_REVIEW unset or 0 → passthrough allow.
#   4. Mint signal-file path; mkdir -p the parent.
#   5. Invoke F9 helper (notify-emit.sh --mode beacon) — CONSUME, never fork. Output discarded;
#      the helper's job is informational. The response surface is the signal file.
#   6. Poll signal file every 5s with SECONDS-based timeout. On timeout: deny + OPENHUMAN_TIMEOUT.
#   7. On signal present: parse JSON, emit matching permissionDecision (allow/deny). Malformed → deny.
#
# All notification payload text comes from env vars only — the handler MUST NOT cat or otherwise
# read project workflow markdown (plan, charter, review, analysis). Those file substrings are
# intentionally absent from this script; AC10 enforces grep == 0.
#
# JSON parsing via python3 -c (jq is NOT installed per feedback_hooks_jq.md).

# Resolve repo root (relative to this script) to locate the F9 helper. The script lives at
# claude/skills/openhuman/handler.sh — climb three levels.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
NOTIFY_HELPER="$REPO_ROOT/claude/hooks/notify-emit.sh"

emit_decision() {
  local decision="$1" reason="${2:-}"
  if [ -n "$reason" ]; then
    DECISION="$decision" REASON="$reason" python3 -c '
import json, os, sys
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": os.environ["DECISION"],
        "permissionDecisionReason": os.environ["REASON"],
    }
}) + "\n")
'
  else
    DECISION="$decision" python3 -c '
import json, os, sys
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": os.environ["DECISION"],
    }
}) + "\n")
'
  fi
}

# Subprocess-driver caveat: TTY may be absent. python3 -c reads stdin from the hook engine; no
# direct stdin access from the shell needed. Crashes are guarded by set -euo pipefail + the
# defensive passthrough below.

# Step 1: read hook stdin JSON, extract tool_input.command. Graceful default to empty string.
CMD="$(python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' || true)"

# Step 2: defensive double-check the command shape. If the if-clause filter is bypassed somehow,
# do NOT block non-matching commands — fail open on the matcher (passthrough allow), fail closed
# on the human-review timeout (deny). This matches the audit's least-surprise principle.
case "$CMD" in
  "git merge --squash"*) ;;
  *) emit_decision "allow"; exit 0 ;;
esac

# Step 3: env-var gate check. Unset or 0 → passthrough.
if [ "${PIPELINE_HUMAN_REVIEW:-0}" = "0" ]; then
  emit_decision "allow"
  exit 0
fi

# Validate timeout is a positive integer (defensive — orchestrator should already validate).
TIMEOUT_MIN="${PIPELINE_HUMAN_REVIEW}"
case "$TIMEOUT_MIN" in
  ''|*[!0-9]*) emit_decision "allow"; exit 0 ;;
esac
if [ "$TIMEOUT_MIN" -le 0 ]; then
  emit_decision "allow"
  exit 0
fi

# Step 4: mint signal-file path. .claude/openhuman/<feature-name>-<unix-timestamp>.json
FEATURE_NAME="${PIPELINE_FEATURE_NAME:-adhoc}"
# Sanitize feature name for filesystem (replace / with -)
SAFE_NAME="${FEATURE_NAME//\//-}"
SIGNAL=".claude/openhuman/${SAFE_NAME}-$(date +%s).json"
mkdir -p "$(dirname "$SIGNAL")"

# Resolve absolute path for the action_link (signal-file:// URI).
SIGNAL_ABS="$(cd "$(dirname "$SIGNAL")" 2>/dev/null && pwd)/$(basename "$SIGNAL")"
if [ -z "$SIGNAL_ABS" ] || [ "$SIGNAL_ABS" = "/$(basename "$SIGNAL")" ]; then
  SIGNAL_ABS="$SIGNAL"
fi

# Step 5: invoke F9 helper — CONSUME unchanged. Output is informational; capture and discard.
# The helper may exit 0 with empty output if PIPELINE_NO_NOTIFICATIONS=1; that is fine — the
# response surface is the signal file, not the helper output.
if [ -x "$NOTIFY_HELPER" ]; then
  NOTIFY_FEATURE_INDEX="${PIPELINE_FEATURE_INDEX:-}" \
  NOTIFY_STEP="merge" \
  NOTIFY_EVENT_TYPE="human-review" \
  NOTIFY_TEXT="Approve squash-merge of ${FEATURE_NAME}? Reply via signal file." \
  NOTIFY_ACTION_LINK="signal-file://${SIGNAL_ABS}" \
  NOTIFY_FEATURE_NAME="${FEATURE_NAME}" \
  "$NOTIFY_HELPER" --mode beacon >/dev/null 2>&1 || true
fi

# Step 6: poll loop with SECONDS-based timeout.
TIMEOUT_SEC=$((TIMEOUT_MIN * 60))
SECONDS=0
while [ ! -f "$SIGNAL" ]; do
  if [ "$SECONDS" -ge "$TIMEOUT_SEC" ]; then
    emit_decision "deny" "OPENHUMAN_TIMEOUT: ${TIMEOUT_MIN} minutes elapsed without approval"
    exit 0
  fi
  sleep 5
done

# Step 7: signal file present. Parse JSON, extract decision field.
DECISION="$(SIG="$SIGNAL" python3 -c '
import json, os, sys
try:
    with open(os.environ["SIG"], "r", encoding="utf-8") as f:
        d = json.load(f)
    val = d.get("decision", "")
    if val in ("allow", "deny"):
        print(val)
    else:
        print("")
except Exception:
    print("")
' 2>/dev/null || echo "")"

case "$DECISION" in
  allow|deny)
    emit_decision "$DECISION"
    exit 0
    ;;
  *)
    emit_decision "deny" "OPENHUMAN_MALFORMED_SIGNAL: ${SIGNAL}"
    exit 0
    ;;
esac
