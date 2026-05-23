#!/usr/bin/env bash
# Smoke test for the three-zone caveman snippet contract.
# Asserts: (1) three Zone H2 headings present; (2) >=1 Han character (U+4E00-U+9FFF) in body.
#
# Idempotent. Sandboxes nothing — read-only against the repo source.
# Runs under the pipeline auto-discovery gate (Step 5.5.7).

set -euo pipefail

REPO_ROOT="${PIPELINEKIT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ] || [ ! -d "$REPO_ROOT" ]; then
  echo "FAIL: cannot resolve repo root (not in a git checkout and PIPELINEKIT_ROOT unset)" >&2
  exit 1
fi

SNIPPET="$REPO_ROOT/claude/snippets/caveman-subagent.md"

if [ ! -f "$SNIPPET" ]; then
  echo "FAIL: snippet not found at $SNIPPET" >&2
  exit 1
fi

# Assert each Zone H2 heading.
for zone in "## Zone 1" "## Zone 2" "## Zone 3"; do
  if ! grep -qF "$zone" "$SNIPPET"; then
    echo "FAIL: missing heading: $zone" >&2
    exit 1
  fi
done

# Assert >=1 Han character in the body. Python3 is the portable regex engine — bash regex
# with `[一-鿿]` is non-portable across locales.
if ! python3 -c "
import re, sys
body = open('$SNIPPET', encoding='utf-8').read()
sys.exit(0 if re.search(r'[一-鿿]', body) else 1)
"; then
  echo "FAIL: no Han character (U+4E00-U+9FFF) found in $SNIPPET" >&2
  exit 1
fi

echo "PASS: three-zone split assertions hold."
exit 0
