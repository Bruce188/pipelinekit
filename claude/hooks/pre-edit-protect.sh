#!/bin/bash
# Blocks edits to sensitive files: .env, credentials, keys, settings.
# Called by PreToolUse hook on Edit — receives tool input on stdin.

INPUT=$(cat)

# Shell pre-filter: skip Python if input clearly doesn't match sensitive patterns
echo "$INPUT" | grep -qE '(\.env|credentials|\.pem|\.key|settings\.json|settings\.local\.json)' || exit 0

FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path','') or d.get('tool_input',{}).get('filePath',''))" 2>/dev/null)

[ -z "$FILE_PATH" ] && exit 0

BASENAME=$(basename "$FILE_PATH")

# Block .env (exact, not .env.example or .envrc)
if [ "$BASENAME" = ".env" ]; then
  echo "BLOCKED: Editing .env files is not allowed. Manage environment variables manually." >&2
  exit 2
fi

# Block credentials* files
if echo "$BASENAME" | grep -qE '^credentials'; then
  echo "BLOCKED: Editing credentials files is not allowed." >&2
  exit 2
fi

# Block *.pem and *.key files
if echo "$BASENAME" | grep -qE '\.(pem|key)$'; then
  echo "BLOCKED: Editing key/certificate files (*.pem, *.key) is not allowed." >&2
  exit 2
fi

# Block .claude/settings.json and .claude/settings.local.json
if echo "$FILE_PATH" | grep -qE '\.claude/settings(\.local)?\.json$'; then
  echo "BLOCKED: Editing Claude settings files directly is not allowed. Use /update-config skill." >&2
  exit 2
fi

exit 0
