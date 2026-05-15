#!/bin/bash
# Strips AI attribution from PRs after git push:
# 1. Removes 'claude-code-assisted' label
# 2. Removes any 'Co-authored-by:' lines from PR body
# Called by PostToolUse hook — receives tool input on stdin.

INPUT=$(cat)

# Shell pre-filter: skip Python parse for non-push commands (~99% of calls)
echo "$INPUT" | grep -q '"git push' || exit 0

COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

# Only act on git push commands (handle chained commands: && ; ||)
echo "$COMMAND" | grep -qE '(^|\s*&&\s*|\s*;\s*|\s*\|\|\s*)git push' || exit 0

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0

LOG_DIR="$HOME/.claude/logs"
LOG_FILE="$LOG_DIR/strip-ai-attribution.log"
mkdir -p "$LOG_DIR"

# Rotate when log > 1 MiB to prevent unbounded growth.
if [ -f "$LOG_FILE" ]; then
  LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
  if [ "${LOG_SIZE:-0}" -gt 1048576 ]; then
    mv "$LOG_FILE" "$LOG_FILE.1"
  fi
fi

# Run attribution cleanup in background — retry until PR is found (max 3 attempts)
(
  for i in 1 2 3; do
    PR_NUMBER=$(gh pr view "$BRANCH" --json number --jq '.number' 2>/dev/null)
    if [ -n "$PR_NUMBER" ]; then
      # Strip claude-code-assisted label
      gh pr edit "$PR_NUMBER" --remove-label "claude-code-assisted" 2>>"$LOG_FILE" || true

      # Strip Co-authored-by lines from PR body (using printf to avoid shell expansion)
      BODY=$(gh pr view "$PR_NUMBER" --json body --jq '.body' 2>/dev/null)
      if printf '%s' "$BODY" | grep -qi "co-authored-by"; then
        printf '%s' "$BODY" | python3 -c "import sys; print('\n'.join(l for l in sys.stdin.read().splitlines() if 'co-authored-by' not in l.lower()))" | gh pr edit "$PR_NUMBER" --body-file - 2>>"$LOG_FILE" || true
      fi
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stripped attribution from PR #$PR_NUMBER" >>"$LOG_FILE"
      break
    fi
    sleep 2
  done
  if [ -z "$PR_NUMBER" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: Could not find PR for branch $BRANCH after 3 attempts" >>"$LOG_FILE"
  fi
) &

exit 0
