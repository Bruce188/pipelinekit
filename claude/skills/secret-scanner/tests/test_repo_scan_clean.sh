#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)

# ---------------------------------------------------------------------------
# Assertion A — repo scan: zero real secrets in the repo
# Excludes: .git/, tresor-resources/, and the authoring SKILL.md itself
# (so the documented placeholder patterns in the regex bank do not self-match)
# ---------------------------------------------------------------------------
AUTHORING_SKILL_PATH="$REPO_ROOT/claude/skills/secret-scanner/SKILL.md"

HITS=$(grep -rEn \
  'AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|(sk|pk)_(live|test)_[0-9a-zA-Z]{24,}|sk-ant-[0-9A-Za-z_\-]{90,}|sk-proj-[0-9A-Za-z_\-]{40,}|gh[pousr]_[0-9A-Za-z]{36,}|glpat-[0-9A-Za-z_\-]{20}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+' \
  --exclude-dir=.git \
  --exclude-dir=.claude \
  --exclude-dir=tresor-resources \
  --exclude-dir=docs \
  "$REPO_ROOT" 2>/dev/null \
  | grep -v "^${AUTHORING_SKILL_PATH}:" \
  || true)

if [[ -n "$HITS" ]]; then
  echo "FAIL: Assertion A — secret pattern found in repo:"
  echo "$HITS"
  exit 1
fi

# ---------------------------------------------------------------------------
# Assertion B — regex-bank contract on SKILL.md
# B1: ## Detection Patterns section contains ≥8 documented family rows
# B2: TODO: token is absent from SKILL.md
# ---------------------------------------------------------------------------

# B2 first: TODO: token must be absent
if grep -q 'TODO:' "$SKILL"; then
  echo "FAIL: Assertion B2 — 'TODO:' token still present in SKILL.md (line-150 fix not applied)"
  exit 1
fi

# B1: count rows in the regex-bank table (lines starting with '|' under ## Detection Patterns
# that contain a regex pattern — skip header/separator rows)
# A table row is any '|'-delimited line with content between pipes
DETECTION_SECTION=$(awk '/^## Detection Patterns/{found=1} found{print} /^## [^D]/{if(found) exit}' "$SKILL")

# Count non-empty, non-separator table rows (exclude header '| Family |' and separator '|---|')
FAMILY_ROW_COUNT=$(echo "$DETECTION_SECTION" | grep -cE '^\|[[:space:]]*[0-9]+' || true)

if [[ "$FAMILY_ROW_COUNT" -lt 8 ]]; then
  echo "FAIL: Assertion B1 — ## Detection Patterns has only $FAMILY_ROW_COUNT numbered family rows (need ≥8)"
  exit 1
fi

echo "OK: test_repo_scan_clean.sh"
exit 0
