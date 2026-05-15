#!/bin/bash
# Automatic Test Execution Logger
# Logs all test commands run by Claude Code
# Reads JSON from stdin (hook protocol), uses python3 for parsing.

# Shell pre-filter: skip Python parse for non-test commands (~99% of calls)
INPUT=$(cat)
echo "$INPUT" | grep -qE '"(pytest|test|jest|vitest|mocha|karma)' || exit 0

LOG_FILE="$HOME/.claude/logs/test_execution.log"
MAX_LOG_SIZE=1048576  # 1MB
mkdir -p "$(dirname "$LOG_FILE")"

# Rotate log if exceeding size cap
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
  mv "$LOG_FILE" "${LOG_FILE}.old"
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Extract all fields in a single python3 invocation (jq not available on this system)
PARSED=$(printf '%s' "$INPUT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    ti=d.get('tool_input',{})
    print(ti.get('command',''))
    print(ti.get('description',''))
    print(d.get('tool_name','Bash'))
except:
    print(); print(); print()
" 2>/dev/null)

COMMAND=$(echo "$PARSED" | head -1)
DESCRIPTION=$(echo "$PARSED" | sed -n '2p')
TOOL=$(echo "$PARSED" | sed -n '3p')

# Early exit on malformed JSON (all fields empty)
[ -z "$COMMAND" ] && [ -z "$TOOL" ] && exit 0

# Detect if this is a test command (including npx jest, pnpm test, bun test)
IS_TEST=false
if [[ "$COMMAND" =~ (pytest|dotnet\ test|npm.*test|yarn.*test|go.*test|cargo.*test|make.*test|python3.*test|npx\ jest|npx\ vitest|pnpm.*test|bun.*test|jest|vitest|mocha) ]]; then
    IS_TEST=true
fi

# Only log if it's a test command or contains python3/pytest in skills directory
if [[ "$IS_TEST" == "true" ]] || [[ "$COMMAND" =~ \.claude/skills.*python3 ]]; then
    CWD=$(pwd)

    echo "[$TIMESTAMP] $TOOL" >> "$LOG_FILE"
    echo "  Command: $COMMAND" >> "$LOG_FILE"
    if [ -n "$DESCRIPTION" ] && [ "$DESCRIPTION" != "null" ]; then
        echo "  Description: $DESCRIPTION" >> "$LOG_FILE"
    fi
    echo "  Directory: $CWD" >> "$LOG_FILE"
    echo "  ---" >> "$LOG_FILE"
fi
