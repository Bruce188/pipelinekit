#!/usr/bin/env bash
# Red-phase contract test for plan-v25 Task 1.5 / 1.6.
#
# Asserts that `claude/skills/pipeline/reference.md` contains a new sub-step
# 6.5 (Charter re-validation) inserted between the existing
# "Renewed feature file:" log line (current Step 6) and the existing
# "Proceed to Step 2 with `docs/features-renewed.md`" line (current Step 7).
#
# The test pins six conditions:
#   1. A line that begins with `6.5.` followed by whitespace exists.
#   2. The skip-log token `CHARTER_REVALIDATE: skipped` appears.
#   3. The clean-log token `CHARTER_REVALIDATE: clean` appears.
#   4. The AskUserQuestion option label `Edit charter` appears.
#   5. The AskUserQuestion option label `Drop feature` appears.
#   6. Line-number ordering: line(Renewed feature file) < line(6.5.) <
#      line(Proceed to Step 2 with `docs/features-renewed.md`).
#
# This test MUST fail on base `main` (reference.md has no sub-step 6.5 yet)
# and MUST pass once Task 1.6 inserts the block.

set -euo pipefail

REF="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/reference.md"

if [ ! -f "$REF" ]; then
  echo "FAIL reference.md not found at $REF"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 1: sub-step 6.5 header line exists.
# ---------------------------------------------------------------------------
if ! grep -E '^6\.5\.[[:space:]]+' "$REF" >/dev/null; then
  echo "FAIL reference.md is missing the sub-step 6.5 header line (expected a line matching '^6\.5\.[[:space:]]+' in $REF)"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 2: skip-condition log token.
# ---------------------------------------------------------------------------
if ! grep -q 'CHARTER_REVALIDATE: skipped' "$REF"; then
  echo "FAIL reference.md is missing the skip-condition log token 'CHARTER_REVALIDATE: skipped'"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 3: clean-drift log token.
# ---------------------------------------------------------------------------
if ! grep -q 'CHARTER_REVALIDATE: clean' "$REF"; then
  echo "FAIL reference.md is missing the empty-drift log token 'CHARTER_REVALIDATE: clean'"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 4: AskUserQuestion 'Edit charter' option label.
# ---------------------------------------------------------------------------
if ! grep -q 'Edit charter' "$REF"; then
  echo "FAIL reference.md is missing the AskUserQuestion option label 'Edit charter'"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 5: AskUserQuestion 'Drop feature' option label.
# ---------------------------------------------------------------------------
if ! grep -q 'Drop feature' "$REF"; then
  echo "FAIL reference.md is missing the AskUserQuestion option label 'Drop feature'"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion 6: section ordering --- line(6) < line(6.5) < line(7).
# ---------------------------------------------------------------------------
L6="$(grep -n 'Renewed feature file:' "$REF" | head -1 | cut -d: -f1 || true)"
L65="$(grep -nE '^6\.5\.' "$REF" | head -1 | cut -d: -f1 || true)"
L7="$(grep -n 'Proceed to Step 2 with `docs/features-renewed.md`' "$REF" | head -1 | cut -d: -f1 || true)"

if [ -z "$L6" ]; then
  echo "FAIL could not locate the 'Renewed feature file:' anchor (current Step 6) in reference.md"
  exit 1
fi
if [ -z "$L65" ]; then
  echo "FAIL could not locate the sub-step 6.5 header line (regex '^6\.5\.') in reference.md"
  exit 1
fi
if [ -z "$L7" ]; then
  echo "FAIL could not locate the 'Proceed to Step 2 with \`docs/features-renewed.md\`' anchor (current Step 7) in reference.md"
  exit 1
fi

if ! [[ "$L6" -lt "$L65" && "$L65" -lt "$L7" ]]; then
  echo "FAIL section ordering violated: expected L6 < L65 < L7, got L6=$L6 L65=$L65 L7=$L7"
  exit 1
fi

echo "OK: test_reference_substep_65.sh"
exit 0
