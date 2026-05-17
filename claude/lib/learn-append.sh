#!/usr/bin/env bash
# Append one JSONL lesson to ~/.pipelinekit/projects/<slug>/learnings.jsonl
# Best-effort: failures NEVER block the caller (always exit 0).
# Usage: learn-append.sh --severity <info|warn|error> --category <cat> \
#                       --source <review|post-merge> --feature <name> \
#                       --lesson "<one-line lesson>"

set -uo pipefail

SEVERITY=""
CATEGORY=""
SOURCE=""
FEATURE=""
LESSON=""

while [ $# -gt 0 ]; do
  case "$1" in
    --severity) SEVERITY="$2"; shift 2 ;;
    --category) CATEGORY="$2"; shift 2 ;;
    --source)   SOURCE="$2"; shift 2 ;;
    --feature)  FEATURE="$2"; shift 2 ;;
    --lesson)   LESSON="$2"; shift 2 ;;
    *) echo "learn-append: unknown arg: $1" >&2; exit 0 ;;
  esac
done

# Derive project slug
TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)" || TOPLEVEL=""
if [ -z "$TOPLEVEL" ]; then
  echo "learn-append: not in a git repo — skipping" >&2
  exit 0
fi
PROJECT_SLUG="$(basename "$TOPLEVEL")"

# Defensive: refuse to write if ~/.pipelinekit/ resolves inside the project tree
PIPELINEKIT_HOME="$HOME/.pipelinekit"
case "$PIPELINEKIT_HOME" in
  "$TOPLEVEL"/*)
    echo "learn-append: ~/.pipelinekit/ inside project tree — aborting" >&2
    exit 0
    ;;
esac

OUT_DIR="$PIPELINEKIT_HOME/projects/$PROJECT_SLUG"
OUT_FILE="$OUT_DIR/learnings.jsonl"
mkdir -p "$OUT_DIR" || { echo "learn-append: cannot create $OUT_DIR" >&2; exit 0; }

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Emit JSONL via python3 (handles escaping safely; jq not assumed installed)
python3 - "$TS" "$PROJECT_SLUG" "$FEATURE" "$SEVERITY" "$CATEGORY" "$LESSON" "$SOURCE" >>"$OUT_FILE" <<'PY' || exit 0
import json, sys
ts, slug, feature, severity, category, lesson, source = sys.argv[1:8]
print(json.dumps({
    "ts": ts,
    "project_slug": slug,
    "feature": feature,
    "severity": severity,
    "category": category,
    "lesson": lesson,
    "source": source,
}))
PY

exit 0
