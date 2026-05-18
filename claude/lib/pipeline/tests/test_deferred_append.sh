#!/usr/bin/env bash
# Red-phase shell test for
# claude.lib.pipeline.charter_classifier.append_out_of_scope_to_deferred.
#
# The helper appends one row per `out_of_scope` finding to the `## Deferred`
# table in <basedir>/progress.md, creating the section + table header if
# absent. It is idempotent on (Item, Source). When no `out_of_scope`
# findings are present, the file is byte-identical after the call.
#
# Three cases are exercised in isolated mktemp -d directories with trap-
# based cleanup. Each case drives the helper via a single `python3 -c`
# harness that imports `from claude.lib.pipeline import charter_classifier`
# after inserting the repo root onto `sys.path`.
#
# On base `main` the function does not exist on the module — the harness
# raises AttributeError (or ModuleNotFoundError if charter_classifier.py
# itself is missing) and `set -euo pipefail` aborts the script before the
# first grep assertion. This is the red-phase proof.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)

# ---------------------------------------------------------------------------
# Case 1 — appends rows AND creates `## Deferred` header when absent.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/progress.md" <<'EOF'
# Progress

**Plan:** docs/plan.md
**Charter:** docs/charter.md

## Status

| Task | Title | Status |
|------|-------|--------|
| 1.1  | Some task | done |
EOF

python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline import charter_classifier
charter_classifier.append_out_of_scope_to_deferred(
    '$TMP/progress.md',
    [
        {'text': 'logging adds latency', 'scope_tag': 'out_of_scope', 'severity': 'non-blocking'},
        {'text': 'any in-scope thing', 'scope_tag': 'in_scope', 'severity': 'blocking'},
    ],
    'review-v3.md',
)
"

if ! grep -q '## Deferred' "$TMP/progress.md"; then
  echo "FAIL: case-1 — '## Deferred' header was not created"
  exit 1
fi

if ! grep -q 'out-of-scope of charter (review-v3)' "$TMP/progress.md"; then
  echo "FAIL: case-1 — Reason column 'out-of-scope of charter (review-v3)' missing"
  exit 1
fi

if ! grep -q 'logging adds latency' "$TMP/progress.md"; then
  echo "FAIL: case-1 — out_of_scope finding 'logging adds latency' was not appended"
  exit 1
fi

inscope_count=$(grep -c 'any in-scope thing' "$TMP/progress.md" || true)
if [[ "$inscope_count" != "0" ]]; then
  echo "FAIL: case-1 — in_scope finding 'any in-scope thing' was appended (count=$inscope_count, expected 0)"
  exit 1
fi

rm -rf "$TMP"
trap - EXIT

# ---------------------------------------------------------------------------
# Case 2 — idempotent re-run: same invocation twice yields exactly one row.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/progress.md" <<'EOF'
# Progress

**Plan:** docs/plan.md
**Charter:** docs/charter.md

## Status

| Task | Title | Status |
|------|-------|--------|
| 1.1  | Some task | done |
EOF

python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline import charter_classifier
charter_classifier.append_out_of_scope_to_deferred(
    '$TMP/progress.md',
    [
        {'text': 'logging adds latency', 'scope_tag': 'out_of_scope', 'severity': 'non-blocking'},
        {'text': 'any in-scope thing', 'scope_tag': 'in_scope', 'severity': 'blocking'},
    ],
    'review-v3.md',
)
"

python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline import charter_classifier
charter_classifier.append_out_of_scope_to_deferred(
    '$TMP/progress.md',
    [
        {'text': 'logging adds latency', 'scope_tag': 'out_of_scope', 'severity': 'non-blocking'},
        {'text': 'any in-scope thing', 'scope_tag': 'in_scope', 'severity': 'blocking'},
    ],
    'review-v3.md',
)
"

dup_count=$(grep -c 'logging adds latency' "$TMP/progress.md" || true)
if [[ "$dup_count" != "1" ]]; then
  echo "FAIL: case-2 — idempotency violated: 'logging adds latency' appears $dup_count time(s) (expected 1)"
  exit 1
fi

rm -rf "$TMP"
trap - EXIT

# ---------------------------------------------------------------------------
# Case 3 — no edit when no out_of_scope findings; file byte-identical.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/progress.md" <<'EOF'
# Progress

**Plan:** docs/plan.md
**Charter:** docs/charter.md

## Status

| Task | Title | Status |
|------|-------|--------|
| 1.1  | Some task | done |

## Deferred

| Item | Source | Reason | Target Iteration |
|------|--------|--------|-----------------|
EOF

cp "$TMP/progress.md" "$TMP/progress.md.before"

python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline import charter_classifier
charter_classifier.append_out_of_scope_to_deferred(
    '$TMP/progress.md',
    [
        {'text': 'x', 'scope_tag': 'in_scope'},
        {'text': 'y', 'scope_tag': 'scope_creep'},
    ],
    'review-v3.md',
)
"

if ! diff -q "$TMP/progress.md.before" "$TMP/progress.md" > /dev/null; then
  echo "FAIL: case-3 — progress.md was modified despite zero out_of_scope findings"
  echo "----- diff -----"
  diff "$TMP/progress.md.before" "$TMP/progress.md" || true
  echo "----------------"
  exit 1
fi

rm -rf "$TMP"
trap - EXIT

# ---------------------------------------------------------------------------
# Case 4 — pipe characters in finding text do not break the markdown table.
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/progress.md" <<'EOF'
# Progress

**Plan:** docs/plan.md
**Charter:** docs/charter.md

## Status

| Task | Title | Status |
|------|-------|--------|
| 1.1  | Some task | done |
EOF

python3 -c "
import sys
sys.path.insert(0, '$REPO')
from claude.lib.pipeline import charter_classifier
charter_classifier.append_out_of_scope_to_deferred(
    '$TMP/progress.md',
    [{'text': 'a | b | c', 'scope_tag': 'out_of_scope', 'severity': 'non-blocking'}],
    'review-v3.md',
)
"

# The appended row must escape the internal pipe characters as `\|` so
# markdown table parsers see 4 data columns, not 6 data columns.
# Assertion: the row contains the escaped form `\|` (backslash-pipe).
# A row without escaping would store the literal `a | b | c` which adds
# extra pipe-delimited cells and breaks /create-plan's Deferred-table parser.
if ! grep -q 'a \\| b \\| c' "$TMP/progress.md"; then
  echo "FAIL: case-4 — pipe characters in finding text not escaped to \\| in the appended row"
  echo "     row: $(grep 'review-v3' "$TMP/progress.md" | head -1)"
  exit 1
fi

rm -rf "$TMP"
trap - EXIT

echo "OK: test_deferred_append.sh"
exit 0
