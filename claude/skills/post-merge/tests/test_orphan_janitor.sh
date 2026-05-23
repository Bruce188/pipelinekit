#!/usr/bin/env bash
# Smoke test for /post-merge Step 12 orphan janitor (OQ-2).
# Asserts: 5 fake orphans matching claude/config/orphan-patterns.txt are
# removed; 2 protected files (progress.md + a plan-vN.md) survive byte-identical.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
ORPHAN_FILE="$ROOT/claude/config/orphan-patterns.txt"
NEVER_STAGE_FILE="$ROOT/claude/config/never-stage.txt"

[ -r "$ORPHAN_FILE" ] || { echo "FAIL: orphan-patterns.txt missing"; exit 1; }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
mkdir -p "$TMPDIR/docs"
cd "$TMPDIR"

# Five fake orphans (each matches an orphan-patterns.txt glob)
touch docs/pipeline-state.md.feature-1-done
touch docs/pipeline-state.md.feature-2-done
touch docs/features.md.feature-9-done
touch docs/pipeline-state.md.archived-1779519401
touch docs/RESUME.md

# Two protected files (do NOT match orphan-patterns.txt)
echo "progress content" > docs/progress.md
echo "plan content"     > docs/plan-v77.md
PROGRESS_SHA=$(sha256sum docs/progress.md | awk '{print $1}')
PLAN_SHA=$(sha256sum docs/plan-v77.md     | awk '{print $1}')

# Run janitor inline (transcribed from post-merge SKILL.md Step 12)
export PIPELINE_JANITOR_DRY_RUN=0
while IFS= read -r pattern; do
  case "$pattern" in ''|\#*) continue ;; esac
  for f in $(compgen -G "$pattern" 2>/dev/null); do
    if [ -r "$NEVER_STAGE_FILE" ]; then
      if python3 - "$f" "$NEVER_STAGE_FILE" <<'PY'
import fnmatch, sys
path = sys.argv[1]; ns_file = sys.argv[2]
with open(ns_file) as fh:
    patterns = [ln.strip() for ln in fh if ln.strip() and not ln.startswith('#')]
sys.exit(0 if any(fnmatch.fnmatch(path, p) for p in patterns) else 1)
PY
      then
        continue
      fi
    fi
    rm -- "$f"
  done
done < "$ORPHAN_FILE"

# Assert: 5 orphans removed
shopt -s nullglob
remaining_globs=( docs/pipeline-state.md.feature-* docs/features.md.feature-* \
                  docs/pipeline-state.md.archived-* )
shopt -u nullglob
ORPHANS_REMAINING=${#remaining_globs[@]}
if [ -e docs/RESUME.md ]; then ORPHANS_REMAINING=$((ORPHANS_REMAINING + 1)); fi
[ "$ORPHANS_REMAINING" -eq 0 ] \
  || { echo "FAIL: $ORPHANS_REMAINING orphan(s) survived (expected 0)"; exit 1; }

# Assert: protected files byte-identical
NEW_PROGRESS_SHA=$(sha256sum docs/progress.md | awk '{print $1}')
NEW_PLAN_SHA=$(sha256sum docs/plan-v77.md     | awk '{print $1}')
[ "$PROGRESS_SHA" = "$NEW_PROGRESS_SHA" ] \
  || { echo "FAIL: docs/progress.md modified by janitor"; exit 1; }
[ "$PLAN_SHA" = "$NEW_PLAN_SHA" ] \
  || { echo "FAIL: docs/plan-v77.md modified by janitor"; exit 1; }

echo "PASS: 5 orphans removed; progress.md + plan-v77.md untouched."
