#!/usr/bin/env bash
# ppr_research_flag.sh — /ppr --research mode helper
# Publishes keep-rows from docs/research-results.tsv to a research/<tag>-YYYY-MM-DD branch.
# Default: --dry-run (safe preview). Real publish requires --no-dry-run --research-tag <slug>.
set -euo pipefail

# Hook compatibility verified (plan v68, task 1.3):
#   - block-push-main.sh line 18: regex matches only branches ending in main|master or HEAD:main|master;
#     research/<tag>-<date> does not match — research/* branches pass through cleanly.
#   - validate-commit-msg.sh line 325: CONVENTIONAL_REGEX allows 'chore:' prefix;
#     our commit template "chore: publish research keeps for <tag> (<N> rows)" conforms.
#   - strip-ai-attribution.sh line 42: only strips 'co-authored-by' trailer lines;
#     our commit template contains no AI-attribution strings.

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [ "${1:-}" != "--research" ]; then
    echo "ERROR: first argument must be --research" >&2
    exit 2
fi
shift

DRY_RUN=1
RESEARCH_TAG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --no-dry-run)
            DRY_RUN=0
            shift
            ;;
        --research-tag)
            if [ -z "${2:-}" ]; then
                echo "ERROR: --research-tag requires a value" >&2
                exit 2
            fi
            RESEARCH_TAG="$2"
            shift 2
            ;;
        --research-tag=*)
            RESEARCH_TAG="${1#*=}"
            shift
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Usage: ppr_research_flag.sh --research [--dry-run|--no-dry-run] [--research-tag <slug>]" >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# --no-dry-run requires --research-tag
if [ "$DRY_RUN" -eq 0 ] && [ -z "$RESEARCH_TAG" ]; then
    echo "ERROR: --research-tag <slug> is required when --no-dry-run is set." >&2
    exit 2
fi

# Tag slug validation (only for non-empty tags)
if [ -n "$RESEARCH_TAG" ] && ! echo "$RESEARCH_TAG" | grep -qE '^[a-zA-Z0-9._-]+$'; then
    echo "ERROR: --research-tag value '$RESEARCH_TAG' is invalid. Use only letters, digits, dots, underscores, and hyphens." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# TSV validation
# ---------------------------------------------------------------------------

TSV="docs/research-results.tsv"
if [ ! -f "$TSV" ]; then
    echo "ERROR: docs/research-results.tsv missing — run /research-loop first." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Parse header and locate status column index (0-based)
# ---------------------------------------------------------------------------

HEADER="$(head -1 "$TSV")"

# Use python3 to find the status column index dynamically
STATUS_COL="$(python3 -c "
import sys
header = sys.argv[1]
cols = header.rstrip('\n').split('\t')
try:
    idx = cols.index('status')
    print(idx)
except ValueError:
    print(-1)
" "$HEADER")"

if [ "$STATUS_COL" -eq -1 ]; then
    echo "ERROR: docs/research-results.tsv has no 'status' column in the header." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Filter keep rows
# ---------------------------------------------------------------------------

# Count keep rows (excluding header)
KEEP_COUNT="$(tail -n +2 "$TSV" | python3 -c "
import sys
col = int(sys.argv[1])
count = 0
for line in sys.stdin:
    fields = line.rstrip('\n').split('\t')
    if len(fields) > col and fields[col].strip() == 'keep':
        count += 1
print(count)
" "$STATUS_COL")"

if [ "$KEEP_COUNT" -eq 0 ]; then
    echo "WARN: 0 keep rows in docs/research-results.tsv — nothing to publish."
    exit 0
fi

# ---------------------------------------------------------------------------
# Base branch detection (canonical snippet from ~/.claude/rules/workflow.md)
# ---------------------------------------------------------------------------

BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@') || true
[ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}') || true
[ -z "$BASE" ] && BASE="main"

# ---------------------------------------------------------------------------
# Branch name computation with collision avoidance
# ---------------------------------------------------------------------------

DATE=$(date -u +%Y-%m-%d)
CANDIDATE_BASE="research/${RESEARCH_TAG}-${DATE}"
BRANCH=""

for suffix in "" -2 -3 -4 -5 -6 -7 -8 -9; do
    CANDIDATE="${CANDIDATE_BASE}${suffix}"
    LOCAL_EXISTS=0
    REMOTE_EXISTS=0

    git rev-parse --verify "refs/heads/$CANDIDATE" >/dev/null 2>&1 && LOCAL_EXISTS=1 || true
    { git ls-remote --heads origin "$CANDIDATE" 2>/dev/null | grep -q "$CANDIDATE" && REMOTE_EXISTS=1; } || true

    if [ "$LOCAL_EXISTS" -eq 0 ] && [ "$REMOTE_EXISTS" -eq 0 ]; then
        BRANCH="$CANDIDATE"
        break
    fi
done

if [ -z "$BRANCH" ]; then
    echo "ERROR: all branch name candidates for '$CANDIDATE_BASE' (suffixes -2 through -9) already exist locally or on origin. Delete a stale remote branch or use a different --research-tag." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Dry-run path
# ---------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY-RUN: would create branch ${BRANCH}"
    echo "DRY-RUN: ${KEEP_COUNT} keep row(s) would be committed"
    echo "DRY-RUN: would run: git checkout -b ${BRANCH} ${BASE}"
    echo "DRY-RUN: would run: git add ${TSV}"
    echo "DRY-RUN: would run: git commit -m \"chore: publish research keeps for ${RESEARCH_TAG} (${KEEP_COUNT} rows)\""
    echo "DRY-RUN: would run: git push -u origin ${BRANCH}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Real publish path
# ---------------------------------------------------------------------------

# Filter TSV to keep-rows only (header + keep rows)
FILTERED_TSV="$(python3 -c "
import sys
col = int(sys.argv[1])
tsv_path = sys.argv[2]
lines = []
with open(tsv_path, 'r') as f:
    rows = f.readlines()
if rows:
    lines.append(rows[0])  # header
    for row in rows[1:]:
        fields = row.rstrip('\n').split('\t')
        if len(fields) > col and fields[col].strip() == 'keep':
            lines.append(row)
sys.stdout.write(''.join(lines))
" "$STATUS_COL" "$TSV")"

git checkout -b "$BRANCH" "$BASE"

# Write filtered TSV (overwrite working copy)
echo "$FILTERED_TSV" > "$TSV"

git add "$TSV"
git commit -m "chore: publish research keeps for ${RESEARCH_TAG} (${KEEP_COUNT} rows)"
git push -u origin "$BRANCH"

echo "Published ${BRANCH} with ${KEEP_COUNT} keep row(s)."
exit 0
