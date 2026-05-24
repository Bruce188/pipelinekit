#!/usr/bin/env bash
# agent-caveman-gate.sh -- PreToolUse hook for the Agent tool.
#
# When ~/.claude/.caveman-active exists, every Agent dispatch must carry the
# caveman-subagent contract in its prompt parameter so the spawned subagent
# inherits the three-zone split. The Claude Code hook API cannot rewrite
# tool_input on the fly (see claude/hooks/env-scrub.py line 19), so this
# hook uses the detect-and-block pattern: missing contract → exit 2 with
# stderr instructions, and the dispatching agent re-issues the call with
# the contract prepended.
#
# Selftest: bash agent-caveman-gate.sh --selftest

set -euo pipefail

CAVEMAN_MARKER="$HOME/.claude/.caveman-active"
SNIPPET="$HOME/.claude/snippets/caveman-subagent.md"

# ─── Selftest ────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT

  PASS=0
  FAIL=0

  run_case() {
    local name="$1" input="$2" marker_exists="$3" expected_exit="$4"
    local saved_marker="" marker_was=""
    if [ -e "$CAVEMAN_MARKER" ]; then
      marker_was="yes"
      cp -a "$CAVEMAN_MARKER" "$TMP/marker.bak"
    fi
    if [ "$marker_exists" = "yes" ]; then
      echo "wenyan-ultra" > "$CAVEMAN_MARKER"
    else
      rm -f "$CAVEMAN_MARKER"
    fi
    local actual_exit
    set +e
    printf '%s' "$input" | bash "$0" >/dev/null 2>&1
    actual_exit=$?
    set -e
    if [ "$marker_was" = "yes" ]; then
      cp -a "$TMP/marker.bak" "$CAVEMAN_MARKER"
    else
      rm -f "$CAVEMAN_MARKER"
    fi
    if [ "$actual_exit" = "$expected_exit" ]; then
      PASS=$((PASS+1))
      echo "PASS: $name"
    else
      FAIL=$((FAIL+1))
      echo "FAIL: $name (expected exit $expected_exit, got $actual_exit)"
    fi
  }

  run_case "caveman off → allow" \
    '{"tool_name":"Agent","tool_input":{"prompt":"do stuff"}}' \
    "no" 0

  run_case "non-Agent tool → allow" \
    '{"tool_name":"Bash","tool_input":{"command":"ls"}}' \
    "yes" 0

  run_case "Agent + contract present (marker comment) → allow" \
    '{"tool_name":"Agent","tool_input":{"prompt":"<!-- snippet: caveman-subagent v2 --> do stuff"}}' \
    "yes" 0

  run_case "Agent + contract present (wrapper tag) → allow" \
    '{"tool_name":"Agent","tool_input":{"prompt":"<caveman-inherited level=\"wenyan-ultra\"> ... </caveman-inherited> do stuff"}}' \
    "yes" 0

  run_case "Agent + contract present (Inherited verbosity floor) → allow" \
    '{"tool_name":"Agent","tool_input":{"prompt":"Inherited verbosity floor: wenyan-ultra. ... do stuff"}}' \
    "yes" 0

  run_case "Agent + no contract → BLOCK (exit 2)" \
    '{"tool_name":"Agent","tool_input":{"prompt":"do stuff with no contract header"}}' \
    "yes" 2

  run_case "malformed JSON → allow (defensive)" \
    'not-json' \
    "yes" 0

  echo "---"
  echo "Selftest: $PASS passed, $FAIL failed"
  [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# ─── Main hook path ──────────────────────────────────────────────────────────

# Fast path: caveman not active → exit 0 immediately, no JSON parse needed.
[ ! -f "$CAVEMAN_MARKER" ] && exit 0

INPUT=$(cat)

# Pre-filter: only fire on Agent tool. Cheap string match before invoking python3.
case "$INPUT" in
  *'"tool_name":"Agent"'*|*'"tool_name": "Agent"'*) ;;
  *) exit 0 ;;
esac

# Parse JSON via python3 (jq is not installed -- see feedback_hooks_jq.md).
PROMPT=$(printf '%s' "$INPUT" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("__SKIP__")
    sys.exit(0)
if d.get("tool_name") != "Agent":
    print("__SKIP__")
    sys.exit(0)
print(d.get("tool_input", {}).get("prompt", ""))
' 2>/dev/null)

[ "$PROMPT" = "__SKIP__" ] && exit 0

# Accept any of these contract markers in the prompt:
#   - "caveman-subagent"            (the snippet filename / header comment)
#   - "Inherited verbosity floor"   (first line of snippet body)
#   - "<caveman-inherited"          (the wrapper tag the protocol uses)
#   - three-zone + caveman/wenyan   (explicit pairing for ad-hoc inheritance)
if printf '%s' "$PROMPT" | grep -qE -- 'caveman-subagent|Inherited verbosity floor|<caveman-inherited|three-zone.*(caveman|wenyan)|wenyan.*three-zone'; then
  exit 0
fi

# Denial tracking: convert to ask after 3 consecutive hits in 5 min so the
# dispatching agent stops banging on the gate.
TRACKER="$(dirname "$0")/denial_tracker.py"
if [ -f "$TRACKER" ]; then
  if python3 "$TRACKER" check Agent caveman-gate 2>/dev/null; then
    exit 0
  fi
  python3 "$TRACKER" record Agent caveman-gate 2>/dev/null || true
fi

LEVEL=$(head -n1 "$CAVEMAN_MARKER" 2>/dev/null || echo "wenyan-ultra")

{
  echo "BLOCKED: Agent dispatch missing caveman-subagent contract."
  echo ""
  echo "Caveman mode is active (level: $LEVEL). Every Agent dispatch MUST prepend"
  echo "the contract from ~/.claude/snippets/caveman-subagent.md to the 'prompt'"
  echo "parameter so the subagent applies the three-zone split:"
  echo "  Zone 1 — code/paths/commits (normal English, exact)"
  echo "  Zone 2 — narrative prose (real classical Chinese 文言, Han chars mandatory)"
  echo "  Zone 3 — fragments/status/beacons (ultra English)"
  echo ""
  echo "Fix: prepend this header to your prompt, then retry the Agent call:"
  echo ""
  echo "<caveman-inherited level=\"$LEVEL\">"
  if [ -f "$SNIPPET" ]; then
    cat "$SNIPPET"
  else
    echo "(snippet missing at $SNIPPET — run scripts/install.sh to restore)"
  fi
  echo "</caveman-inherited>"
  echo ""
  echo "---"
  echo ""
  echo "(your original prompt text below)"
  echo ""
  echo "Alternatively, run '/caveman off' to stop caveman mode entirely."
} >&2

exit 2
