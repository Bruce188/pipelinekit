#!/usr/bin/env bash
# Verify a pipelinekit install in $CLAUDE_HOME. Exits non-zero on failure.
# The checks live in claude/skills/kit/check.py; the /kit command runs the same file.
set -uo pipefail

export CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

echo "Verifying pipelinekit at $CLAUDE_HOME"
python3 "$REPO_ROOT/claude/skills/kit/check.py" --verbose --no-remote || FAIL=1

# Personal-data leak guard (repo checkout only).
if [[ -d "$REPO_ROOT/claude" ]]; then
  LEAK=$(grep -rIn -E "(brucieboyy[0-9]*|/home/bruce(/|\$)|-home-bruce\b)" "$REPO_ROOT/claude" 2>/dev/null | wc -l)
  if [[ "$LEAK" -eq 0 ]]; then
    echo "  [pass] no personal data leaks"
  else
    echo "  [fail] $LEAK personal data references in claude/"
    FAIL=1
  fi
fi

echo
if [[ "$FAIL" -gt 0 ]]; then
  echo "Verification FAILED"
  exit 1
fi
echo "Verification PASSED"