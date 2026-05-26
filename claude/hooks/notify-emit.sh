#!/usr/bin/env bash
set -euo pipefail
# notify-emit.sh — canonical notification builder/emitter for /pipeline + F10.
#
# Reads 6 fields from env vars (NOTIFY_*), short-circuits on
# PIPELINE_NO_NOTIFICATIONS=1, and emits in one of two modes:
#   - hook mode (default): one-line JSON {"terminalSequence":"\033]777;notify;Claude Code;<text>\007"}
#   - beacon mode (--mode beacon): one-line JSON of the 6-field payload
#     captured by the orchestrator for forwarding to the PushNotification tool.
#
# Truncation convention: 200-char byte cap inclusive of the 3-char "..." ellipsis
# (so when NOTIFY_TEXT length > 200, output text = ${NOTIFY_TEXT:0:197}...).
#
# The helper does NOT read any docs/*.md file — the payload text comes from env
# vars only. The public CLI here is the authoritative contract.
#
# Throttling: NONE here. Channels' built-in mechanics are authoritative.

# Opt-out short-circuit (must be before any other side effects).
[ "${PIPELINE_NO_NOTIFICATIONS:-0}" = "1" ] && exit 0

MODE="hook"
if [ "${1:-}" = "--mode" ] && [ "${2:-}" = "beacon" ]; then
  MODE="beacon"
fi

# Required-field defensive defaults — missing/empty required field → no-op exit 0.
NOTIFY_TEXT="${NOTIFY_TEXT:-}"
NOTIFY_EVENT_TYPE="${NOTIFY_EVENT_TYPE:-}"
NOTIFY_FEATURE_NAME="${NOTIFY_FEATURE_NAME:-}"
if [ -z "$NOTIFY_TEXT" ] || [ -z "$NOTIFY_EVENT_TYPE" ] || [ -z "$NOTIFY_FEATURE_NAME" ]; then
  exit 0
fi

# Optional fields default to empty string for the payload.
NOTIFY_FEATURE_INDEX="${NOTIFY_FEATURE_INDEX:-}"
NOTIFY_STEP="${NOTIFY_STEP:-}"
NOTIFY_ACTION_LINK="${NOTIFY_ACTION_LINK:-}"

# 200-byte truncation with ellipsis suffix (197 + "...") when length > 200.
if [ "${#NOTIFY_TEXT}" -gt 200 ]; then
  NOTIFY_TEXT="${NOTIFY_TEXT:0:197}..."
fi

# JSON construction via python3 (jq is NOT installed per feedback_hooks_jq.md).
# Export the truncated text so the python3 -c child reads it from env.
export NOTIFY_TEXT_OUT="$NOTIFY_TEXT"

if [ "$MODE" = "beacon" ]; then
  python3 -c '
import json, os, sys
payload = {
    "feature_index": os.environ.get("NOTIFY_FEATURE_INDEX", ""),
    "step":          os.environ.get("NOTIFY_STEP", ""),
    "event_type":    os.environ.get("NOTIFY_EVENT_TYPE", ""),
    "text":          os.environ.get("NOTIFY_TEXT_OUT", ""),
    "action_link":   os.environ.get("NOTIFY_ACTION_LINK", ""),
    "feature_name":  os.environ.get("NOTIFY_FEATURE_NAME", ""),
    # path_d_attempted surfaces Path D salvage state for feature-failed events.
    # Defaults to False when the env var is absent (legacy callers, non-failed
    # events). The orchestrator sets NOTIFY_PATH_D_ATTEMPTED=true when emitting
    # the feature-failed beacon after a Path D dispatch has fired.
    "path_d_attempted": os.environ.get("NOTIFY_PATH_D_ATTEMPTED", "false").lower() == "true",
}
sys.stdout.write(json.dumps(payload) + "\n")
'
else
  # Hook mode: emit OSC 777 terminalSequence JSON. The literal escape bytes are
  # \x1b (ESC) at the start and \x07 (BEL) at the end of the OSC 777 sequence.
  python3 -c '
import json, os, sys
text = os.environ.get("NOTIFY_TEXT_OUT", "")
seq = "\x1b]777;notify;Claude Code;" + text + "\x07"
sys.stdout.write(json.dumps({"terminalSequence": seq}) + "\n")
'
fi

# Notification-hook exit-code contract: non-blocking; always exit 0.
exit 0
