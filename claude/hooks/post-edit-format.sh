#!/bin/bash
# Auto-formats files after Write/Edit using the project's formatter.
# Called by PostToolUse hook on Write|Edit — receives tool input on stdin.
# Always exits 0 — formatting failures must never block the agent.

INPUT=$(cat)

# Shell pre-filter: only process files with formattable extensions
echo "$INPUT" | grep -qE '\.(cs|ts|tsx|js|jsx|py|json|yaml|yml)' || exit 0

FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path','') or d.get('tool_input',{}).get('filePath',''))" 2>/dev/null)

[ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ] && exit 0

# Skip excluded directories
case "$FILE_PATH" in
  */node_modules/*|*/.git/*|*/bin/*|*/obj/*|*/dist/*|*/build/*|*/__pycache__/*) exit 0 ;;
esac

# Get file extension
EXT="${FILE_PATH##*.}"

# Get file directory
DIR=$(dirname "$FILE_PATH")

# Find nearest parent directory with package.json (used by ts/js/json/yaml formatters)
PROJ_DIR="$DIR"
while [ "$PROJ_DIR" != "/" ] && [ ! -f "$PROJ_DIR/package.json" ]; do
  PROJ_DIR=$(dirname "$PROJ_DIR")
done

case "$EXT" in
  cs)
    # .NET: dotnet format if solution/project file exists
    if compgen -G "$DIR/../*.sln" >/dev/null 2>&1 || \
       compgen -G "$DIR/../*.csproj" >/dev/null 2>&1 || \
       compgen -G "$DIR/*.sln" >/dev/null 2>&1 || \
       compgen -G "$DIR/*.csproj" >/dev/null 2>&1; then
      timeout 5 dotnet format --include "$FILE_PATH" --verbosity quiet 2>/dev/null || true
    fi
    ;;
  ts|tsx|js|jsx)
    # Node.js: prettier if available
    if [ -f "$PROJ_DIR/node_modules/.bin/prettier" ]; then
      timeout 5 "$PROJ_DIR/node_modules/.bin/prettier" --write -- "$FILE_PATH" 2>/dev/null || true
    fi
    ;;
  py)
    # Python: ruff (preferred) or black
    if command -v ruff >/dev/null 2>&1; then
      timeout 5 ruff format -- "$FILE_PATH" 2>/dev/null || true
    elif command -v black >/dev/null 2>&1; then
      timeout 5 black -q -- "$FILE_PATH" 2>/dev/null || true
    fi
    ;;
  json|yaml|yml)
    # Prettier for config files (if available in a parent project)
    if [ -f "$PROJ_DIR/node_modules/.bin/prettier" ]; then
      timeout 5 "$PROJ_DIR/node_modules/.bin/prettier" --write -- "$FILE_PATH" 2>/dev/null || true
    fi
    ;;
esac

exit 0
