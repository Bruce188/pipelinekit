---
name: test-hooks
description: Run hook tests and summarize results. Auto-loads when working on files under .claude/hooks/. Use to verify hook correctness after changes to hook scripts or tests.
allowed-tools: Bash
paths:
  - "**/.claude/hooks/**"
---

# Hook Test Runner

Run all hook unit tests under `~/.claude/hooks/tests/` and print a concise pass/fail summary. Always exits 0 — advisory only.

## Usage

```
/test-hooks
```

## Body

```bash
#!/usr/bin/env bash
set -uo pipefail

TEST_DIR="$HOME/.claude/hooks/tests"
PASS=0
FAIL=0
FAIL_NAMES=()
declare -A FAIL_OUTPUT

# Discover test files by glob -- never hardcoded names
shopt -s nullglob
TEST_FILES=("$TEST_DIR"/test_*.py)
shopt -u nullglob

if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
  echo "hook-tests: no test files found in $TEST_DIR"
  exit 0
fi

for f in "${TEST_FILES[@]}"; do
  name="$(basename "$f")"
  output="$(python3 "$f" 2>&1)"
  rc=$?
  if [[ $rc -eq 0 ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    FAIL_NAMES+=("$name")
    FAIL_OUTPUT["$name"]="$output"
  fi
done

TOTAL=$((PASS + FAIL))
echo "hook-tests: $TOTAL total | $PASS passed | $FAIL failed"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for name in "${FAIL_NAMES[@]}"; do
    echo "  FAIL: $name"
    # Print first 10 lines of output as excerpt
    excerpt="$(printf '%s' "${FAIL_OUTPUT[$name]}" | head -n 10)"
    while IFS= read -r line; do
      echo "    $line"
    done <<< "$excerpt"
  done
fi

exit 0
```
