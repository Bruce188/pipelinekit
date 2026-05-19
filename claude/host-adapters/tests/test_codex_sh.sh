#!/usr/bin/env bash
set -uo pipefail
# NOTE: deliberately NOT set -e — tests observe non-zero exits

ADAPTER="$(cd "$(dirname "$0")/.." && pwd)/codex.sh"

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
PASS_COUNT=0; FAIL_COUNT=0
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }
pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
assert_eq() { [ "$1" = "$2" ] && pass "$3" || fail "$3 (got=$1 want=$2)"; }
assert_file_contains() { grep -qF -- "$2" "$1" && pass "$3" || fail "$3 (file $1 missing '$2')"; }
assert_file_absent() { [ ! -e "$1" ] && pass "$2" || fail "$2 (file $1 exists)"; }

# ---------------------------------------------------------------------------
# Helper: write stub codex binary into a given STUB_DIR
# The stub captures argv (one arg per line), stdin, and exits with the code
# in $STUB_DIR/exit-code (defaults to 0).
# ---------------------------------------------------------------------------
write_stub() {
  local stub_dir="$1"
  cat > "$stub_dir/codex" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$@" > "${stub_dir}/argv"
cat > "${stub_dir}/stdin"
EC_FILE="${stub_dir}/exit-code"
EC=0; [ -f "\$EC_FILE" ] && EC=\$(cat "\$EC_FILE")
echo "STUB_OUT"
echo "STUB_ERR" >&2
exit "\$EC"
STUB
  chmod +x "$stub_dir/codex"
}

# ---------------------------------------------------------------------------
# AC1: non-zero exit from codex is propagated; output/exit file written
# ---------------------------------------------------------------------------
test_ac1_nonzero_exit_propagates() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"
  echo "42" > "$STUB_DIR/exit-code"

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  local ACTUAL_EC
  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" 2>/dev/null; ACTUAL_EC=$?

  assert_eq "$ACTUAL_EC" "42" "AC1: exit code propagated (42)"
  assert_file_contains "$TASK_ROOT/.claude/tasks/T_abc/output/exit" "42" "AC1: output/exit contains 42"
  assert_file_contains "$OUTPUT_FILE" "STUB_OUT" "AC1: out.txt contains STUB_OUT"
}

# ---------------------------------------------------------------------------
# AC2: zero exit produces no 'unbound variable' in stderr
# ---------------------------------------------------------------------------
test_ac2_zero_exit_no_unbound() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"
  # exit-code file absent → stub exits 0

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  local STDERR_FILE
  STDERR_FILE=$(mktemp)
  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" 2>"$STDERR_FILE"

  if grep -q "unbound variable" "$STDERR_FILE"; then
    fail "AC2: stderr contains 'unbound variable'"
  else
    pass "AC2: no 'unbound variable' in stderr"
  fi
  rm -f "$STDERR_FILE"
}

# ---------------------------------------------------------------------------
# AC3: OUTPUT_DIR is derived correctly — <task-dir>/output not parent/output
# ---------------------------------------------------------------------------
test_ac3_output_dir_preserves_taskid() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" || true

  # Correct path: .claude/tasks/T_abc/output/exit
  if [ -f "$TASK_ROOT/.claude/tasks/T_abc/output/exit" ]; then
    pass "AC3: output/exit in correct task dir"
  else
    fail "AC3: output/exit missing from correct task dir ($TASK_ROOT/.claude/tasks/T_abc/output/exit)"
  fi

  # Wrong path (bug): .claude/tasks/output/exit (parent-dir bug)
  assert_file_absent "$TASK_ROOT/.claude/tasks/output/exit" "AC3: no output/exit in parent tasks dir"
}

