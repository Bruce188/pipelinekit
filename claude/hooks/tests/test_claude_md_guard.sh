#!/usr/bin/env bash
# Test runner for claude/hooks/claude-md-guard.py — 8 cases per plan-v15.md § 5.

set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/claude-md-guard.py"
[ -x "$HOOK" ] || { echo "FAIL: hook not executable: $HOOK"; exit 1; }

TMPDIR_BASE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

PASS=0
FAIL=0

run_case() {
  local name="$1"
  local payload="$2"
  local expected_exit="$3"
  local expected_stderr_substr="$4"

  local actual_stderr
  local actual_exit
  actual_stderr=$(printf '%s' "$payload" | python3 "$HOOK" 2>&1 >/dev/null)
  actual_exit=$?

  if [ "$actual_exit" != "$expected_exit" ]; then
    echo "FAIL: $name: expected exit $expected_exit, got $actual_exit (stderr: $actual_stderr)"
    FAIL=$((FAIL+1))
    return
  fi
  if [ -n "$expected_stderr_substr" ]; then
    if ! echo "$actual_stderr" | grep -q -- "$expected_stderr_substr"; then
      echo "FAIL: $name: stderr missing '$expected_stderr_substr' (got: $actual_stderr)"
      FAIL=$((FAIL+1))
      return
    fi
  fi
  echo "PASS: $name"
  PASS=$((PASS+1))
}

# T1: non-CLAUDE.md path
run_case T1 \
  '{"tool_name":"Write","tool_input":{"file_path":"/tmp/foo/bar.md","content":"hello"}}' \
  0 ""

# T2: 6000 lines
big=$(python3 -c "print('\n'.join(['# Title'] + ['line']*6000))")
payload=$(python3 -c "import json,sys; print(json.dumps({'tool_name':'Write','tool_input':{'file_path':'/tmp/CLAUDE.md','content':sys.stdin.read()}}))" <<< "$big")
run_case T2 "$payload" 2 "CM002"

# T3: no top-level heading
payload='{"tool_name":"Write","tool_input":{"file_path":"/tmp/CLAUDE.md","content":"## Subheading\nbody"}}'
run_case T3 "$payload" 2 "CM003"

# T4: valid content
payload='{"tool_name":"Write","tool_input":{"file_path":"/tmp/CLAUDE.md","content":"# Title\nbody"}}'
run_case T4 "$payload" 0 ""

# T5: Edit with replacement that exists
target="$TMPDIR_BASE/CLAUDE.md"
printf '# Title\nfoo bar\n' > "$target"
payload=$(python3 -c "import json; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':'$target','old_string':'foo','new_string':'baz'}}))")
run_case T5 "$payload" 0 ""

# T6: Edit with replacement that does NOT exist
payload=$(python3 -c "import json; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':'$target','old_string':'nonexistent','new_string':'baz'}}))")
run_case T6 "$payload" 0 ""

# T7: banned phrase + valid heading
payload='{"tool_name":"Write","tool_input":{"file_path":"/tmp/CLAUDE.md","content":"# Title\nCo-Authored-By: Claude\n"}}'
run_case T7 "$payload" 0 "CM005"

# T8: malformed JSON
run_case T8 "not-a-json" 0 "WARN: could not parse stdin"

TOTAL=$((PASS+FAIL))
echo "$PASS/$TOTAL tests passed"
exit $FAIL
