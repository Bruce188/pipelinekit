#!/usr/bin/env bash
# claude/skills/caveman-mode/tier1_allowlist.sh
# Deterministic Tier 1 path allowlist gate for /caveman-compress.
# Exit 0 = accept; exit 2 = reject (with stderr refusal).
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "caveman-compress: usage: tier1_allowlist.sh <path>" >&2
  exit 2
fi
path="$1"
if [[ "$path" =~ (^|/)CLAUDE\.md(\.template)?$ ]] || [[ "$path" =~ (^|/)rules/[^/]+\.md$ ]]; then
  exit 0
fi
echo "caveman-compress: rejected $path — not in Tier 1 allowlist (CLAUDE.md* | rules/*.md)" >&2
exit 2
