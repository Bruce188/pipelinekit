#!/usr/bin/env bash
# Smoke test for feat/path-d-escalation.
#
# Asserts the documentation + helper contracts that wire Path D between
# Path C exhaustion and the feature-failed terminal. A pure-bash test
# cannot dispatch a real subagent, so the assertions cover the surface
# the orchestrator reads at runtime: reference.md body, SKILL.md state
# template + Step 5.8 row + cycle-accounting note, workflow.md schema,
# and notify-emit.sh beacon payload.
#
# Run from repo root:
#   bash claude/skills/pipeline/tests/test_path_d_escalation.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
REFERENCE="$REPO_ROOT/claude/skills/pipeline/reference.md"
SKILL="$REPO_ROOT/claude/skills/pipeline/SKILL.md"
SKILLD="$REPO_ROOT/claude/skills/pipeline"
WORKFLOW="$REPO_ROOT/claude/rules/workflow.md"
NOTIFY="$REPO_ROOT/claude/hooks/notify-emit.sh"

PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

[ -f "$REFERENCE" ] || { echo "missing: $REFERENCE"; exit 1; }
[ -f "$SKILL"     ] || { echo "missing: $SKILL"; exit 1; }
[ -f "$WORKFLOW"  ] || { echo "missing: $WORKFLOW"; exit 1; }
[ -f "$NOTIFY"    ] || { echo "missing: $NOTIFY"; exit 1; }

echo "Test 1: reference.md has a Path D section heading"
if grep -E '^### Path D — Fresh-context Salvage' "$REFERENCE" >/dev/null; then
  ok "reference.md has '### Path D — Fresh-context Salvage' heading"
else
  fail "reference.md missing '### Path D — Fresh-context Salvage' heading"
fi

echo "Test 2: Path D section appears AFTER Path C section in reference.md"
PATH_C_LINE=$(grep -n '^### Path C — Scope Change' "$REFERENCE" | head -1 | cut -d: -f1)
PATH_D_LINE=$(grep -n '^### Path D — Fresh-context Salvage' "$REFERENCE" | head -1 | cut -d: -f1)
if [ -n "$PATH_C_LINE" ] && [ -n "$PATH_D_LINE" ] && [ "$PATH_D_LINE" -gt "$PATH_C_LINE" ]; then
  ok "Path D (line $PATH_D_LINE) appears after Path C (line $PATH_C_LINE)"
else
  fail "Path D does not appear after Path C in reference.md (C=$PATH_C_LINE D=$PATH_D_LINE)"
fi

echo "Test 3: SKILL.md Step 5.8 summary lists Path D"
if grep -F '**Path D — Fresh-context Salvage:**' "$SKILLD"/*.md >/dev/null; then
  ok "SKILL.md Step 5.8 summary contains Path D row"
else
  fail "SKILL.md Step 5.8 summary missing Path D row"
fi

echo "Test 4: SKILL.md state-file template contains **Path D attempted:**"
if grep -F '**Path D attempted:**' "$SKILLD"/*.md >/dev/null; then
  ok "SKILL.md state template lists **Path D attempted:**"
else
  fail "SKILL.md state template missing **Path D attempted:**"
fi

echo "Test 5: workflow.md Pipeline State Schema lists **Path D attempted:**"
if grep -F '**Path D attempted:**' "$WORKFLOW" >/dev/null; then
  ok "workflow.md schema lists **Path D attempted:**"
else
  fail "workflow.md schema missing **Path D attempted:**"
fi

echo "Test 6: notify-emit.sh beacon mode emits path_d_attempted field"
# Invoke beacon mode with required env vars + NOTIFY_PATH_D_ATTEMPTED=true.
PAYLOAD=$(
  NOTIFY_TEXT="path D fired" \
  NOTIFY_EVENT_TYPE="feature-failed" \
  NOTIFY_FEATURE_NAME="feat/test" \
  NOTIFY_PATH_D_ATTEMPTED="true" \
  bash "$NOTIFY" --mode beacon
)
if echo "$PAYLOAD" | grep -F '"path_d_attempted": true' >/dev/null; then
  ok "notify-emit.sh beacon payload contains path_d_attempted=true when env var set"
else
  fail "notify-emit.sh beacon payload missing path_d_attempted=true (got: $PAYLOAD)"
fi

echo "Test 7: notify-emit.sh defaults path_d_attempted to false when env var unset"
PAYLOAD_DEFAULT=$(
  NOTIFY_TEXT="ordinary failure" \
  NOTIFY_EVENT_TYPE="feature-failed" \
  NOTIFY_FEATURE_NAME="feat/test" \
  bash "$NOTIFY" --mode beacon
)
if echo "$PAYLOAD_DEFAULT" | grep -F '"path_d_attempted": false' >/dev/null; then
  ok "notify-emit.sh beacon payload defaults path_d_attempted=false"
else
  fail "notify-emit.sh beacon payload not defaulting path_d_attempted=false (got: $PAYLOAD_DEFAULT)"
fi

echo "Test 8: Path D body documents the one-shot constraint"
PATH_D_BODY=$(awk '/^### Path D — Fresh-context Salvage/,/^### Retry/' "$REFERENCE")
if echo "$PATH_D_BODY" | grep -E 'one-shot|exactly once|max 1 attempt|EXACTLY ONCE' >/dev/null; then
  ok "Path D body documents the one-shot / max-1-attempt constraint"
else
  fail "Path D body missing one-shot / max-1-attempt language"
fi

echo "Test 9: Path D body documents the no-infinite-loop backstop"
if echo "$PATH_D_BODY" | grep -E 'no.{0,20}loop.{0,20}back|never loops? back|feature-failed terminal|infinite loop' >/dev/null; then
  ok "Path D body documents the no-loop-back backstop to feature-failed terminal"
else
  fail "Path D body missing no-loop-back / feature-failed-terminal backstop language"
fi

echo "Test 10: SKILL.md cycle accounting mentions Path D"
if grep -E 'Path D adds 1 more salvage attempt|Path D.{0,30}salvage' "$SKILLD"/*.md >/dev/null; then
  ok "SKILL.md cycle-accounting note mentions Path D"
else
  fail "SKILL.md cycle-accounting note missing Path D mention"
fi

echo
echo "Result: $PASS pass, $FAIL fail"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
