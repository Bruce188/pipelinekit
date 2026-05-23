#!/usr/bin/env bash
# Smoke test for claude/lib/pipeline/features_pruner.py (SubQ-A, SubQ-D).
# Builds a synthetic 3-feature features.md (1 done, 2 active), runs the
# pruner against a temp working tree, and asserts the done block moved
# out + feature-history.md gained one section. Also asserts idempotency
# (second run is a no-op for already-pruned blocks) and PIPELINE_HYGIENE_OFF=1
# is a true no-op.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
PRUNER="$ROOT/claude/lib/pipeline/features_pruner.py"
RENDER="$ROOT/claude/skills/docs-writer/render.py"

[ -r "$PRUNER" ] || { echo "FAIL: features_pruner.py missing"; exit 1; }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Build a synthetic repo layout
mkdir -p "$TMPDIR/docs" "$TMPDIR/docs-source" "$TMPDIR/documentation" \
         "$TMPDIR/claude/lib/pipeline" "$TMPDIR/claude/skills/docs-writer" \
         "$TMPDIR/claude/config"
cp "$PRUNER" "$TMPDIR/claude/lib/pipeline/features_pruner.py"
cp "$RENDER" "$TMPDIR/claude/skills/docs-writer/render.py"
# template.html dependency may not be loadable; pruner tolerates render failures.
cp -r "$ROOT/claude/skills/docs-writer/"*.html "$TMPDIR/claude/skills/docs-writer/" 2>/dev/null || true
cp "$ROOT/claude/config/never-stage.txt" "$TMPDIR/claude/config/never-stage.txt" 2>/dev/null || true

cat > "$TMPDIR/docs/features.md" <<'EOF'
# Features

## feat/active-one
- spec: Build X.

## fix/done-block
- spec: Fix Y.

### Run Log
- ppr-done — PR #999 squashed (abc1234)

## chore/active-two
- spec: Chore Z.
EOF

# Make $TMPDIR a git repo so `git rev-parse --show-toplevel` works inside the pruner.
cd "$TMPDIR"
git init -q
git add -A
git -c user.email=t@t -c user.name=t commit -q -m init

# Run 1: should move 1 done block out
python3 claude/lib/pipeline/features_pruner.py >/tmp/pruner-out.log 2>&1 || true
grep -q "1 merged blocks detected" /tmp/pruner-out.log \
  || { echo "FAIL (run 1): expected '1 merged blocks detected' in output"; cat /tmp/pruner-out.log; exit 1; }

# Assertion 1: features.md retains 2 active blocks; done block gone
ACTIVE_COUNT=$(grep -c '^## ' docs/features.md)
[ "$ACTIVE_COUNT" -eq 2 ] \
  || { echo "FAIL: expected 2 active H2 blocks in features.md (got $ACTIVE_COUNT)"; cat docs/features.md; exit 1; }
if grep -q 'fix/done-block' docs/features.md; then
  echo "FAIL: done block 'fix/done-block' still in features.md"
  exit 1
fi
grep -q 'feat/active-one' docs/features.md \
  || { echo "FAIL: active block 'feat/active-one' lost"; exit 1; }
grep -q 'chore/active-two' docs/features.md \
  || { echo "FAIL: active block 'chore/active-two' lost"; exit 1; }

# Assertion 2: feature-history.md gained one H2 section
[ -f docs-source/feature-history.md ] \
  || { echo "FAIL: feature-history.md not created"; exit 1; }
grep -q 'fix/done-block' docs-source/feature-history.md \
  || { echo "FAIL: done block not in feature-history.md"; exit 1; }
if ! grep -q '<details>' docs-source/feature-history.md; then
  echo "FAIL: history section missing <details> richness primitive"
  exit 1
fi

# Assertion 3: features.md NOT deleted (SubQ-D — never-stage intersection)
[ -f docs/features.md ] \
  || { echo "FAIL: docs/features.md was deleted (never-stage intersection violated)"; exit 1; }

# Run 2: idempotent (already-present block not re-appended)
HISTORY_SHA_BEFORE=$(sha256sum docs-source/feature-history.md | awk '{print $1}')
python3 claude/lib/pipeline/features_pruner.py >/tmp/pruner-out2.log 2>&1 || true
HISTORY_SHA_AFTER=$(sha256sum docs-source/feature-history.md | awk '{print $1}')
[ "$HISTORY_SHA_BEFORE" = "$HISTORY_SHA_AFTER" ] \
  || { echo "FAIL: idempotency violated — feature-history.md changed on second run"; exit 1; }

# Run 3: PIPELINE_HYGIENE_OFF=1 is a no-op
if ! PIPELINE_HYGIENE_OFF=1 python3 claude/lib/pipeline/features_pruner.py 2>&1 | tee /tmp/pruner-out3.log | grep -q 'skipped'; then
  echo "FAIL: PIPELINE_HYGIENE_OFF=1 did not skip"
  cat /tmp/pruner-out3.log
  exit 1
fi

echo "PASS: pruner moves done blocks, preserves active blocks, idempotent, honours opt-out, never-stage intersection holds."
