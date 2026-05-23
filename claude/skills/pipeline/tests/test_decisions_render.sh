#!/usr/bin/env bash
# Smoke test for claude/lib/pipeline/decisions_renderer.py.
# Synthesizes 2 analysis files (F12 + F13), runs the renderer, asserts both
# H2 cards appear with F13 BEFORE F12 (newest-first) + cross-link to dashboard.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
EXTRACTOR="$ROOT/claude/lib/pipeline/workflow_extractor.py"
RENDERER="$ROOT/claude/lib/pipeline/decisions_renderer.py"
RENDER="$ROOT/claude/skills/docs-writer/render.py"

[ -r "$EXTRACTOR" ] || { echo "FAIL: workflow_extractor.py missing"; exit 1; }
[ -r "$RENDERER" ]  || { echo "FAIL: decisions_renderer.py missing"; exit 1; }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir -p "$TMPDIR/docs" "$TMPDIR/docs-source" "$TMPDIR/documentation" \
         "$TMPDIR/claude/lib/pipeline" "$TMPDIR/claude/skills/docs-writer"
cp "$EXTRACTOR" "$TMPDIR/claude/lib/pipeline/"
cp "$RENDERER"  "$TMPDIR/claude/lib/pipeline/"
cp "$RENDER"    "$TMPDIR/claude/skills/docs-writer/"
cp -r "$ROOT/claude/skills/docs-writer/"*.html "$TMPDIR/claude/skills/docs-writer/" 2>/dev/null || true

cat > "$TMPDIR/docs/analysis-v90.md" <<'EOF'
---
version: 1
feature: feat/example-f12
feature_index: 12/13
created: 2026-05-22
status: analyzed
---
# Analysis
- OQ-1 resolved: chose option A over option B.
- OQ-2 resolved: kept default behaviour.
### SubQ-A
Hybrid mode chosen.
EOF

cat > "$TMPDIR/docs/analysis-v91.md" <<'EOF'
---
version: 1
feature: feat/example-f13
feature_index: 13/13
created: 2026-05-23
status: analyzed
---
# Analysis
- OQ-1 resolved: 12-section layout (larger).
- OQ-2 resolved: newest-first ordering.
### SubQ-A
RICH/EMBEDDED hybrid extractor.
EOF

cd "$TMPDIR"
git init -q
git add -A
git -c user.email=t@t -c user.name=t commit -q -m init

# Run 1
python3 claude/lib/pipeline/decisions_renderer.py >/tmp/dec-out.log 2>&1 || \
  { echo "FAIL: decisions_renderer.py non-zero exit"; cat /tmp/dec-out.log; exit 1; }

# Assertion 1: outputs exist
[ -s docs-source/decisions.md ] || { echo "FAIL: decisions.md not written"; exit 1; }
[ -s documentation/decisions.html ] || { echo "FAIL: decisions.html not written"; exit 1; }

# Assertion 2: both feature cards present
grep -q 'feat/example-f12' documentation/decisions.html \
  || { echo "FAIL: F12 card missing"; exit 1; }
grep -q 'feat/example-f13' documentation/decisions.html \
  || { echo "FAIL: F13 card missing"; exit 1; }

# Assertion 3: F13 appears BEFORE F12 (newest-first per OQ-2)
F13_POS=$(grep -n 'data-feature="13/13"\|feat/example-f13' documentation/decisions.html | head -1 | cut -d: -f1)
F12_POS=$(grep -n 'data-feature="12/13"\|feat/example-f12' documentation/decisions.html | head -1 | cut -d: -f1)
[ "$F13_POS" -lt "$F12_POS" ] \
  || { echo "FAIL: F13 should appear before F12 (newest-first); F13=$F13_POS F12=$F12_POS"; exit 1; }

# Assertion 4: cross-link to dashboard present
grep -q 'dashboard.html' documentation/decisions.html \
  || { echo "FAIL: cross-link to dashboard.html missing"; exit 1; }

# Assertion 5: per-OQ entries present
grep -q 'OQ-1' documentation/decisions.html \
  || { echo "FAIL: OQ-1 resolution entry missing"; exit 1; }

# Assertion 6: PIPELINE_HYGIENE_OFF=1 no-op
PIPELINE_HYGIENE_OFF=1 python3 claude/lib/pipeline/decisions_renderer.py 2>&1 | grep -q skipped \
  || { echo "FAIL: PIPELINE_HYGIENE_OFF=1 did not skip"; exit 1; }

# Assertion 7: EMBEDDED-mode fallback
rm "$TMPDIR/docs/analysis-v90.md" "$TMPDIR/docs/analysis-v91.md"
cat > "$TMPDIR/docs-source/feature-history.md" <<'EOF'
# Feature History

## F1 — feat/embedded-example
<details><summary>Decisions</summary>
- **OQ-1:** embedded mode example.
- **SubQ-A:** detected via fallback.
</details>
EOF
python3 claude/lib/pipeline/decisions_renderer.py >/dev/null 2>&1 || \
  { echo "FAIL: EMBEDDED mode run failed"; exit 1; }
grep -q 'feat/embedded-example' documentation/decisions.html \
  || { echo "FAIL: EMBEDDED-mode card missing"; exit 1; }

echo "PASS: decisions renderer emits newest-first cards, cross-links, both modes work, honours opt-out."
