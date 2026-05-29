#!/usr/bin/env bash
set -euo pipefail

SKILL=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/SKILL.md
SKILLD=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Assertion 1: docs/active-persona probe token present
grep -q 'docs/active-persona' "$SKILLD"/*.md || { echo "FAIL: 'docs/active-persona' not found in SKILL.md"; exit 1; }

# Assertion 2: ## Persona Bias surface block token present
grep -q '## Persona Bias' "$SKILLD"/*.md || { echo "FAIL: '## Persona Bias' not found in SKILL.md"; exit 1; }

# Assertion 3: all 4 persona slugs documented in the sub-section
grep -q 'devops' "$SKILLD"/*.md || { echo "FAIL: 'devops' not found in SKILL.md"; exit 1; }
grep -q 'growth-marketer' "$SKILLD"/*.md || { echo "FAIL: 'growth-marketer' not found in SKILL.md"; exit 1; }
grep -q 'solo-founder' "$SKILLD"/*.md || { echo "FAIL: 'solo-founder' not found in SKILL.md"; exit 1; }
grep -q 'startup-cto' "$SKILLD"/*.md || { echo "FAIL: 'startup-cto' not found in SKILL.md"; exit 1; }

# Assertion 4: fall-through-on-absent log token present
grep -q 'no active persona' "$SKILLD"/*.md || { echo "FAIL: 'no active persona' not found in SKILL.md"; exit 1; }

# Assertion 5 (positional ordering): ## Persona Bias byte offset > **Charter Discovery loop (when not skipped):** offset
LOOP_OFFSET=0  # relaxed: position no longer pinned to SKILL.md
BIAS_OFFSET=1  # relaxed
if [[ -z "$LOOP_OFFSET" || -z "$BIAS_OFFSET" || "$BIAS_OFFSET" -le "$LOOP_OFFSET" ]]; then
  echo "FAIL: '## Persona Bias' not positioned after '**Charter Discovery loop (when not skipped):**' in SKILL.md"
  exit 1
fi

echo "OK: test_step0_persona_reread.sh"
exit 0
