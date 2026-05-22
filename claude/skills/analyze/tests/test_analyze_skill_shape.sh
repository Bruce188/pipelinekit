#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md

# Assertion 1: frontmatter name matches
grep -q '^name: analyze' "$SKILL" || { echo "FAIL: frontmatter 'name: analyze' not found"; exit 1; }

# Assertion 2: frontmatter description present
grep -q '^description:' "$SKILL" || { echo "FAIL: frontmatter 'description:' not found"; exit 1; }

# Assertion 3: frontmatter allowed-tools present
grep -q '^allowed-tools:' "$SKILL" || { echo "FAIL: frontmatter 'allowed-tools:' not found"; exit 1; }

# Assertion 4: Step 1 header present
grep -q '### Step 1: Scope Interview' "$SKILL" || { echo "FAIL: 'Step 1: Scope Interview' header not found"; exit 1; }

# Assertion 5: Step 3 header present
grep -q '### Step 3: Read Existing Context' "$SKILL" || { echo "FAIL: 'Step 3: Read Existing Context' header not found"; exit 1; }

# Assertion 6: Step 5 header present
grep -q '### Step 5: Write Analysis File' "$SKILL" || { echo "FAIL: 'Step 5: Write Analysis File' header not found"; exit 1; }

# Assertion 7: charter probe sentinel token present (CHARTER_FOUND or NO_CHARTER)
grep -q 'CHARTER_FOUND\|NO_CHARTER' "$SKILL" || { echo "FAIL: charter probe sentinel (CHARTER_FOUND/NO_CHARTER) not found"; exit 1; }

# Assertion 8: Analysis pointer update wording present
grep -q '\*\*Analysis:\*\*' "$SKILL" || { echo "FAIL: '**Analysis:**' pointer field not found"; exit 1; }

# Assertion 9: positional — Step 1 line precedes Step 5 line
STEP1_LINE=$(grep -n '### Step 1: Scope Interview' "$SKILL" | head -1 | cut -d: -f1)
STEP5_LINE=$(grep -n '### Step 5: Write Analysis File' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$STEP1_LINE" || -z "$STEP5_LINE" || "$STEP1_LINE" -ge "$STEP5_LINE" ]]; then
  echo "FAIL: Step 1 header not positioned before Step 5 header"
  exit 1
fi

echo "OK: test_analyze_skill_shape.sh"
exit 0
