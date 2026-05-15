#!/usr/bin/env bash
# TDD ordering check: warn if source files are written before test files in a session.
# PreToolUse hook for Write|Edit. Always exits 0 (warn, never block).

set -euo pipefail

# Session marker file — unique per parent process
# Use XDG_RUNTIME_DIR if available (user-only, not world-writable), fall back to /tmp
MARKER="${XDG_RUNTIME_DIR:-/tmp}/claude-tdd-session-${PPID}"

# Read tool input from stdin
INPUT=$(cat)

# Extract file_path using sed (avoid python3 startup cost on hot path)
FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$FILE_PATH" ] && FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"filePath"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')

# No file path — nothing to check
[ -z "$FILE_PATH" ] && exit 0

# Get just the filename and extension for quick filtering
BASENAME=$(basename "$FILE_PATH")
EXT="${BASENAME##*.}"

# Skip non-testable file types (shell pre-filter)
case "$EXT" in
    md|json|yaml|yml|toml|cfg|ini|lock|txt|csv|svg|png|jpg|gif|ico) exit 0 ;;
esac

# Skip non-testable directories
case "$FILE_PATH" in
    */.claude/*|.claude/*|docs/*|node_modules/*|.git/*|dist/*|build/*|bin/*|obj/*) exit 0 ;;
    *.env|*.env.*|*.gitignore|*.dockerignore) exit 0 ;;
esac

# Check if this is a test file — precise patterns only (avoids false positives
# like src/contest/handler.py or lib/spectrum.ts)
IS_TEST=false
case "$BASENAME" in
    test_*|*_test.*|*_spec.*|*.test.*|*.spec.*|*Tests.*|*Spec.*) IS_TEST=true ;;
esac
case "$FILE_PATH" in
    *__tests__/*) IS_TEST=true ;;
esac

if [ "$IS_TEST" = true ]; then
    # Test file being written — create the session marker
    touch "$MARKER"
    exit 0
fi

# Source file being written — check for marker (skip if marker is a symlink)
if [ -L "$MARKER" ]; then
    exit 0
fi
if [ ! -f "$MARKER" ]; then
    echo "WARNING: Writing source file before any test file in this session. TDD recommends writing tests first." >&2
fi

exit 0