# ---------------------------------------------------------------------------
# AC4: else-branch captures exit code; stderr NOT merged with stdout
# ---------------------------------------------------------------------------
test_ac4_else_branch_captures_ec() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"
  echo "7" > "$STUB_DIR/exit-code"

  # Prompt path that does NOT match .claude/tasks/<id>/ → else branch
  local PROMPT_FILE="$TASK_ROOT/somewhere/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "prompt" > "$PROMPT_FILE"

  local STDERR_FILE
  STDERR_FILE=$(mktemp)
  local ACTUAL_EC
  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" 2>"$STDERR_FILE"; ACTUAL_EC=$?

  assert_eq "$ACTUAL_EC" "7" "AC4: else-branch exit code propagated (7)"
  assert_file_contains "$OUTPUT_FILE" "STUB_OUT" "AC4: out.txt contains STUB_OUT"

  # stderr must NOT be in stdout file
  if grep -qF "STUB_ERR" "$OUTPUT_FILE"; then
    fail "AC4: out.txt must not contain STUB_ERR (stderr leaked into stdout)"
  else
    pass "AC4: STUB_ERR not in out.txt"
  fi

  # stderr must be in captured stderr
  assert_file_contains "$STDERR_FILE" "STUB_ERR" "AC4: stderr captured separately"
  rm -f "$STDERR_FILE"
}

# ---------------------------------------------------------------------------
# AC5: prompt is passed as positional argument (not via stdin)
# ---------------------------------------------------------------------------
test_ac5_positional_prompt() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" || true

  # The stub writes each argv arg on its own line; prompt content should appear
  if grep -Fxq "test prompt" "$STUB_DIR/argv"; then
    pass "AC5: prompt content passed as positional arg"
  else
    fail "AC5: prompt content not found in argv (not passed as positional arg)"
  fi
}

# ---------------------------------------------------------------------------
# AC6: no -p or --prompt-file flag in argv
# ---------------------------------------------------------------------------
test_ac6_no_prompt_file_flag() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" || true

  if grep -qE '^(-p|--prompt-file)$' "$STUB_DIR/argv"; then
    fail "AC6: found -p or --prompt-file in argv"
  else
    pass "AC6: no -p or --prompt-file flag in argv"
  fi
}

# ---------------------------------------------------------------------------
# AC7: codex unavailable → exit 2 + WORKER_UNAVAILABLE message
# ---------------------------------------------------------------------------
test_ac7_unavailable_exit_2() {
  local TASK_ROOT
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$TASK_ROOT"' RETURN

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  local STDERR_FILE
  STDERR_FILE=$(mktemp)
  local ACTUAL_EC
  # Use PATH that has no codex binary
  PATH="/usr/bin:/bin" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" 2>"$STDERR_FILE"; ACTUAL_EC=$?

  assert_eq "$ACTUAL_EC" "2" "AC7: exit code 2 when codex unavailable"
  assert_file_contains "$STDERR_FILE" "WORKER_UNAVAILABLE: codex (host-adapter missing)" "AC7: WORKER_UNAVAILABLE message"
  rm -f "$STDERR_FILE"
}

# ---------------------------------------------------------------------------
# AC8: --model and --max-turns are forwarded to codex
# ---------------------------------------------------------------------------
test_ac8_forwards_model_max_turns() {
  local STUB_DIR TASK_ROOT
  STUB_DIR=$(mktemp -d)
  TASK_ROOT=$(mktemp -d)
  trap 'rm -rf "$STUB_DIR" "$TASK_ROOT"' RETURN

  write_stub "$STUB_DIR"

  local PROMPT_FILE="$TASK_ROOT/.claude/tasks/T_abc/prompt.md"
  local OUTPUT_FILE="$TASK_ROOT/out.txt"
  mkdir -p "$(dirname "$PROMPT_FILE")"
  echo "test prompt" > "$PROMPT_FILE"

  PATH="$STUB_DIR:$PATH" bash "$ADAPTER" "$PROMPT_FILE" "$OUTPUT_FILE" --model o4-mini --max-turns 3; true

  assert_file_contains "$STUB_DIR/argv" "--model" "AC8: --model in argv"
  assert_file_contains "$STUB_DIR/argv" "o4-mini" "AC8: o4-mini in argv"
  assert_file_contains "$STUB_DIR/argv" "--max-turns" "AC8: --max-turns in argv"
  assert_file_contains "$STUB_DIR/argv" "3" "AC8: max-turns value 3 in argv"
}

# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------
TESTS=(
  test_ac1_nonzero_exit_propagates
  test_ac2_zero_exit_no_unbound
  test_ac3_output_dir_preserves_taskid
  test_ac4_else_branch_captures_ec
  test_ac5_positional_prompt
  test_ac6_no_prompt_file_flag
  test_ac7_unavailable_exit_2
  test_ac8_forwards_model_max_turns
)
for t in "${TESTS[@]}"; do "$t"; done
echo "RESULT: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ]
