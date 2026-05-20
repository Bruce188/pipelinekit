#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
SKILL="${REPO_ROOT}/claude/skills/pipeline/SKILL.md"
CHARTER="${REPO_ROOT}/claude/skills/pipeline/charter.md"
ANALYZE="${REPO_ROOT}/claude/skills/analyze/SKILL.md"

fail() { echo "FAIL: $*" >&2; exit 1; }

# A1 — charter.md schema gains an OPTIONAL ## Stakeholders entry
grep -qE 'Stakeholders' "$CHARTER" \
  || fail "charter.md missing Stakeholders schema entry"

# A2 — charter.md question-bank carries the conditional-probe sub-section
grep -qE '^### Stakeholders \(conditional probe\)' "$CHARTER" \
  || fail "charter.md missing ### Stakeholders (conditional probe) sub-section"

# A3 — SKILL.md Step 0 carries the multi-party trigger vocabulary
for tok in teammate "customer segment" upstream downstream "external service"; do
  grep -qE "$tok" "$SKILL" \
    || fail "SKILL.md Step 0 missing trigger token: $tok"
done

# A4 — additive-only wording (optional / conditional) appears in charter.md
grep -qiE 'optional|conditional' "$CHARTER" \
  || fail "charter.md missing additive-only wording (optional/conditional)"

# A5 — /analyze reads ## Stakeholders
grep -qE '## Stakeholders' "$ANALYZE" \
  || fail "analyze/SKILL.md missing ## Stakeholders reader"

# A6 — backward-compat: Stakeholders NOT in the required-10 numbered list
# (rough heuristic: search for the canonical 10-topic enumeration and
# confirm Stakeholders is NOT listed alongside Goal/Users/Problem/etc.)
if grep -qE '^(- |[0-9]+\. )Stakeholders\b' "$CHARTER"; then
  fail "charter.md required-10 list erroneously includes Stakeholders"
fi

echo "OK: test_charter_stakeholders_section"
exit 0
