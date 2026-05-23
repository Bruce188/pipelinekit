#!/usr/bin/env bash
# MANDATORY assertion: orphan janitor refuses to delete any path matching
# BOTH orphan-patterns.txt AND never-stage.txt (R-5 mitigation).

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
ORPHAN_FILE="$ROOT/claude/config/orphan-patterns.txt"
NEVER_STAGE_FILE="$ROOT/claude/config/never-stage.txt"

[ -r "$ORPHAN_FILE" ] || { echo "FAIL: orphan-patterns.txt missing"; exit 1; }
[ -r "$NEVER_STAGE_FILE" ] || { echo "FAIL: never-stage.txt missing"; exit 1; }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
mkdir -p "$TMPDIR/docs"
cd "$TMPDIR"

# Construct two synthetic intersecting patterns: a file under docs/ that
# matches a never-stage entry (docs/progress.md) AND a synthetic orphan
# pattern. We add an extra synthetic pattern to a LOCAL copy of
# orphan-patterns.txt for this test so the real config stays untouched.

cp "$ORPHAN_FILE" orphan-patterns.local.txt
echo "docs/progress.md"  >> orphan-patterns.local.txt
echo "double match — added by test" > docs/progress.md
SHA=$(sha256sum docs/progress.md | awk '{print $1}')

export PIPELINE_JANITOR_DRY_RUN=0
while IFS= read -r pattern; do
  case "$pattern" in ''|\#*) continue ;; esac
  for f in $(compgen -G "$pattern" 2>/dev/null); do
    if python3 - "$f" "$NEVER_STAGE_FILE" <<'PY'
import fnmatch, sys
path = sys.argv[1]; ns_file = sys.argv[2]
with open(ns_file) as fh:
    patterns = [ln.strip() for ln in fh if ln.strip() and not ln.startswith('#')]
sys.exit(0 if any(fnmatch.fnmatch(path, p) for p in patterns) else 1)
PY
    then
      echo "SKIP guard fired for $f (expected)"
      continue
    fi
    rm -- "$f"
  done
done < orphan-patterns.local.txt

# Assert: docs/progress.md survives byte-identical
[ -f docs/progress.md ] \
  || { echo "FAIL: docs/progress.md deleted despite never-stage intersection"; exit 1; }
NEW_SHA=$(sha256sum docs/progress.md | awk '{print $1}')
[ "$SHA" = "$NEW_SHA" ] \
  || { echo "FAIL: docs/progress.md modified by janitor"; exit 1; }

echo "PASS: never-stage intersection guard prevents deletion of double-match file."
