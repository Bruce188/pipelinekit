#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# fetch_issues.sh — wrap `gh issue list` with the four selector forms,
# apply --issues-sort, apply --issues-limit, and emit a JSON array on stdout.
#
# Usage: fetch_issues.sh <selector> [<limit>] [<sort>] [<comment-author>]
#
#   <selector>       label:<name> | milestone:<name> | all | <bare-name>
#   <limit>          integer 1..200 (default 50)
#   <sort>           created | updated | priority (default created)
#   <comment-author> optional GitHub login for maintainer-comment override
#
# Exit codes:
#   0  on success — JSON array on stdout
#   1  on missing/invalid args
#   2  on gh CLI missing
#   3  on gh auth failure
#   4  on repo missing remote
#   5  on gh API rate limit
#   6  on empty result set (no issues match)
#   7  on other gh failures (stderr passed through)

# ── Usage guard ──────────────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
  echo "Usage: fetch_issues.sh <selector> [<limit>] [<sort>] [<comment-author>]" >&2
  echo "  <selector>       label:<name> | milestone:<name> | all | <bare-name>" >&2
  echo "  <limit>          integer 1..200 (default 50)" >&2
  echo "  <sort>           created | updated | priority (default created)" >&2
  echo "  <comment-author> optional GitHub login for maintainer-comment override" >&2
  exit 1
fi

SELECTOR="${1}"
LIMIT="${2:-50}"
SORT_MODE="${3:-created}"
COMMENT_AUTHOR="${4:-}"

# ── Validate args ─────────────────────────────────────────────────────────────

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [[ "$LIMIT" -lt 1 ]] || [[ "$LIMIT" -gt 200 ]]; then
  echo "ERROR: <limit> must be an integer 1..200 (got: $LIMIT)" >&2
  exit 1
fi

case "$SORT_MODE" in
  created|updated|priority) ;;
  *)
    echo "ERROR: <sort> must be one of: created, updated, priority (got: $SORT_MODE)" >&2
    exit 1
    ;;
esac

# ── Pre-checks ────────────────────────────────────────────────────────────────

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not installed. See https://cli.github.com/" >&2
  exit 2
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh not authenticated. Run \`gh auth login\` first." >&2
  exit 3
fi

if ! git remote -v 2>/dev/null | grep -q .; then
  echo "ERROR: --issues requires a GitHub remote. This repo has no remote configured." >&2
  exit 4
fi

# ── Selector parsing ──────────────────────────────────────────────────────────

GH_FILTER=()
if [[ "$SELECTOR" == label:* ]]; then
  LABEL="${SELECTOR#label:}"
  GH_FILTER=(--label "$LABEL")
elif [[ "$SELECTOR" == milestone:* ]]; then
  MILESTONE="${SELECTOR#milestone:}"
  GH_FILTER=(--milestone "$MILESTONE")
elif [[ "$SELECTOR" == "all" ]]; then
  GH_FILTER=()
else
  # bare name → default to label mode
  GH_FILTER=(--label "$SELECTOR")
fi

# ── Fetch issues ──────────────────────────────────────────────────────────────

GH_STDERR=$(mktemp)
trap 'rm -f "$GH_STDERR"' EXIT

GH_SORT_ARG="created"
if [[ "$SORT_MODE" == "updated" ]]; then
  GH_SORT_ARG="updated"
fi
# priority sort is done client-side after fetch

GH_JSON=""
GH_EXIT=0
GH_JSON=$(gh issue list \
  --state open \
  "${GH_FILTER[@]}" \
  --limit 200 \
  --sort "$GH_SORT_ARG" \
  --json number,title,body,labels,createdAt,updatedAt,milestone,comments \
  2>"$GH_STDERR") || GH_EXIT=$?

if [[ $GH_EXIT -ne 0 ]]; then
  STDERR_CONTENT=$(cat "$GH_STDERR")
  if echo "$STDERR_CONTENT" | grep -qi "API rate limit"; then
    echo "ERROR: gh API rate limit exceeded. Retry after checking: gh api rate_limit" >&2
    exit 5
  fi
  echo "$STDERR_CONTENT" >&2
  exit 7
fi

# ── Empty result check ────────────────────────────────────────────────────────

if [[ "$GH_JSON" == "[]" || -z "$GH_JSON" ]]; then
  echo "ERROR: No open issues match selector $SELECTOR. Nothing to process." >&2
  exit 6
fi

# ── Client-side priority sort (if requested) ──────────────────────────────────

if [[ "$SORT_MODE" == "priority" ]]; then
  GH_JSON=$(python3 -c "
import json, sys

data = json.loads(sys.stdin.read())

def priority_key(issue):
    labels = [l.get('name', '') for l in issue.get('labels', [])]
    for label in labels:
        if label == 'priority:high':
            return 0
        if label == 'priority:medium':
            return 1
        if label == 'priority:low':
            return 2
    return 3

# Use stable sort to preserve original order within same priority class
data.sort(key=priority_key)
print(json.dumps(data))
" <<< "$GH_JSON") || {
    echo "ERROR: failed to parse JSON from gh issue list (priority sort)" >&2
    exit 7
  }
fi

# ── Apply limit ───────────────────────────────────────────────────────────────

TOTAL=$(python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))" <<< "$GH_JSON") || {
  echo "ERROR: failed to parse JSON from gh issue list (total count)" >&2
  exit 7
}

if [[ "$TOTAL" -gt "$LIMIT" ]]; then
  echo "WARN: $TOTAL issues match selector; processing top $LIMIT by $SORT_MODE" >&2
  GH_JSON=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(json.dumps(data[:int(sys.argv[1])]))
" "$LIMIT" <<< "$GH_JSON") || {
    echo "ERROR: failed to parse JSON from gh issue list (limit slice)" >&2
    exit 7
  }
fi

# ── Annotate with _maintainer_login if comment-author override given ──────────

if [[ -n "$COMMENT_AUTHOR" ]]; then
  GH_JSON=$(python3 -c "
import json, sys
login = sys.argv[1]
data = json.loads(sys.stdin.read())
for issue in data:
    issue['_maintainer_login'] = login
print(json.dumps(data))
" "$COMMENT_AUTHOR" <<< "$GH_JSON") || {
    echo "ERROR: failed to parse JSON from gh issue list (maintainer annotation)" >&2
    exit 7
  }
fi

# ── Emit JSON on stdout ───────────────────────────────────────────────────────

echo "$GH_JSON"
exit 0
