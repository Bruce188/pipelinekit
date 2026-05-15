#!/usr/bin/env bash
# Verify claude-portable install integrity.
# Exits non-zero if critical paths or sanitization invariants fail.

set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
FAIL=0
pass()  { printf '  [pass] %s\n' "$*"; }
fail()  { printf '  [fail] %s\n' "$*"; FAIL=$((FAIL+1)); }

echo "Verifying claude-portable at $CLAUDE_HOME"

# Core files (CLAUDE.md may be rendered or template-only pre-install)
if [[ -f "$CLAUDE_HOME/CLAUDE.md" ]]; then
  pass "exists: CLAUDE.md (rendered)"
elif [[ -f "$CLAUDE_HOME/CLAUDE.md.template" ]]; then
  pass "exists: CLAUDE.md.template (pre-render)"
else
  fail "missing: CLAUDE.md or CLAUDE.md.template"
fi
for f in rules/workflow.md rules/agents-worktrees.md; do
  [[ -f "$CLAUDE_HOME/$f" ]] && pass "exists: $f" || fail "missing: $f"
done

# Hook executability
HOOK_COUNT=$(find "$CLAUDE_HOME/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | wc -l)
[[ "$HOOK_COUNT" -gt 10 ]] && pass "hooks present ($HOOK_COUNT)" || fail "too few hooks ($HOOK_COUNT)"
NONEXEC=$(find "$CLAUDE_HOME/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) ! -executable 2>/dev/null | wc -l)
[[ "$NONEXEC" -eq 0 ]] && pass "all hooks executable" || fail "$NONEXEC hooks not executable"

# Skill count
SKILL_COUNT=$(find "$CLAUDE_HOME/skills" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
[[ "$SKILL_COUNT" -ge 20 ]] && pass "skills present ($SKILL_COUNT)" || fail "too few skills ($SKILL_COUNT)"

# Agent count
AGENT_COUNT=$(find "$CLAUDE_HOME/agents" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l)
[[ "$AGENT_COUNT" -ge 10 ]] && pass "agents present ($AGENT_COUNT)" || fail "too few agents ($AGENT_COUNT)"

# Sanitization invariants (relevant only when run from the repo)
REPO_ROOT="${CLAUDE_PORTABLE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if [[ -d "$REPO_ROOT/claude" ]]; then
  LEAK=$(grep -rIn -E "(brucieboyy99|/home/bruce(/|$))" "$REPO_ROOT/claude" 2>/dev/null | wc -l)
  [[ "$LEAK" -eq 0 ]] && pass "no personal data leaks" || fail "$LEAK personal data references found"

  ORCH=$(grep -rIn "orchestrate\.sh" "$REPO_ROOT/claude" 2>/dev/null | wc -l)
  [[ "$ORCH" -eq 0 ]] && pass "no orchestrate.sh references" || fail "$ORCH orchestrate.sh references remain"

  CLAUDE_P=$(grep -rIn -E "\bclaude -p\b" "$REPO_ROOT/claude" 2>/dev/null | wc -l)
  [[ "$CLAUDE_P" -eq 0 ]] && pass "no 'claude -p' subprocess calls" || fail "$CLAUDE_P 'claude -p' references remain"
fi

# Optional Claude CLI
if command -v claude >/dev/null 2>&1; then
  pass "claude CLI on PATH ($(claude --version 2>&1 | head -1))"
else
  fail "claude CLI not on PATH — install from https://claude.ai/install.sh"
fi

echo
if [[ "$FAIL" -gt 0 ]]; then
  echo "Verification FAILED ($FAIL issues)"
  exit 1
fi
echo "Verification PASSED"
