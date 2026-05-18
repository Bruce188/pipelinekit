#!/usr/bin/env bash
# Red-phase test for claude/lib/pipeline/charter_revalidate_skip.sh.
#
# The wrapper script consults `**Charter:**` in <basedir>/progress.md and emits
# a "CHARTER_REVALIDATE: skipped ..." line on stdout (exit 0) when any of these
# three skip conditions holds:
#   1. Pointer line literally `(none)`.
#   2. Pointer line references a charter path that does not exist on disk.
#   3. Pointer line is absent entirely from progress.md.
#
# Each case is exercised in an isolated mktemp -d directory with a trap-based
# cleanup. The inner script's stdout is captured and asserted against the
# required substring. On base `main` the wrapper does not exist, so the
# `bash <path>` invocation fails and (under `set -euo pipefail`) the script
# exits non-zero before the first assertion can run — the red-phase proof.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
SCRIPT="$REPO/claude/lib/pipeline/charter_revalidate_skip.sh"

run_case() {
  # $1 = case label (for failure messages)
  # $2 = tempdir
  local label="$1"
  local tmp="$2"
  local out
  out=$(bash "$SCRIPT" "$tmp")
  if [[ "$out" != *"CHARTER_REVALIDATE: skipped"* ]]; then
    echo "FAIL: $label — stdout did not contain 'CHARTER_REVALIDATE: skipped'"
    echo "----- stdout -----"
    echo "$out"
    echo "------------------"
    exit 1
  fi
}

# Case 1: pointer is literally `(none)` → skip.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/progress.md" <<'EOF'
# Progress

**Charter:** (none)
EOF
run_case "case-1 (none) pointer" "$TMP"
rm -rf "$TMP"
trap - EXIT

# Case 2: pointer references a file that does not exist under tempdir → skip.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/progress.md" <<'EOF'
# Progress

**Charter:** docs/charter.md
EOF
# Intentionally do NOT create $TMP/docs/charter.md.
run_case "case-2 pointer to missing file" "$TMP"
rm -rf "$TMP"
trap - EXIT

# Case 3: no `**Charter:**` line at all → skip.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/progress.md" <<'EOF'
# Progress

This progress file deliberately omits any Charter pointer line.
Some other innocuous content lives here.
EOF
run_case "case-3 no pointer at all" "$TMP"
rm -rf "$TMP"
trap - EXIT

echo "OK: test_skip_condition.sh"
exit 0
