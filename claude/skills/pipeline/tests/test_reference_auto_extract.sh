#!/usr/bin/env bash
set -euo pipefail

REFERENCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/reference.md

# Assertion 1: new H2 section header is present
grep -q '^## Step 0: Charter Auto-Extract' "$REFERENCE" || { echo "FAIL: '## Step 0: Charter Auto-Extract' header not found in reference.md"; exit 1; }

# Assertion 2: discovery helper is named
grep -q 'discover_artifact_paths' "$REFERENCE" || { echo "FAIL: 'discover_artifact_paths' not found in reference.md"; exit 1; }

# Assertion 3: extraction helper is named
grep -q 'extract_draft_charter' "$REFERENCE" || { echo "FAIL: 'extract_draft_charter' not found in reference.md"; exit 1; }

# Assertion 4: renderer is named
grep -q 'render_charter_markdown' "$REFERENCE" || { echo "FAIL: 'render_charter_markdown' not found in reference.md"; exit 1; }

# Assertion 5: skip-gate is named
grep -q 'should_auto_extract' "$REFERENCE" || { echo "FAIL: 'should_auto_extract' not found in reference.md"; exit 1; }

# Assertion 6: user-confirmation gate is documented
grep -q 'AskUserQuestion' "$REFERENCE" || { echo "FAIL: 'AskUserQuestion' not found in reference.md"; exit 1; }

# Assertion 7: all three AskUserQuestion options appear
grep -q 'accept' "$REFERENCE" && grep -q 'edit' "$REFERENCE" && grep -q 'start fresh discovery' "$REFERENCE" || { echo "FAIL: one or more AskUserQuestion options (accept/edit/start fresh discovery) missing from reference.md"; exit 1; }

# Assertion 8: canonical skip-log token
grep -q 'CHARTER_AUTO_EXTRACT_SKIPPED' "$REFERENCE" || { echo "FAIL: 'CHARTER_AUTO_EXTRACT_SKIPPED' token not found in reference.md"; exit 1; }

# Assertion 9: subprocess-mode skip path is documented
grep -q 'subprocess mode' "$REFERENCE" || { echo "FAIL: 'subprocess mode' not found in reference.md"; exit 1; }

# Assertion 10: field-mapping table present (Goal, Users, Non-Goals rows)
grep -qE '\|[[:space:]]*Goal[[:space:]]*\|' "$REFERENCE" || { echo "FAIL: Goal row missing from field-mapping table in reference.md"; exit 1; }
grep -qE '\|[[:space:]]*Users[[:space:]]*\|' "$REFERENCE" || { echo "FAIL: Users row missing from field-mapping table in reference.md"; exit 1; }
grep -qE '\|[[:space:]]*Non-Goals[[:space:]]*\|' "$REFERENCE" || { echo "FAIL: Non-Goals row missing from field-mapping table in reference.md"; exit 1; }

# Assertion 11: existing reference.md content intact (Step 1.6 header still present)
grep -q '^## Step 1.6: Renew Feature File' "$REFERENCE" || { echo "FAIL: existing '## Step 1.6: Renew Feature File' header was removed from reference.md"; exit 1; }

echo "OK: test_reference_auto_extract.sh"
exit 0
