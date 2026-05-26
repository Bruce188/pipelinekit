#!/usr/bin/env bash
# claude/skills/caveman-mode/tests/test_tier1_allowlist.sh
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/tier1_allowlist.sh"
PASS=0; FAIL=0
check() {
  local name="$1" expected_exit="$2" expected_stderr_substr="$3" path="$4"
  local out err rc
  err=$("$SCRIPT" "$path" 2>&1 >/dev/null); rc=$?
  if [ "$rc" = "$expected_exit" ] && { [ -z "$expected_stderr_substr" ] || echo "$err" | grep -q "$expected_stderr_substr"; }; then
    echo "PASS: $name"; PASS=$((PASS+1))
  else
    echo "FAIL: $name (rc=$rc, stderr=$err)"; FAIL=$((FAIL+1))
  fi
}
check "accept CLAUDE.md"                       0 "" "CLAUDE.md"
check "accept claude/CLAUDE.md.template"       0 "" "claude/CLAUDE.md.template"
check "accept claude/rules/workflow.md"        0 "" "claude/rules/workflow.md"
check "accept claude/rules/agents-worktrees.md" 0 "" "claude/rules/agents-worktrees.md"
check "reject claude/agents/code-reviewer.md"   2 "not in Tier 1 allowlist" "claude/agents/code-reviewer.md"
check "reject claude/skills/pipeline/SKILL.md"  2 "not in Tier 1 allowlist" "claude/skills/pipeline/SKILL.md"
check "reject claude/commands/caveman-compress.md" 2 "not in Tier 1 allowlist" "claude/commands/caveman-compress.md"
check "reject /tmp/random.md"                   2 "not in Tier 1 allowlist" "/tmp/random.md"
echo "Results: $PASS PASS / $FAIL FAIL"
exit "$FAIL"
