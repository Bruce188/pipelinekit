#!/bin/bash
# PostToolUse hook for Edit|Write: run the project's own prettier on
# ts/tsx/js/jsx/json/yaml files. Always exits 0; formatting never blocks.
# Python and .NET are left to their own tooling (ruff/black and dotnet format
# were slow here: a PATH scan per edit and up to 5 s per .cs edit).

INPUT=$(cat)

# Cheap pre-filter before spawning python.
echo "$INPUT" | grep -qE '\.(tsx?|jsx?|json|ya?ml)"' || exit 0

FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print((json.load(sys.stdin).get('tool_input') or {}).get('file_path',''))" 2>/dev/null)
[ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ] || exit 0

case "$FILE_PATH" in
  */node_modules/*|*/.git/*|*/dist/*|*/build/*) exit 0 ;;
  *.ts|*.tsx|*.js|*.jsx|*.json|*.yaml|*.yml) ;;
  *) exit 0 ;;
esac

# Nearest parent with a package.json owns the prettier install.
DIR=$(dirname "$FILE_PATH")
while [ "$DIR" != "/" ] && [ ! -f "$DIR/package.json" ]; do
  DIR=$(dirname "$DIR")
done

PRETTIER="$DIR/node_modules/.bin/prettier"
[ -x "$PRETTIER" ] || exit 0

# Stock macOS has no timeout; Homebrew's coreutils names it gtimeout. With
# neither, the hook's own timeout in settings.json is the only limit.
LIMIT=$(command -v timeout || command -v gtimeout)
if [ -n "$LIMIT" ]; then
  "$LIMIT" 5 "$PRETTIER" --write -- "$FILE_PATH" >/dev/null 2>&1 || true
else
  "$PRETTIER" --write -- "$FILE_PATH" >/dev/null 2>&1 || true
fi
exit 0
