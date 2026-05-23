#!/usr/bin/env bash
set -euo pipefail
# test_session_start_context.sh — bash smoke for session-start-context.sh.
#
# Asserts:
#   01: script exists, exec-bit set, bash -n clean.
#   02: not-a-git-repo case -> exit 0 + "(not a git repo)" in output.
#   03: opt-out env-var -> exit 0 + empty stdout.
#   04: 4 expected H2 blocks present in output (Branch, Working Tree, Recent Commits, Unstaged Diff Summary).
#   05: 8 KB cap honoured on a repo with > 1000 unstaged-diff lines.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$(cd "$SCRIPT_DIR/.." && pwd)/session-start-context.sh"

SANDBOX="$(mktemp -d)"
cleanup() {
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

PASS=0
FAIL=0
FAILED_NAMES=()

record() {
  local name="$1" outcome="$2" detail="${3:-}"
  if [ "$outcome" = "PASS" ]; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name — $detail"
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# test_01: script exists + exec-bit set + bash -n clean.
# ---------------------------------------------------------------------------
if [ -f "$HOOK" ] && [ -x "$HOOK" ] && bash -n "$HOOK"; then
  record "test_01_script_exists_exec_syntax_clean" PASS
else
  record "test_01_script_exists_exec_syntax_clean" FAIL "missing, not executable, or bash -n failed for $HOOK"
fi

# ---------------------------------------------------------------------------
# test_02: not-a-git-repo case.
# ---------------------------------------------------------------------------
T2_DIR="$SANDBOX/t02"
mkdir -p "$T2_DIR"
T2_OUT=$(cd "$T2_DIR" && bash "$HOOK" </dev/null 2>/dev/null)
T2_EXIT=$?
if [ "$T2_EXIT" = "0" ] && echo "$T2_OUT" | grep -qF '(not a git repo)'; then
  record "test_02_not_a_git_repo" PASS
else
  record "test_02_not_a_git_repo" FAIL "exit=$T2_EXIT, output=$T2_OUT"
fi

# ---------------------------------------------------------------------------
# test_03: opt-out env-var -> exit 0, empty stdout.
# ---------------------------------------------------------------------------
T3_OUT=$(PIPELINE_NO_SESSION_START_CONTEXT=1 bash "$HOOK" </dev/null 2>/dev/null)
T3_EXIT=$?
if [ "$T3_EXIT" = "0" ] && [ -z "$T3_OUT" ]; then
  record "test_03_opt_out_env_var" PASS
else
  record "test_03_opt_out_env_var" FAIL "exit=$T3_EXIT, len=${#T3_OUT}"
fi

# ---------------------------------------------------------------------------
# test_04: 4 expected H2 blocks present in output.
# ---------------------------------------------------------------------------
T4_DIR="$SANDBOX/t04"
mkdir -p "$T4_DIR"
(
  cd "$T4_DIR"
  git init -q -b main
  git config user.email "test@example.com"
  git config user.name "Test"
  echo "hello" > a.txt
  git add a.txt
  git commit -q -m "chore: initial commit"
  echo "more" >> a.txt
)
T4_OUT=$(cd "$T4_DIR" && bash "$HOOK" </dev/null 2>/dev/null)
T4_EXIT=$?
T4_MISSING=""
for hdr in '^## Branch' '^## Working Tree' '^## Recent Commits' '^## Unstaged Diff Summary'; do
  echo "$T4_OUT" | grep -qE "$hdr" || T4_MISSING="$T4_MISSING $hdr"
done
if [ "$T4_EXIT" = "0" ] && [ -z "$T4_MISSING" ]; then
  record "test_04_four_h2_blocks_present" PASS
else
  record "test_04_four_h2_blocks_present" FAIL "exit=$T4_EXIT, missing:$T4_MISSING"
fi

# ---------------------------------------------------------------------------
# test_05: 8 KB cap on a repo with > 1000 unstaged-diff lines.
# ---------------------------------------------------------------------------
T5_DIR="$SANDBOX/t05"
mkdir -p "$T5_DIR"
(
  cd "$T5_DIR"
  git init -q -b main
  git config user.email "test@example.com"
  git config user.name "Test"
  for i in $(seq 1 60); do
    printf 'line %d\n' "$i" > "file_$i.txt"
  done
  git add .
  git commit -q -m "chore: seed"
  # Generate > 1000 unstaged-diff lines by churning each file.
  for i in $(seq 1 60); do
    for j in $(seq 1 30); do
      printf 'extra line %d-%d\n' "$i" "$j" >> "file_$i.txt"
    done
  done
)
T5_OUT=$(cd "$T5_DIR" && bash "$HOOK" </dev/null 2>/dev/null)
T5_EXIT=$?
T5_BYTES=$(printf '%s' "$T5_OUT" | wc -c)
if [ "$T5_EXIT" = "0" ] && [ "$T5_BYTES" -le 8192 ]; then
  record "test_05_eight_kb_cap" PASS
else
  record "test_05_eight_kb_cap" FAIL "exit=$T5_EXIT, bytes=$T5_BYTES"
fi

# ---------------------------------------------------------------------------
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
