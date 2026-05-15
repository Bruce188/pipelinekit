#!/bin/bash
# Stop hook: warns about incomplete state before agent finishes.
# Always exits 0 — warns, never blocks.

# Drain stdin (hook protocol)
cat > /dev/null

# 1. Check for tasks still in "doing" state
if [ -f docs/progress.md ]; then
  DOING_COUNT=$(grep -c '\bdoing\b' docs/progress.md 2>/dev/null || echo 0)
  if [ "$DOING_COUNT" -gt 0 ]; then
    echo "WARNING: $DOING_COUNT task(s) still in 'doing' state. Agent may be stopping prematurely." >&2
  fi
fi

# 2. Check for uncommitted/untracked changes (git status --porcelain catches both)
DIRTY=$(git status --porcelain 2>/dev/null)
if [ -n "$DIRTY" ]; then
  FILE_COUNT=$(echo "$DIRTY" | wc -l)
  echo "WARNING: $FILE_COUNT uncommitted/untracked file(s). Consider committing before stopping." >&2
fi

exit 0
