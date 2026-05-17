#!/usr/bin/env bash
# Host adapter for Anthropic's `claude` CLI.
# Interface contract: <prompt-file> <output-file> [--model <m>] [--max-turns N]
# Exit codes: 0 success, non-zero failure.
set -euo pipefail

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

ARGS=(--print --output-format text)
[ -n "$MODEL" ] && ARGS+=(--model "$MODEL")
[ -n "$MAX_TURNS" ] && ARGS+=(--max-turns "$MAX_TURNS")

cat "$PROMPT_FILE" | claude "${ARGS[@]}" > "$OUTPUT_FILE"
