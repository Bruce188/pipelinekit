#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SKILL="$SKILL_DIR/SKILL.md"
CHARTER="$SKILL_DIR/charter.md"
REFERENCE="$SKILL_DIR/reference.md"

# Assertion 1 (reconciled AC-1): exactly 4 new H3 topic headers (12-15)
TOPIC_COUNT=$(grep -cE "^### Topic (12|13|14|15):" "$CHARTER" || true)
if [[ "$TOPIC_COUNT" -ne 4 ]]; then
  echo "FAIL: expected 4 '### Topic (12|13|14|15):' headers in charter.md, got $TOPIC_COUNT"
  exit 1
fi
echo "OK: 4 new topic headers (12-15) present"

# Assertion 2 (reconciled AC-2, Risk-B): >= 4 AskUserQuestion mentions in charter.md
AUQ_COUNT=$(grep -c "AskUserQuestion" "$CHARTER" || true)
if [[ "$AUQ_COUNT" -lt 4 ]]; then
  echo "FAIL: expected >= 4 'AskUserQuestion' mentions in charter.md, got $AUQ_COUNT"
  exit 1
fi
echo "OK: AskUserQuestion mentions in charter.md >= 4 ($AUQ_COUNT)"

# Assertion 3 (reconciled AC-3, Risk-C): schema header bumped to "19 topics in order"
if ! grep -qE "^Required sections \(19 topics in order\)" "$CHARTER"; then
  echo "FAIL: 'Required sections (19 topics in order)' not found in charter.md"
  exit 1
fi
echo "OK: schema header reads '19 topics in order'"

# Assertion 4 (reconciled AC-3, Risk-C): convergence-check header bumped to "19 topics enumerated"
if ! grep -qE "^The 19 topics enumerated" "$CHARTER"; then
  echo "FAIL: 'The 19 topics enumerated' not found in charter.md"
  exit 1
fi
echo "OK: convergence-check header reads '19 topics enumerated'"

# Assertion 5 (reconciled AC-3, Risk-C): 4 new convergence-check bullets (12-15)
BULLET_COUNT=$(grep -cE "^- Topic (12|13|14|15) —" "$CHARTER" || true)
if [[ "$BULLET_COUNT" -ne 4 ]]; then
  echo "FAIL: expected 4 '- Topic (12|13|14|15) —' bullets in charter.md, got $BULLET_COUNT"
  exit 1
fi
echo "OK: 4 new convergence-check bullets present"

# Assertion 6 (reconciled AC-3, Risk-C): SKILL.md explainer bumped to "19 topics"
if ! grep -qF "I'll ask about 19 topics" "$SKILL_DIR"/*.md; then
  echo "FAIL: \"I'll ask about 19 topics\" not found in SKILL.md"
  exit 1
fi
echo "OK: SKILL.md explainer reads '19 topics'"

# Assertion 7 (reconciled AC-3, Risk-C): reference.md 9-topic -> 19-topic
NINE_COUNT=$(grep -cE "(^|[^0-9])9-topic" "$REFERENCE" || true)
NINETEEN_COUNT=$(grep -cE "19-topic" "$REFERENCE" || true)
if [[ "$NINE_COUNT" -ne 0 ]]; then
  echo "FAIL: expected 0 '9-topic' mentions in reference.md, got $NINE_COUNT"
  exit 1
fi
if [[ "$NINETEEN_COUNT" -lt 2 ]]; then
  echo "FAIL: expected >= 2 '19-topic' mentions in reference.md, got $NINETEEN_COUNT"
  exit 1
fi
echo "OK: reference.md scrubbed 9-topic -> 19-topic ($NINETEEN_COUNT hits)"

# Assertion 8 (positional ordering): Topic 12 after Topic 11; AI Layer template after Review style; Stakeholders preserved
T11_OFFSET=$(grep -ob '### Topic 11: Review style' "$CHARTER" | head -1 | cut -d: -f1)
T12_OFFSET=$(grep -ob '### Topic 12: AI Champion' "$CHARTER" | head -1 | cut -d: -f1)
if [[ -z "$T11_OFFSET" || -z "$T12_OFFSET" || "$T12_OFFSET" -le "$T11_OFFSET" ]]; then
  echo "FAIL: '### Topic 12:' not positioned after '### Topic 11: Review style' in charter.md"
  exit 1
fi

RS_OFFSET=$(grep -ob '^## Review style$' "$CHARTER" | head -1 | cut -d: -f1)
AIL_OFFSET=$(grep -ob '^## AI Layer$' "$CHARTER" | head -1 | cut -d: -f1)
if [[ -z "$RS_OFFSET" || -z "$AIL_OFFSET" || "$AIL_OFFSET" -le "$RS_OFFSET" ]]; then
  echo "FAIL: '## AI Layer' template block not positioned after '## Review style' placeholder in charter.md"
  exit 1
fi

STAKE_COUNT=$(grep -cE "^### Stakeholders \(conditional probe\)" "$CHARTER" || true)
if [[ "$STAKE_COUNT" -ne 1 ]]; then
  echo "FAIL: expected exactly 1 '### Stakeholders (conditional probe)' block, got $STAKE_COUNT"
  exit 1
fi
echo "OK: positional ordering + Stakeholders preserve"

echo "OK: test_step0_ai_layer_topics.sh"
exit 0
