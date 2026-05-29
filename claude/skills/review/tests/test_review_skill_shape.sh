#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md
SKILLD=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Assertion 1: frontmatter name matches
grep -q '^name: pipeline-review' "$SKILL" || { echo "FAIL: frontmatter 'name: pipeline-review' not found"; exit 1; }

# Assertion 2: frontmatter description present
grep -q '^description:' "$SKILL" || { echo "FAIL: frontmatter 'description:' not found"; exit 1; }

# Assertion 3: frontmatter allowed-tools present
grep -q '^allowed-tools:' "$SKILL" || { echo "FAIL: frontmatter 'allowed-tools:' not found"; exit 1; }

# Assertion 4: Step 1 header present
grep -q '### Step 1: Detect Project Type and Base Branch' "$SKILL" || { echo "FAIL: 'Step 1: Detect Project Type and Base Branch' header not found"; exit 1; }

# Assertion 5: Step 6 header present (Spawn Review Agents)
grep -q '### Step 6: Spawn Review Agents' "$SKILL" || { echo "FAIL: 'Step 6: Spawn Review Agents' header not found"; exit 1; }

# Assertion 6: 5-agent panel names present
grep -q 'code-reviewer' "$SKILLD"/*.md || { echo "FAIL: 'code-reviewer' agent name not found"; exit 1; }
grep -q 'security-auditor' "$SKILLD"/*.md || { echo "FAIL: 'security-auditor' agent name not found"; exit 1; }
grep -q 'spec-tracer' "$SKILLD"/*.md || { echo "FAIL: 'spec-tracer' agent name not found"; exit 1; }

# Assertion 7: Review pointer field wording present
grep -q '\*\*Review:\*\*' "$SKILLD"/*.md || { echo "FAIL: '**Review:**' pointer field not found"; exit 1; }

# Assertion 8: Plan pointer wording present (review reads progress.md Plan field)
grep -q '\*\*Plan:\*\*' "$SKILLD"/*.md || { echo "FAIL: '**Plan:**' pointer field not found"; exit 1; }

# Assertion 9: positional — Step 1 line precedes Step 6 line
STEP1_LINE=$(grep -n '### Step 1: Detect Project Type and Base Branch' "$SKILL" | head -1 | cut -d: -f1)
STEP6_LINE=$(grep -n '### Step 6: Spawn Review Agents' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$STEP1_LINE" || -z "$STEP6_LINE" || "$STEP1_LINE" -ge "$STEP6_LINE" ]]; then
  echo "FAIL: Step 1 header not positioned before Step 6 header"
  exit 1
fi

echo "OK: test_review_skill_shape.sh"
exit 0
