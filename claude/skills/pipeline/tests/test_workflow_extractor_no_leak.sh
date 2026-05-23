#!/usr/bin/env bash
# Leak guard: plants 2 sentinel strings inside docs/charter.md § Goal and
# docs/analysis-v99.md reasoning prose, runs BOTH renderers, asserts NEITHER
# sentinel appears in the rendered HTML. Runs both modes (RICH then EMBEDDED).

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
EXTRACTOR="$ROOT/claude/lib/pipeline/workflow_extractor.py"
DASH="$ROOT/claude/lib/pipeline/dashboard_renderer.py"
DEC="$ROOT/claude/lib/pipeline/decisions_renderer.py"
PRUNER="$ROOT/claude/lib/pipeline/features_pruner.py"
RENDER="$ROOT/claude/skills/docs-writer/render.py"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir -p "$TMPDIR/docs" "$TMPDIR/docs-source" "$TMPDIR/documentation" \
         "$TMPDIR/claude/lib/pipeline" "$TMPDIR/claude/skills/docs-writer"
cp "$EXTRACTOR" "$TMPDIR/claude/lib/pipeline/"
cp "$DASH"      "$TMPDIR/claude/lib/pipeline/"
cp "$DEC"       "$TMPDIR/claude/lib/pipeline/"
cp "$PRUNER"    "$TMPDIR/claude/lib/pipeline/" 2>/dev/null || true
cp "$RENDER"    "$TMPDIR/claude/skills/docs-writer/"
cp -r "$ROOT/claude/skills/docs-writer/"*.html "$TMPDIR/claude/skills/docs-writer/" 2>/dev/null || true

SENTINEL_CHARTER="SECRET_SENTINEL_CHARTER_GOAL_42"
SENTINEL_ANALYSIS="SECRET_SENTINEL_ANALYSIS_OQ_REASONING_99"

cat > "$TMPDIR/docs/charter.md" <<EOF
# Charter
## Goal
$SENTINEL_CHARTER should never appear anywhere in the rendered HTML.
## Deployment target
any
## Review style
orchestrator decides
## Decision Log
| Date | Decision |
|------|----------|
EOF

cat > "$TMPDIR/docs/analysis-v99.md" <<EOF
---
version: 1
feature: feat/leak-guard-fixture
feature_index: 99/99
created: 2026-05-23
status: analyzed
---
# Analysis
The reasoning prose below contains $SENTINEL_ANALYSIS which MUST be stripped.
- OQ-1 resolved: short headline only — $SENTINEL_ANALYSIS in the body must NOT appear in HTML.
EOF

cat > "$TMPDIR/docs/pipeline-state.md" <<'EOF'
**Feature file:** docs/features.md
**Feature:** 99/99
**Name:** feat/leak-guard-fixture
**Step:** review
**Review cycles:** 0
**Replan count:** 0
EOF

cd "$TMPDIR"
git init -q
git add -A
git -c user.email=t@t -c user.name=t commit -q -m init

# RICH mode pass
python3 claude/lib/pipeline/dashboard_renderer.py >/dev/null 2>&1 || \
  { echo "FAIL: dashboard renderer non-zero (RICH)"; exit 1; }
python3 claude/lib/pipeline/decisions_renderer.py >/dev/null 2>&1 || \
  { echo "FAIL: decisions renderer non-zero (RICH)"; exit 1; }

if grep -q "$SENTINEL_CHARTER" documentation/dashboard.html; then
  echo "FAIL: charter sentinel leaked into dashboard.html (RICH mode)"
  exit 1
fi
if grep -q "$SENTINEL_CHARTER" documentation/decisions.html; then
  echo "FAIL: charter sentinel leaked into decisions.html (RICH mode)"
  exit 1
fi
if grep -q "$SENTINEL_ANALYSIS" documentation/dashboard.html; then
  echo "FAIL: analysis sentinel leaked into dashboard.html (RICH mode)"
  exit 1
fi
if grep -q "$SENTINEL_ANALYSIS" documentation/decisions.html; then
  echo "FAIL: analysis sentinel leaked into decisions.html (RICH mode)"
  exit 1
fi

# EMBEDDED mode pass — remove analysis file + plant sentinel in feature-history.md body
rm docs/analysis-v99.md
mkdir -p docs-source
cat > docs-source/feature-history.md <<EOF
# Feature History

## F99 — feat/leak-guard-fixture
Body prose mentions $SENTINEL_ANALYSIS which MUST stay out of HTML.

<details><summary>Decisions</summary>
- **OQ-1:** short headline only.
</details>
EOF
python3 claude/lib/pipeline/decisions_renderer.py >/dev/null 2>&1 || \
  { echo "FAIL: decisions renderer non-zero (EMBEDDED)"; exit 1; }
if grep -q "$SENTINEL_ANALYSIS" documentation/decisions.html; then
  echo "FAIL: analysis sentinel leaked into decisions.html (EMBEDDED mode)"
  exit 1
fi

echo "PASS: no sentinel leaks in either RICH or EMBEDDED mode."
