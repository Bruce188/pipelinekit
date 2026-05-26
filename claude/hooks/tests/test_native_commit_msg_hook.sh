#!/bin/bash
# Test for native commit-msg hook install (F5).
# Scratch-repo smoke test: assert wrapper enforces validator across all git commit
# invocations, with backup + idempotency.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"

WRAPPER="$REPO_ROOT/claude/hooks/commit-msg-wrapper.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "PASS  $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "FAIL  $1"; [ -n "${2:-}" ] && echo "      $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# Sandbox setup.
SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-native-commit-msg-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

(
  cd "$SANDBOX"
  git init -b main >/dev/null 2>&1
  git config user.email "t@t.com"
  git config user.name "test"
  git commit --allow-empty -m "init: empty base" >/dev/null 2>&1
)

# --- Case 1: wrapper file exists and is executable ---
if [ -f "$WRAPPER" ] && [ -x "$WRAPPER" ]; then
  pass "case 1: wrapper file exists + executable"
else
  fail "case 1: wrapper file exists + executable" "expected $WRAPPER to exist and be executable"
fi

# Install symlink (simulates what install_native_commit_msg_hook would do).
# Guard: only install if wrapper exists. If wrapper is absent we still want
# subsequent cases to execute to confirm RED semantics.
if [ -f "$WRAPPER" ]; then
  ln -sfn "$WRAPPER" "$SANDBOX/.git/hooks/commit-msg"
  chmod +x "$WRAPPER" 2>/dev/null || true
fi

# --- Case 2: bad commit subject -> non-zero, stderr cites conventional-commit ---
out2_exit=0
out2_stderr=$( cd "$SANDBOX" && git commit --allow-empty -m "bad commit" 2>&1 ) || out2_exit=$?
if [ "$out2_exit" -ne 0 ] && printf '%s' "$out2_stderr" | grep -qiE 'conventional-commit|forbidden|emoji'; then
  pass "case 2: bad subject rejected with validator error"
else
  fail "case 2: bad subject rejected with validator error" "exit=$out2_exit stderr=$out2_stderr"
fi

# --- Case 3: valid feat: commit succeeds ---
out3_exit=0
out3_stderr=$( cd "$SANDBOX" && git commit --allow-empty -m "feat: valid subject" 2>&1 ) || out3_exit=$?
if [ "$out3_exit" -eq 0 ]; then
  pass "case 3: valid feat: commit accepted"
else
  fail "case 3: valid feat: commit accepted" "exit=$out3_exit stderr=$out3_stderr"
fi

# --- Case 4: emoji commit -> non-zero (emoji ban) ---
out4_exit=0
out4_stderr=$( cd "$SANDBOX" && git commit --allow-empty -m "chore: ship $(printf '\xf0\x9f\x9a\x80') feature" 2>&1 ) || out4_exit=$?
if [ "$out4_exit" -ne 0 ] && printf '%s' "$out4_stderr" | grep -qi 'emoji'; then
  pass "case 4: emoji subject rejected"
else
  fail "case 4: emoji subject rejected" "exit=$out4_exit stderr=$out4_stderr"
fi

# --- Case 5: empty / missing message file -> silent exit 0 (rebase reword) ---
# Invoke the hook directly with a zero-byte message file.
EMPTY_MSG="$SANDBOX/empty-msg-$$"
: > "$EMPTY_MSG"
out5_exit=0
if [ -x "$SANDBOX/.git/hooks/commit-msg" ]; then
  ( cd "$SANDBOX" && bash "$SANDBOX/.git/hooks/commit-msg" "$EMPTY_MSG" ) >/dev/null 2>&1 || out5_exit=$?
else
  out5_exit=99
fi
# Also test missing argument case.
out5b_exit=0
if [ -x "$SANDBOX/.git/hooks/commit-msg" ]; then
  ( cd "$SANDBOX" && bash "$SANDBOX/.git/hooks/commit-msg" ) >/dev/null 2>&1 || out5b_exit=$?
else
  out5b_exit=99
fi
if [ "$out5_exit" -eq 0 ] && [ "$out5b_exit" -eq 0 ]; then
  pass "case 5: empty/missing message file -> silent exit 0"
else
  fail "case 5: empty/missing message file -> silent exit 0" "empty=$out5_exit missing=$out5b_exit"
fi
rm -f "$EMPTY_MSG"

# --- Case 6: alien pre-existing hook -> backed up to .pre-pipelinekit ---
# Reset sandbox hook to an alien script and re-run the inline install logic.
rm -f "$SANDBOX/.git/hooks/commit-msg"
rm -f "$SANDBOX/.git/hooks/commit-msg.pre-pipelinekit"
cat > "$SANDBOX/.git/hooks/commit-msg" <<'ALIEN'
#!/bin/sh
exit 0
ALIEN
chmod +x "$SANDBOX/.git/hooks/commit-msg"
inline_install() {
  local target="$1"
  local wrapper_src="$2"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$wrapper_src" ]; then
    echo "already linked"
    return 0
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    local backup="$target.pre-pipelinekit"
    [ -e "$backup" ] && backup="$backup.$(date +%s)"
    mv "$target" "$backup"
    echo "backed up -> $backup"
  fi
  ln -sfn "$wrapper_src" "$target"
}
out6_log=$( inline_install "$SANDBOX/.git/hooks/commit-msg" "$WRAPPER" )
if [ -L "$SANDBOX/.git/hooks/commit-msg" ] \
   && [ -e "$SANDBOX/.git/hooks/commit-msg.pre-pipelinekit" ] \
   && printf '%s' "$out6_log" | grep -q "backed up"; then
  pass "case 6: alien hook backed up + symlink installed"
else
  fail "case 6: alien hook backed up + symlink installed" "log=$out6_log target_is_symlink=$([ -L "$SANDBOX/.git/hooks/commit-msg" ] && echo yes || echo no) backup_exists=$([ -e "$SANDBOX/.git/hooks/commit-msg.pre-pipelinekit" ] && echo yes || echo no)"
fi

# --- Case 7: idempotency -> second invocation no-op, no second backup ---
backup_count_before=$(find "$SANDBOX/.git/hooks" -maxdepth 1 -name 'commit-msg.pre-pipelinekit*' | wc -l)
out7_log=$( inline_install "$SANDBOX/.git/hooks/commit-msg" "$WRAPPER" )
backup_count_after=$(find "$SANDBOX/.git/hooks" -maxdepth 1 -name 'commit-msg.pre-pipelinekit*' | wc -l)
if [ "$backup_count_before" = "$backup_count_after" ] \
   && printf '%s' "$out7_log" | grep -q "already linked"; then
  pass "case 7: idempotent re-install -> no extra backup"
else
  fail "case 7: idempotent re-install -> no extra backup" "before=$backup_count_before after=$backup_count_after log=$out7_log"
fi

echo ""
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
