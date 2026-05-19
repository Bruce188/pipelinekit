#!/usr/bin/env bash
set -euo pipefail
# Host adapter for the Codex CLI.
# Interface contract: <prompt-file> <output-file> [--model <m>] [--max-turns N]
# Exit codes:
#   0 — codex exec completed successfully
#   2 — runtime unavailable: codex binary not on PATH
#   non-zero (other) — codex exec ran but failed (pass-through)

if [ $# -lt 2 ]; then
  echo "usage: $(basename "$0") <prompt-file> <output-file> [--model <m>] [--max-turns N]" >&2
  exit 1
fi

PROMPT_FILE="$1"
OUTPUT_FILE="$2"
shift 2

MODEL=""
MAX_TURNS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --max-turns) MAX_TURNS="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

# Runtime availability check — exit 2 if codex is not on PATH
if ! command -v codex >/dev/null 2>&1; then
  echo "WORKER_UNAVAILABLE: codex (host-adapter missing)" >&2
  exit 2
fi

# Derive task-id from prompt-file path if it follows the
# .claude/tasks/<id>/prompt.md convention.
TASK_ID=""
OUTPUT_DIR=""
if echo "$PROMPT_FILE" | grep -qE '\.claude/tasks/([^/]+)/'; then
  TASK_ID=$(echo "$PROMPT_FILE" | sed -E 's|.*\.claude/tasks/([^/]+)/.*|\1|')
  OUTPUT_DIR="$(dirname "$PROMPT_FILE")/output"
  OUTPUT_DIR=$(realpath "$OUTPUT_DIR" 2>/dev/null || echo "$OUTPUT_DIR")
  mkdir -p "$OUTPUT_DIR"
fi

# Read prompt preserving trailing newlines (command substitution would strip them).
IFS= read -rd '' PROMPT_TEXT <"$PROMPT_FILE" || true

# Build codex args
ARGS=()
[ -n "$MODEL" ] && ARGS+=(--model "$MODEL")
[ -n "$MAX_TURNS" ] && ARGS+=(--max-turns "$MAX_TURNS")

# Run codex exec, capturing stdout and stderr
if [ -n "$OUTPUT_DIR" ]; then
  EC=0
  codex exec "${ARGS[@]}" "$PROMPT_TEXT" \
    > "$OUTPUT_DIR/stdout" \
    2> "$OUTPUT_DIR/stderr" \
    || EC=$?
  echo "$EC" > "$OUTPUT_DIR/exit"
  # Also write to the canonical output-file
  cp "$OUTPUT_DIR/stdout" "$OUTPUT_FILE"
  exit "$EC"
else
  # No task-id derivable — write only to <output-file>;
  # stderr passes through to caller, exit code is captured + propagated.
  EC=0
  codex exec "${ARGS[@]}" "$PROMPT_TEXT" > "$OUTPUT_FILE" || EC=$?
  exit "$EC"
fi
