#!/usr/bin/env bash
# test_memory_journal.sh — pipeline smoke gate for memory-journal.sh.
#
# Thin wrapper around the bash `--selftest` mode. The hook's self-test carries
# the full case table (basic append, JSON validity, required fields, append
# behavior, kill switch, rotation, non-JSON tolerance, cwd fallback); this
# wrapper just dispatches it under the pipeline smoke-gate harness
# (auto-discovered at Step 5.5.7) so the same suite runs both manually and
# inside the per-feature loop.
#
# Exit 0 on full pass, non-zero on any FAIL — matches the pipeline contract.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../memory-journal.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK" >&2
  exit 1
fi

bash "$HOOK" --selftest
