#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md

# Assertion 1: charter_extractor module name appears in new Step 0 sub-step or pointer
grep -q 'charter_extractor' "$SKILL" || { echo "FAIL: 'charter_extractor' not found in SKILL.md"; exit 1; }

# Assertion 2: canonical skip-log token appears
grep -q 'CHARTER_AUTO_EXTRACT_SKIPPED' "$SKILL" || { echo "FAIL: 'CHARTER_AUTO_EXTRACT_SKIPPED' token not found in SKILL.md"; exit 1; }

# Assertion 3: descriptive word 'auto-extract' appears
grep -q 'auto-extract' "$SKILL" || { echo "FAIL: 'auto-extract' not found in SKILL.md"; exit 1; }

# Assertion 4: skip-condition ladder length floor (>= 5 numbered entries)
count=$(grep -cE '^[0-9]+\.[ \t]+' "$SKILL")
[[ "$count" -ge 5 ]] || { echo "FAIL: skip-condition ladder count too low ($count, expected >= 5)"; exit 1; }

# Assertion 5: positional grep — auto-extract entry appears before existing docs/charter.md-exists condition
# The condition text uses backtick-wrapped path: `docs/charter.md` exists (backtick before space)
AUTO_LINE=$(grep -n 'charter_extractor' "$SKILL" | head -1 | cut -d: -f1)
COND5_LINE=$(grep -n 'charter.md.*exists AND' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$AUTO_LINE" || -z "$COND5_LINE" || "$AUTO_LINE" -ge "$COND5_LINE" ]]; then
  echo "FAIL: auto-extract entry not positioned before existing docs/charter.md-exists condition"
  exit 1
fi

# Assertion 6: existing skip-conditions preserved
for token in '--no-charter' '--charter <path>' '--max-questions 0'; do
  grep -q -- "$token" "$SKILL" || { echo "FAIL: existing skip-condition token missing: $token"; exit 1; }
done

# Assertion 7: subprocess-mode language preserved
grep -q 'subprocess mode' "$SKILL" || grep -q 'Subprocess mode' "$SKILL" || { echo "FAIL: subprocess mode paragraph removed from SKILL.md"; exit 1; }

# Assertion 8: reference.md pointer adjacent to the new entry
grep -B 5 -A 5 'charter_extractor' "$SKILL" | grep -q 'reference.md' || { echo "FAIL: reference.md pointer not adjacent to charter_extractor mention in SKILL.md"; exit 1; }

echo "OK: test_step0_auto_extract.sh"
exit 0
