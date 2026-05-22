#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md

# Assertion 1: frontmatter name matches
grep -q '^name: ppr' "$SKILL" || { echo "FAIL: frontmatter 'name: ppr' not found"; exit 1; }

# Assertion 2: frontmatter description present
grep -q '^description:' "$SKILL" || { echo "FAIL: frontmatter 'description:' not found"; exit 1; }

# Assertion 3: frontmatter allowed-tools present
grep -q '^allowed-tools:' "$SKILL" || { echo "FAIL: frontmatter 'allowed-tools:' not found"; exit 1; }

# Assertion 4: Step 1 header present
grep -q '### Step 1: Safety Checks' "$SKILL" || { echo "FAIL: 'Step 1: Safety Checks' header not found"; exit 1; }

# Assertion 5: Step 3 header present (Create Pull Request)
grep -q '### Step 3: Create Pull Request' "$SKILL" || { echo "FAIL: 'Step 3: Create Pull Request' header not found"; exit 1; }

# Assertion 6: charter probe sentinel token present
grep -q 'CHARTER_FOUND\|NO_CHARTER' "$SKILL" || { echo "FAIL: charter probe sentinel (CHARTER_FOUND/NO_CHARTER) not found"; exit 1; }

# Assertion 7: CHARTER_GOAL_LINE sentinel present
grep -q 'CHARTER_GOAL_LINE' "$SKILL" || { echo "FAIL: 'CHARTER_GOAL_LINE' sentinel not found"; exit 1; }

# Assertion 8: Review pointer field wording present
grep -q '\*\*Review:\*\*' "$SKILL" || { echo "FAIL: '**Review:**' pointer field not found"; exit 1; }

# Assertion 9: positional — Step 1 line precedes Step 3 line
STEP1_LINE=$(grep -n '### Step 1: Safety Checks' "$SKILL" | head -1 | cut -d: -f1)
STEP3_LINE=$(grep -n '### Step 3: Create Pull Request' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$STEP1_LINE" || -z "$STEP3_LINE" || "$STEP1_LINE" -ge "$STEP3_LINE" ]]; then
  echo "FAIL: Step 1 header not positioned before Step 3 header"
  exit 1
fi

echo "OK: test_ppr_skill_shape.sh"
exit 0
