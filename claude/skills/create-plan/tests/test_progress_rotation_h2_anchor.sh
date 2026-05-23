#!/usr/bin/env bash
# Regression test for create-plan Step 5 dual-anchor rotation (OQ-1).
# Asserts the documented behaviour: BOTH `## Status` and `## Iteration:`
# H2 anchors are recognised as iteration-boundary markers.
#
# This test is doctrine-only: it inspects the SKILL.md prose, NOT a live
# rotator invocation (the rotator is described in prose, not a standalone
# script). Future enhancement: extract rotation into a helper and unit-test it.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
SKILL="$ROOT/claude/skills/create-plan/SKILL.md"

[ -f "$SKILL" ] || { echo "FAIL: SKILL.md not found at $SKILL"; exit 1; }

# Assert the Step 5 substep mentions both anchors.
grep -q 'Iteration-boundary anchors' "$SKILL" \
  || { echo "FAIL: 'Iteration-boundary anchors' substep marker not found in SKILL.md"; exit 1; }
grep -q '## Status' "$SKILL" \
  || { echo "FAIL: '## Status' anchor not mentioned"; exit 1; }
grep -q '## Iteration:' "$SKILL" \
  || { echo "FAIL: '## Iteration:' anchor not mentioned"; exit 1; }
grep -q 'OQ-1' "$SKILL" \
  || { echo "FAIL: OQ-1 reference missing — link prose to feature spec"; exit 1; }
grep -q 'no iteration-boundary H2 found' "$SKILL" \
  || { echo "FAIL: backwards-compat no-op clause missing"; exit 1; }

# Synthetic two-iteration fixture for documentation purposes.
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cat > "$TMPDIR/progress.md" <<'EOF'
# Progress

**Plan:** docs/plan.md
**Analysis:** docs/analysis.md

## Iteration: alpha
| Task | Status | Note |
|------|--------|------|
| 1.1  | done   | shipped |

## Iteration: bravo
| Task | Status | Note |
|------|--------|------|
| 1.1  | done   | shipped |

## Deferred
| Item | Source | Reason | Target |
|------|--------|--------|--------|
EOF

# Doctrine check: file has TWO `## Iteration:` H2 anchors.
ITER_COUNT=$(grep -c '^## Iteration:' "$TMPDIR/progress.md")
[ "$ITER_COUNT" -eq 2 ] \
  || { echo "FAIL: synthetic fixture should have exactly 2 ## Iteration: H2 anchors (got $ITER_COUNT)"; exit 1; }

echo "PASS: SKILL.md Step 5 documents dual-anchor recognition (## Status + ## Iteration:)."
