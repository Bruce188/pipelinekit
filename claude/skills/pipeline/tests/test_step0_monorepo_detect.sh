#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md

# Assertion 1: new multi-config conflict-log token present
grep -q 'DEPLOY_TARGET_MONOREPO_MULTI_CONFIG' "$SKILL" || { echo "FAIL: 'DEPLOY_TARGET_MONOREPO_MULTI_CONFIG' not found in SKILL.md"; exit 1; }

# Assertion 2: new --auto resolver log token present
grep -q 'MONOREPO_AUTO_FIRST_MATCH' "$SKILL" || { echo "FAIL: 'MONOREPO_AUTO_FIRST_MATCH' not found in SKILL.md"; exit 1; }

# Assertion 3: all three monorepo sub-dir names documented
grep -q 'apps/' "$SKILL" || { echo "FAIL: 'apps/' not found in SKILL.md"; exit 1; }
grep -q 'packages/' "$SKILL" || { echo "FAIL: 'packages/' not found in SKILL.md"; exit 1; }
grep -q 'services/' "$SKILL" || { echo "FAIL: 'services/' not found in SKILL.md"; exit 1; }

# Assertion 4 (positional ordering): MONOREPO_AUTO_FIRST_MATCH byte offset > DEPLOY_TARGET_AUTO_DETECT_CONFLICT offset
CONFLICT_OFFSET=$(grep -ob 'DEPLOY_TARGET_AUTO_DETECT_CONFLICT' "$SKILL" | head -1 | cut -d: -f1)
FIRSTMATCH_OFFSET=$(grep -ob 'MONOREPO_AUTO_FIRST_MATCH' "$SKILL" | head -1 | cut -d: -f1)
if [[ -z "$CONFLICT_OFFSET" || -z "$FIRSTMATCH_OFFSET" || "$FIRSTMATCH_OFFSET" -le "$CONFLICT_OFFSET" ]]; then
  echo "FAIL: MONOREPO_AUTO_FIRST_MATCH not positioned after DEPLOY_TARGET_AUTO_DETECT_CONFLICT in SKILL.md"
  exit 1
fi

echo "OK: test_step0_monorepo_detect.sh"
exit 0
