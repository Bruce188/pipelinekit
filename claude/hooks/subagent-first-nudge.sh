#!/usr/bin/env bash
# subagent-first-nudge.sh — UserPromptSubmit hook
#
# Pipelinekit's Subagent-First principle says non-trivial work should dispatch
# via the `Agent` tool by default. The principle lives in prose at
# ~/.claude/rules/agents-worktrees.md § Subagent Defaults, but prose-only
# enforcement drifts — the LEAD frequently runs work inline that should have
# been dispatched, and the user has to correct mid-flight.
#
# This hook injects a default-mode reminder on every UserPromptSubmit, so the
# LEAD reads the dispatch protocol before planning. Users opt OUT per-prompt by
# including any of these literal phrases in their message:
#
#   - "no subagents" / "no agents"
#   - "do it inline" / "inline mode"
#   - "do it yourself"
#   - "skip subagents" / "skip agents"
#   - "no dispatch" / "don't dispatch"
#
# When opt-out fires, the hook emits a one-line "opt-out detected" notice
# instead of the default nudge — so the LEAD still sees a signal, just the
# opposite one.
#
# Env knobs:
#   PIPELINE_NO_SUBAGENT_NUDGE=1  -> skip silently (kill switch)
#
# Self-test: bash subagent-first-nudge.sh --selftest

set -euo pipefail

# ─── Kill switch ──────────────────────────────────────────────────────────────
if [ "${PIPELINE_NO_SUBAGENT_NUDGE:-0}" = "1" ]; then
  exit 0
fi

# ─── Once-per-session marker ──────────────────────────────────────────────────
# Cap firing to one banner per session lifecycle. SessionStart and PostCompact
# hooks clear the marker. Delete the marker manually to force a re-emit.
NUDGE_MARKER="${HOME}/.claude/.subagent-nudge-fired"

# ─── Self-test ────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS=0; FAIL=0; FAILED=()
  rec() {
    if [ "$2" = "PASS" ]; then echo "PASS: $1"; PASS=$((PASS+1))
    else echo "FAIL: $1 — ${3:-}"; FAIL=$((FAIL+1)); FAILED+=("$1"); fi
  }

  run_with() {
    # $1 = prompt string; returns stdout.
    # Each invocation runs in a sandboxed HOME so the once-per-session marker
    # does not bleed between selftest cases (or touch the real user marker).
    local _sandbox
    _sandbox=$(mktemp -d)
    HOME="$_sandbox" printf '%s' "{\"prompt\":\"$1\",\"session_id\":\"test\"}" \
      | HOME="$_sandbox" bash "${BASH_SOURCE[0]}" 2>/dev/null
    rm -rf "$_sandbox"
  }

  # Test 1: default prompt → nudge present
  OUT=$(run_with "implement a new feature for X")
  if echo "$OUT" | grep -q "DEFAULT MODE"; then
    rec "default_prompt_emits_nudge" PASS
  else
    rec "default_prompt_emits_nudge" FAIL "expected DEFAULT MODE in output"
  fi

  # Test 2: opt-out 'no subagents' → opt-out notice
  OUT=$(run_with "fix the bug, no subagents please")
  if echo "$OUT" | grep -q "opt-out detected"; then
    rec "opt_out_no_subagents" PASS
  else
    rec "opt_out_no_subagents" FAIL "expected opt-out notice"
  fi

  # Test 3: opt-out 'do it inline'
  OUT=$(run_with "edit this file, do it inline")
  if echo "$OUT" | grep -q "opt-out detected"; then
    rec "opt_out_do_it_inline" PASS
  else
    rec "opt_out_do_it_inline" FAIL "expected opt-out notice"
  fi

  # Test 4: opt-out 'do it yourself'
  OUT=$(run_with "just do it yourself")
  if echo "$OUT" | grep -q "opt-out detected"; then
    rec "opt_out_do_it_yourself" PASS
  else
    rec "opt_out_do_it_yourself" FAIL "expected opt-out notice"
  fi

  # Test 5: false-positive guard — 'inline' as adjective should NOT opt out
  OUT=$(run_with "fix the inline comment in foo.js")
  if echo "$OUT" | grep -q "DEFAULT MODE"; then
    rec "no_false_positive_inline_adjective" PASS
  else
    rec "no_false_positive_inline_adjective" FAIL "wrongly opted out"
  fi

  # Test 6: kill switch
  OUT=$(PIPELINE_NO_SUBAGENT_NUDGE=1 run_with "implement X")
  if [ -z "$OUT" ]; then
    rec "kill_switch_silent" PASS
  else
    rec "kill_switch_silent" FAIL "expected empty output, got: $OUT"
  fi

  # Test 7: JSON envelope shape
  OUT=$(run_with "implement X")
  if echo "$OUT" | python3 -c "import sys, json; d=json.load(sys.stdin); assert d['hookSpecificOutput']['hookEventName']=='UserPromptSubmit'" 2>/dev/null; then
    rec "json_envelope_shape" PASS
  else
    rec "json_envelope_shape" FAIL "expected valid hookSpecificOutput JSON"
  fi

  echo "Results: $PASS PASS / $FAIL FAIL"
  [ "$FAIL" -ne 0 ] && { echo "Failed: ${FAILED[*]}"; exit 1; }
  exit 0
