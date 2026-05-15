#!/bin/bash
# Blocks worktree agents that finish without committing.
# Called by SubagentStop hook — checks if the agent's worktree has uncommitted changes.
# Exits 2 (blocking) if uncommitted changes are found.

INPUT=$(cat)

# Check if this agent used a worktree (look for worktree path in agent output)
# Try known field names — log which one worked for diagnostics
LOG_DIR="$HOME/.claude/logs"
mkdir -p "$LOG_DIR"
WORKTREE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
# Try candidate field names
for field in ('agent_worktree_path', 'worktree_path', 'worktreePath'):
    v = d.get(field, '')
    if v:
        print(v, file=sys.stderr)  # log which field matched
        print(v)
        break
else:
    print('')
" 2>"$LOG_DIR/worktree-field-debug.log")

# If no worktree path, this wasn't a worktree agent — skip
[ -z "$WORKTREE_PATH" ] && exit 0

# Validate worktree path starts with expected prefix (canonicalized)
RESOLVED_PATH=$(realpath -m "$WORKTREE_PATH" 2>/dev/null) || { echo "WARNING: Cannot resolve worktree path: $WORKTREE_PATH" >&2; exit 0; }
EXPECTED_PREFIX="$HOME/.claude/worktrees/"
case "$RESOLVED_PATH" in
  "$EXPECTED_PREFIX"*) ;; # valid worktree path
  *) echo "WARNING: Unexpected worktree path: $WORKTREE_PATH (resolved: $RESOLVED_PATH)" >&2; exit 0 ;;
esac

# Check if worktree has uncommitted changes
if [ -d "$WORKTREE_PATH" ]; then
  cd "$WORKTREE_PATH" 2>/dev/null || exit 0
  DIRTY=$(git status --porcelain 2>/dev/null)
  if [ -n "$DIRTY" ]; then
    echo "BLOCKED: Worktree agent finished with uncommitted changes at $WORKTREE_PATH" >&2
    echo "Agent must commit with 'wip: [description]' before reporting done." >&2
    echo "Recovery: cherry-pick or copy changes from $WORKTREE_PATH before cleanup." >&2
    exit 2
  fi
fi

exit 0
