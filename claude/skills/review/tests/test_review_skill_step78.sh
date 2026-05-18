#!/usr/bin/env bash
set -euo pipefail

# Red-phase contract test for Step 7.8 of claude/skills/review/SKILL.md
# Asserts that the replacement block contains the canonical tokens for the
# charter-aware classifier (Task 1.6) AND that the 5-agent review panel
# composition referenced elsewhere in SKILL.md remains intact.
#
# Today (base main) this MUST fail: the current Step 7.8 uses hyphenated
# "out-of-scope" and lacks every other new token.

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md

# 1. Python module name appears.
grep -q 'charter_classifier' "$SKILL" || {
  echo "FAIL: 'charter_classifier' not found in $SKILL — Step 7.8 must invoke the Python module."
  exit 1
}

# 2. Decorating field name appears.
grep -q 'scope_tag' "$SKILL" || {
  echo "FAIL: 'scope_tag' not found in $SKILL — Step 7.8 must reference the decorating field."
  exit 1
}

# 3. Canonical skip-log token appears.
grep -q 'CHARTER_ABSENT_CLASSIFIER_SKIPPED' "$SKILL" || {
  echo "FAIL: 'CHARTER_ABSENT_CLASSIFIER_SKIPPED' not found in $SKILL — canonical skip-log token must appear."
  exit 1
}

# 4. Underscore-form scope tag literal appears (replaces old hyphenated form).
grep -q 'out_of_scope' "$SKILL" || {
  echo "FAIL: 'out_of_scope' (underscore form) not found in $SKILL — old hyphenated 'out-of-scope' must be replaced."
  exit 1
}

# 5. Skip-gate function name appears (anchors the Python heredoc).
grep -q 'classifier_should_skip' "$SKILL" || {
  echo "FAIL: 'classifier_should_skip' not found in $SKILL — skip-gate function name must anchor the Python heredoc."
  exit 1
}

# 6. 5-agent panel intact.
for agent in code-reviewer security-auditor test-engineer performance-tuner spec-tracer; do
  grep -q "$agent" "$SKILL" || { echo "FAIL: missing agent $agent in SKILL.md"; exit 1; }
done

# 7. Old phrase removed (negative assertion).
if grep -q "partial string match on the finding" "$SKILL"; then
  echo "FAIL: old phrase 'partial string match on the finding' still present in $SKILL — Step 7.8 must be replaced, not augmented."
  exit 1
fi

echo "OK: test_review_skill_step78.sh"
exit 0
