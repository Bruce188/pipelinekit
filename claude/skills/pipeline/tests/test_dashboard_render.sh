#!/usr/bin/env bash
# Smoke test for claude/lib/pipeline/dashboard_renderer.py.
# Synthesizes a minimal repo + pipeline-state.md, runs the renderer, asserts
# the 12 sections + Generated timestamp + cross-link + idempotency + opt-out.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
EXTRACTOR="$ROOT/claude/lib/pipeline/workflow_extractor.py"
RENDERER="$ROOT/claude/lib/pipeline/dashboard_renderer.py"
RENDER="$ROOT/claude/skills/docs-writer/render.py"

[ -r "$EXTRACTOR" ] || { echo "FAIL: workflow_extractor.py missing"; exit 1; }
[ -r "$RENDERER" ]  || { echo "FAIL: dashboard_renderer.py missing"; exit 1; }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir -p "$TMPDIR/docs" "$TMPDIR/docs-source" "$TMPDIR/documentation" \
         "$TMPDIR/claude/lib/pipeline" "$TMPDIR/claude/skills/docs-writer" \
         "$TMPDIR/claude/config"
cp "$EXTRACTOR" "$TMPDIR/claude/lib/pipeline/"
cp "$RENDERER"  "$TMPDIR/claude/lib/pipeline/"
cp "$RENDER"    "$TMPDIR/claude/skills/docs-writer/"
cp -r "$ROOT/claude/skills/docs-writer/"*.html "$TMPDIR/claude/skills/docs-writer/" 2>/dev/null || true

cat > "$TMPDIR/docs/pipeline-state.md" <<'EOF'
**Feature file:** docs/features.md
**Feature:** 13/13
**Name:** feat/dashboard-and-decisions-log
**Step:** review
**Review cycles:** 0
**Replan count:** 0
**Started:** 2026-05-23T08:00:00Z
**Max USD:** unlimited
**Max turns:** unlimited
**Phase Mode:** subagent
EOF

cat > "$TMPDIR/docs/features.md" <<'EOF'
# Features
## feat/dashboard-and-decisions-log
[PIPELINE] feat=13/13 step=plan cycle=0 worker=claude :: plan-start
[PIPELINE] feat=13/13 step=plan cycle=0 worker=claude :: plan-done
EOF

cat > "$TMPDIR/docs/charter.md" <<'EOF'
# Charter
## Goal
test goal
## Deployment target
any
## Review style
orchestrator decides
## Decision Log
| Date | Decision |
|------|----------|
| 2026-05-23 | sample |
EOF

cd "$TMPDIR"
git init -q
git add -A
git -c user.email=t@t -c user.name=t commit -q -m init

# Run 1
python3 claude/lib/pipeline/dashboard_renderer.py >/tmp/dash-out.log 2>&1 || \
  { echo "FAIL: dashboard_renderer.py non-zero exit"; cat /tmp/dash-out.log; exit 1; }

# Assertion 1: outputs exist
[ -s docs-source/dashboard.md ] || { echo "FAIL: dashboard.md not written"; exit 1; }
[ -s documentation/dashboard.html ] || { echo "FAIL: dashboard.html not written"; exit 1; }

# Assertion 2: H2 sections 1-3 always-visible (>= 3 ## headers in markdown)
H2_COUNT=$(grep -c '^## ' docs-source/dashboard.md)
[ "$H2_COUNT" -ge 3 ] || { echo "FAIL: expected >= 3 H2 sections (got $H2_COUNT)"; exit 1; }

# Assertion 3: sections 4-12 are <details> collapsibles (>= 9)
DETAILS_COUNT=$(grep -c '<details>' docs-source/dashboard.md)
[ "$DETAILS_COUNT" -ge 9 ] || { echo "FAIL: expected >= 9 <details> sections (got $DETAILS_COUNT)"; exit 1; }

# Assertion 4: Generated timestamp present
grep -qE 'Generated: [0-9]{4}-[0-9]{2}-[0-9]{2}T' docs-source/dashboard.md \
  || { echo "FAIL: Generated ISO8601 timestamp missing"; exit 1; }

# Assertion 5: cross-link to decisions present
grep -q 'decisions.html' documentation/dashboard.html \
  || { echo "FAIL: cross-link to decisions.html missing"; exit 1; }

# Assertion 6: idempotency (md content stable on rerun)
SHA1=$(sha256sum docs-source/dashboard.md | awk '{print $1}')
python3 claude/lib/pipeline/dashboard_renderer.py >/dev/null 2>&1 || true
SHA2=$(sha256sum docs-source/dashboard.md | awk '{print $1}')
# Note: Generated timestamp changes — strip it for the idempotency check
DASH1=$(grep -v '^Generated:' docs-source/dashboard.md | sha256sum | awk '{print $1}')
python3 claude/lib/pipeline/dashboard_renderer.py >/dev/null 2>&1 || true
DASH2=$(grep -v '^Generated:' docs-source/dashboard.md | sha256sum | awk '{print $1}')
[ "$DASH1" = "$DASH2" ] || { echo "FAIL: idempotency violated (non-timestamp content drifted)"; exit 1; }

# Assertion 7: PIPELINE_HYGIENE_OFF=1 is no-op
PIPELINE_HYGIENE_OFF=1 python3 claude/lib/pipeline/dashboard_renderer.py 2>&1 | grep -q skipped \
  || { echo "FAIL: PIPELINE_HYGIENE_OFF=1 did not skip"; exit 1; }

# Assertion 8: wall-time budget (real time < 5s) — re-run via time
START=$(date +%s)
python3 claude/lib/pipeline/dashboard_renderer.py >/dev/null 2>&1 || true
END=$(date +%s)
DUR=$((END - START))
[ "$DUR" -lt 5 ] || { echo "FAIL: dashboard_renderer.py wall-time >= 5s ($DUR s)"; exit 1; }

echo "PASS: dashboard renderer emits 12 sections + Generated ts + cross-link, idempotent, honours opt-out, <5s budget."
