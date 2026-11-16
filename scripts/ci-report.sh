#!/usr/bin/env bash
# Reports a failed scheduled CI run: adds a comment to the open issue with the
# title below, or opens that issue. Used by the report job in
# .github/workflows/ci.yml; needs gh with GH_TOKEN and GH_REPO set.
# usage: ci-report.sh <run-url>
set -euo pipefail

TITLE="Weekly self-check failed"
url="${1:-}"
if ! [[ "$url" =~ ^https://[A-Za-z0-9._/-]+$ ]]; then
  echo "usage: ci-report.sh <run-url>" >&2
  exit 2
fi

listed="$(gh issue list --state open --search "$TITLE in:title" --limit 50 --json number,title)"
number="$(printf '%s' "$listed" | python3 -c '
import json
import sys

found = [i["number"] for i in json.load(sys.stdin) if i.get("title") == sys.argv[1]]
print(min(found) if found else "")
' "$TITLE")"

if [ -n "$number" ]; then
  gh issue comment "$number" --body "The scheduled run failed again: $url"
  echo "added a comment to #$number"
  exit 0
fi

body="The weekly CI run failed: $url

It runs the hook, installer and self-check tests, installs the kit into an
empty home directory and runs the self-check there. Read the log of the
failed job first: \`gh run view --log-failed\` with the run id from the link.

Later failures are added here as comments. Close this issue once a run is
green again."

# The label is a convenience: a repository without it still gets the issue.
gh issue create --title "$TITLE" --label bug --body "$body" ||
  gh issue create --title "$TITLE" --body "$body"