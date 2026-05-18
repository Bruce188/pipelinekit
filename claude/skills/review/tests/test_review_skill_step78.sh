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

# 8. FINDINGS_JSON variable initialized before the heredoc fires (B2 fix).
# Either a shell assignment `FINDINGS_JSON=...` or a mktemp assignment line
# must appear in the SKILL.md Step 7.8 block. The heredoc calls
# `python3 - "$FINDINGS_JSON" ...` — if $FINDINGS_JSON is never set, the
# open() inside the heredoc gets an empty path and crashes.
if ! grep -qE 'FINDINGS_JSON=\$\(mktemp\)|FINDINGS_JSON=' "$SKILL"; then
  echo "FAIL: FINDINGS_JSON is not initialized in $SKILL — Step 7.8 must assign the variable before the heredoc runs."
  exit 1
fi

# 9. REVIEW_FILE_NAME variable initialized (B2 fix — review filename argument).
# The Python heredoc calls append_out_of_scope_to_deferred(..., sys.argv[2])
# where sys.argv[2] is "$REVIEW_FILE_NAME". Without the assignment the Source
# column in the Deferred table is empty.
if ! grep -qE 'REVIEW_FILE_NAME=' "$SKILL"; then
  echo "FAIL: REVIEW_FILE_NAME is not initialized in $SKILL — Step 7.8 must assign the variable before the heredoc runs."
  exit 1
fi

# 10. FINDINGS_LIST_PYTHON either absent or assigned before the heredoc.
# The B2 fix introduced a pre-heredoc shim that serializes the in-memory list
# to $FINDINGS_JSON. NB1 found that the shim used $FINDINGS_LIST_PYTHON as an
# intermediate variable but Step 7 never assigns it, causing a SyntaxError at
# runtime. Option 2 removes the variable entirely (cleaner); Option 1 assigns
# it before the heredoc. This assertion parametrizes on the choice:
# - If the variable is present, it MUST be assigned (= sign) before the heredoc.
# - If the variable is absent, the assertion passes unconditionally.
if grep -q 'FINDINGS_LIST_PYTHON' "$SKILL"; then
  # Variable still referenced — verify it has an assignment line before the heredoc.
  ASSIGN_LINE=$(grep -n 'FINDINGS_LIST_PYTHON=' "$SKILL" 2>/dev/null | head -1 | cut -d: -f1 || echo "")
  HEREDOC_LINE=$(grep -n "<<'PYEOF'" "$SKILL" | head -1 | cut -d: -f1)
  if [ -z "$ASSIGN_LINE" ]; then
    echo "FAIL: FINDINGS_LIST_PYTHON is referenced but never assigned in $SKILL (NB1 unfixed)"
    exit 1
  fi
  if [ "$ASSIGN_LINE" -gt "$HEREDOC_LINE" ]; then
    echo "FAIL: FINDINGS_LIST_PYTHON assignment (line $ASSIGN_LINE) must precede the heredoc (line $HEREDOC_LINE)"
    exit 1
  fi
fi

# 11. two_axis=True kwarg flows to classify_findings.
grep -q 'two_axis=True' "$SKILL" || {
  echo "FAIL: 'two_axis=True' not found in $SKILL — Step 7.8 must pass two_axis kwarg."
  exit 1
}

# 12. CHARTER_SCOPE_CONFLICT token is caught + emitted to stderr.
grep -q 'CHARTER_SCOPE_CONFLICT' "$SKILL" || {
  echo "FAIL: 'CHARTER_SCOPE_CONFLICT' not found in $SKILL — conflict token must be present."
  exit 1
}

# 13. Adjacent-advisory Summary line surfaces.
grep -q 'Charter scope adjacent' "$SKILL" || {
  echo "FAIL: 'Charter scope adjacent' not found in $SKILL — adjacent advisory line missing."
  exit 1
}

# 14. Two-axis worked-examples reference subsection exists.
grep -q 'Two-axis classification' "$SKILL" || {
  echo "FAIL: 'Two-axis classification' reference subsection missing in $SKILL."
  exit 1
}

echo "OK: test_review_skill_step78.sh"
exit 0