fi

# ─── Read envelope ────────────────────────────────────────────────────────────
INPUT=$(cat)

# Extract prompt via python3 (jq not installed — see feedback_hooks_jq.md)
PROMPT=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('prompt', ''))
except Exception:
    print('')
" 2>/dev/null)

# Pre-filter: empty prompt → no-op
if [ -z "$PROMPT" ]; then
  exit 0
fi

# ─── Opt-out detection ────────────────────────────────────────────────────────
# Patterns are case-insensitive, bounded by word breaks. Specific phrases only —
# avoid generic words like "inline" or "directly" that have ambiguous meaning.
OPT_OUT_REGEX='\b(no (sub)?agents?|do it inline|inline mode|do it yourself|skip (sub)?agents?|no dispatch|don.t dispatch)\b'

if echo "$PROMPT" | grep -qiE "$OPT_OUT_REGEX"; then
  MSG="## Subagent dispatch — opt-out detected

The user requested INLINE execution for this prompt. Do NOT dispatch via the \`Agent\` tool unless structurally required (worktree isolation, parallel streams that cannot share context). The default-mode nudge is suppressed for this turn only."
else
  MSG="## Subagent dispatch — DEFAULT MODE

Per pipelinekit's Subagent-First principle, dispatch work via the \`Agent\` tool by default. The only inline exceptions are:

1. **Trivial one-shots** (≤ ~3 tool calls, e.g. read-one-file-then-edit)
2. **Interactive Q&A** with the user actively turn-by-turn
3. **Explicit per-prompt opt-out** — phrases like \`no subagents\`, \`do it inline\`, \`do it yourself\`, \`skip agents\`, \`no dispatch\` (none detected in this prompt)

For pipeline-eligible work (features, slices), prefer \`Skill: pipeline <features-file>\` invoked from the LEAD session — see \`~/.claude/rules/agents-worktrees.md § /pipeline invocation policy\`.

When dispatching multiple independent streams, bundle them in a SINGLE assistant turn (multiple \`Agent\` tool calls in one message) so they run concurrently. Sequential dispatch across turns forfeits the parallelism.

Kill switch for this nudge: export \`PIPELINE_NO_SUBAGENT_NUDGE=1\`."
fi

# ─── Marker gate ──────────────────────────────────────────────────────────────
# Once-per-session cap. If the marker exists, the banner already fired this
# session — exit silently. Otherwise touch the marker and fall through to emit.
# Applies to BOTH the DEFAULT-MODE banner and the opt-out notice (analysis OQ).
# SessionStart and PostCompact hooks clear the marker so the banner re-emits
# after a fresh boot or context compaction.
if [ -f "$NUDGE_MARKER" ]; then
  exit 0
fi
mkdir -p "$(dirname "$NUDGE_MARKER")" 2>/dev/null || true
: > "$NUDGE_MARKER" 2>/dev/null || true

# ─── Emit ─────────────────────────────────────────────────────────────────────
python3 - "$MSG" <<'PYEOF'
import json, sys
msg = sys.argv[1]
out = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": msg,
    }
}
sys.stdout.write(json.dumps(out))
sys.stdout.write("\n")
PYEOF

exit 0
