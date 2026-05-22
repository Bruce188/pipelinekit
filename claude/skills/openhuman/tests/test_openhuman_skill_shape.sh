#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md
SKILL_DIR=$(dirname "$SKILL")

# Assertion 1: frontmatter name matches
grep -q '^name: openhuman' "$SKILL" || { echo "FAIL: frontmatter 'name: openhuman' not found"; exit 1; }

# Assertion 2: frontmatter description present
grep -q '^description:' "$SKILL" || { echo "FAIL: frontmatter 'description:' not found"; exit 1; }

# Assertion 3: frontmatter disable-model-invocation present
grep -q '^disable-model-invocation: true' "$SKILL" || { echo "FAIL: frontmatter 'disable-model-invocation: true' not found"; exit 1; }

# Assertion 4: PIPELINE_HUMAN_REVIEW sentinel present
grep -q 'PIPELINE_HUMAN_REVIEW' "$SKILL" || { echo "FAIL: 'PIPELINE_HUMAN_REVIEW' sentinel not found"; exit 1; }

# Assertion 5: permissionDecision sentinel present
grep -q 'permissionDecision' "$SKILL" || { echo "FAIL: 'permissionDecision' sentinel not found"; exit 1; }

# Assertion 6: OPENHUMAN_TIMEOUT sentinel present
grep -q 'OPENHUMAN_TIMEOUT' "$SKILL" || { echo "FAIL: 'OPENHUMAN_TIMEOUT' sentinel not found"; exit 1; }

# Assertion 7: OPENHUMAN_MALFORMED_SIGNAL sentinel present
grep -q 'OPENHUMAN_MALFORMED_SIGNAL' "$SKILL" || { echo "FAIL: 'OPENHUMAN_MALFORMED_SIGNAL' sentinel not found"; exit 1; }

# Assertion 8: handler.sh file exists alongside SKILL.md
test -f "$SKILL_DIR/handler.sh" || { echo "FAIL: handler.sh not found at $SKILL_DIR/handler.sh"; exit 1; }

# Assertion 9: positional — PIPELINE_HUMAN_REVIEW line precedes OPENHUMAN_TIMEOUT line
HR_LINE=$(grep -n 'PIPELINE_HUMAN_REVIEW' "$SKILL" | head -1 | cut -d: -f1)
TO_LINE=$(grep -n 'OPENHUMAN_TIMEOUT' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$HR_LINE" || -z "$TO_LINE" || "$HR_LINE" -ge "$TO_LINE" ]]; then
  echo "FAIL: PIPELINE_HUMAN_REVIEW not positioned before OPENHUMAN_TIMEOUT"
  exit 1
fi

echo "OK: test_openhuman_skill_shape.sh"
exit 0
