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

# F12 freshness check. Read the resolved charter's frontmatter `created:` field
# and short-circuit when the charter is < 7 days old (604800 seconds). Falls
# through cleanly on any parse failure (treat as "not fresh, fall through").
CREATED=""
if grep -q '^---[[:space:]]*$' "$RESOLVED"; then
  # Extract the first frontmatter block (delimited by two `---` fences) and
  # pull out the `created:` line value.
  CREATED=$(awk '/^---[[:space:]]*$/{c++; next} c==1' "$RESOLVED" \
    | grep -m1 '^created:' \
    | sed -e 's/^created:[[:space:]]*//' -e 's/[[:space:]]*$//' \
    || true)
fi

if [[ -n "$CREATED" ]]; then
  # `date -d` is GNU-only; on environments where the parse fails (e.g. BSD
  # date), fall through (treat as not-fresh). 2>/dev/null suppresses the
  # parse error so `set -e` does not abort.
  if CREATED_TS=$(date -d "$CREATED" +%s 2>/dev/null) && NOW_TS=$(date +%s); then
    DELTA_SECONDS=$(( NOW_TS - CREATED_TS ))
    # 7 days in seconds = 604800.
    if (( DELTA_SECONDS >= 0 && DELTA_SECONDS < 604800 )); then
      DELTA_DAYS=$(( DELTA_SECONDS / 86400 ))
      echo "CHARTER_REVALIDATE: fresh — charter created $CREATED ($DELTA_DAYS days ago); skipping re-validation pass"
      exit 0
    fi
  fi
fi

echo "CHARTER_REVALIDATE: charter found at $RESOLVED"
exit 0
