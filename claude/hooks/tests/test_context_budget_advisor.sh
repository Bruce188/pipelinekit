#!/usr/bin/env bash
# test_context_budget_advisor.sh — pipeline smoke gate for context-budget-advisor.py.
#
# Thin wrapper around the python `--selftest` mode. The python self-test
# carries the full case table (below/at/above threshold, re-warn cadence,
# post-compact reset, opt-out env, custom threshold, missing transcript);
# this wrapper just dispatches it under the pipeline smoke-gate harness
# (auto-discovered at Step 5.5.7) so the same suite runs both manually and
# inside the per-feature loop.
#
# Exit 0 on full pass, non-zero on any FAIL — matches the pipeline contract.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../context-budget-advisor.py"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK" >&2
  exit 1
fi

python3 "$HOOK" --selftest
