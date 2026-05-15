#!/bin/bash
# Blocks direct pushes to main/master. Use feature branches.
# Called by PreToolUse hook — receives tool input on stdin.

INPUT=$(cat)

# Ensure python3 is available
command -v python3 >/dev/null || { echo "WARNING: python3 not found — block-push-main.sh cannot parse input" >&2; exit 0; }

COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

# Only check git push commands (handle chained commands: && ; ||)
echo "$COMMAND" | grep -qE '(^|\s*&&\s*|\s*;\s*|\s*\|\|\s*)git push' || exit 0

# Block pushes targeting main or master (catches all patterns):
# git push origin main, git push origin HEAD:main, git push origin feature:main,
# git push --force origin main, git push -u origin main
if echo "$COMMAND" | grep -qE "(git push\s+(-[a-zA-Z]+\s+)*\S+\s+(main|master)(\s|$))|(:(main|master)(\s|$))"; then
  echo "BLOCKED: Direct push to main/master. Use a feature branch." >&2
  exit 2
fi

exit 0
