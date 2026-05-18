#!/usr/bin/env bash
set -euo pipefail

# charter_revalidate_skip.sh — signal whether /pipeline --renew should run a
# charter re-validation pass or skip it.
#
# Contract (see docs/plan-v25.md Task 1.4 and docs/analysis-v24.md § 6):
#   $1 = base directory containing progress.md.
#
# Reads "$1/progress.md", extracts the first `**Charter:**` pointer line, and
# emits exactly one CHARTER_REVALIDATE: line on stdout describing the outcome.
# Exits 0 on every successful decision (skip OR proceed). Exits 2 only on
# argument-validation failure.
#
# Skip cases (exit 0, stdout matches "CHARTER_REVALIDATE: skipped"):
#   1. progress.md is absent.
#   2. progress.md has no `**Charter:**` line.
#   3. Pointer literally equals `(none)`.
#   4. Pointer references a path that does not exist on disk.
#
# Proceed case (exit 0): pointer resolves to an existing file. Emits
#   "CHARTER_REVALIDATE: charter found at <resolved-path>". The full
#   re-validation flow is the interactive pipeline's responsibility; this
#   wrapper only signals skip-vs-proceed.

if [[ $# -lt 1 || -z "${1:-}" || ! -d "${1:-}" ]]; then
  echo "ERROR: charter_revalidate_skip.sh requires a base directory argument" >&2
  exit 2
fi

BASE_DIR="$1"
PROGRESS_FILE="$BASE_DIR/progress.md"

if [[ ! -f "$PROGRESS_FILE" ]]; then
  echo "CHARTER_REVALIDATE: skipped — progress.md not found"
  exit 0
fi

# Extract the first `**Charter:**` line. `grep -m1` stops at the first match;
# `|| true` keeps `set -e` happy when grep returns 1 (no match).
POINTER_LINE=$(grep -m1 '^\*\*Charter:\*\*' "$PROGRESS_FILE" || true)

if [[ -z "$POINTER_LINE" ]]; then
  echo "CHARTER_REVALIDATE: skipped — no charter pointer in progress.md"
  exit 0
fi

# Strip the `**Charter:**` prefix and trim surrounding whitespace via sed.
POINTER=$(printf '%s\n' "$POINTER_LINE" \
  | sed -e 's/^\*\*Charter:\*\*[[:space:]]*//' -e 's/[[:space:]]*$//')

if [[ "$POINTER" == "(none)" ]]; then
  echo "CHARTER_REVALIDATE: skipped — no charter in effect"
  exit 0
fi

# Resolve pointer to a filesystem path. Absolute pointers used as-is;
# relative pointers are interpreted relative to the base directory.
if [[ "$POINTER" == /* ]]; then
  RESOLVED="$POINTER"
else
  RESOLVED="$BASE_DIR/$POINTER"
fi

if [[ ! -e "$RESOLVED" ]]; then
  echo "CHARTER_REVALIDATE: skipped — charter pointer references missing file: $RESOLVED"
  exit 0
fi

echo "CHARTER_REVALIDATE: charter found at $RESOLVED"
exit 0
