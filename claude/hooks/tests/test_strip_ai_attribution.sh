#!/usr/bin/env bash
# test_strip_ai_attribution.sh — smoke test for strip-ai-attribution.sh.
#
# ACs:
#   1. Non-push command exits 0 fast (no gh invocation).
#   2. `git push` invokes mocked gh with `pr view ... --json number`.
#   3. Hook does NOT exit non-zero even when gh fails or PR absent.
#   4. Log file is created under sandbox HOME (rotation surface exists).
#
# Mocking strategy: PATH-shadow `gh` via $SANDBOX/bin/gh stub. The stub
# writes its argv to a marker file. After hook returns we `wait` for any
# backgrounded subshell (the hook runs gh in `(...) &`).
#
# Real git binary IS used inside the scratch repo for `git rev-parse HEAD`.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../strip-ai-attribution.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found at $HOOK"
  exit 1
fi

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/pkit-strip-ai-XXXXXX")
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILED=()

pass() { echo "PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $1 -- ${2:-}"; FAIL=$((FAIL + 1)); FAILED+=("$1"); }

# Build a scratch git repo so `git rev-parse --abbrev-ref HEAD` resolves.
REPO="$SANDBOX/repo"
mkdir -p "$REPO"
(
  cd "$REPO"
  git init -b feature/test-branch >/dev/null 2>&1
  git config user.email "t@t.test"
  git config user.name "test"
  git commit --allow-empty -m "init: empty" >/dev/null 2>&1
) || { echo "FAIL: could not init scratch repo"; exit 1; }

# PATH-shadow gh — stub writes argv to marker file and returns valid JSON.
MOCK_BIN="$SANDBOX/bin"
MARKER="$SANDBOX/gh-invoked.log"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/gh" <<MOCK_GH
#!/usr/bin/env bash
# Capture argv to marker
printf '%s\\n' "\$*" >> "$MARKER"
# pr view -> emit a fake PR-number JSON OR body
if [[ "\$*" == *"--json number"* ]]; then
  printf '{"number": 42}\\n'
elif [[ "\$*" == *"--json body"* ]]; then
  printf 'feat: x\\n\\nco-authored-by: Claude <noreply@anthropic.com>\\n'
else
  exit 0
fi
MOCK_GH
chmod +x "$MOCK_BIN/gh"

call_hook() {
  local cmd="$1"
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input': {'command': sys.argv[1]}}))" "$cmd")
  HOME="$SANDBOX" PATH="$MOCK_BIN:$PATH" sh -c "cd '$REPO' && printf '%s' '$payload' | bash '$HOOK'" 2>/dev/null
}

# ─── AC1: non-push command → fast exit 0, no marker ───────────────────────────
EXIT=0
call_hook "ls -la" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 0 ] && [ ! -f "$MARKER" ]; then
  pass "AC1_non_push_no_gh_call"
else
  fail "AC1_non_push_no_gh_call" "expected exit 0 + no marker, got exit=$EXIT marker=$([ -f "$MARKER" ] && echo present)"
fi

# ─── AC2: git push → gh pr view called ────────────────────────────────────────
EXIT=0
call_hook "git push origin feature/test-branch" >/dev/null || EXIT=$?
# Hook backgrounds gh in (...) & — wait for completion.
# Allow generous timeout: poll marker for up to ~3 s.
for _ in 1 2 3 4 5 6; do
  if [ -f "$MARKER" ] && grep -q "pr view" "$MARKER"; then
    break
  fi
  sleep 0.5
done

if [ "$EXIT" -eq 0 ] && [ -f "$MARKER" ] && grep -q "pr view" "$MARKER"; then
  pass "AC2_git_push_invokes_gh_pr_view"
else
  fail "AC2_git_push_invokes_gh_pr_view" "expected exit 0 + pr view marker; exit=$EXIT marker=$([ -f "$MARKER" ] && cat "$MARKER" || echo absent)"
fi

# ─── AC3: hook never exits non-zero even on gh failure ────────────────────────
# Replace mock gh with one that exits non-zero.
cat > "$MOCK_BIN/gh" <<'MOCK_GH_FAIL'
#!/usr/bin/env bash
exit 1
MOCK_GH_FAIL
chmod +x "$MOCK_BIN/gh"

EXIT=0
call_hook "git push origin feature/test-branch" >/dev/null || EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  pass "AC3_hook_exit_0_on_gh_failure"
else
  fail "AC3_hook_exit_0_on_gh_failure" "expected exit 0 even when gh fails, got $EXIT"
fi

# ─── AC4: log directory created under sandbox HOME ────────────────────────────
# Wait briefly for backgrounded subshell to write the log.
for _ in 1 2 3 4 5 6; do
  if [ -d "$SANDBOX/.claude/logs" ]; then
    break
  fi
  sleep 0.5
done
if [ -d "$SANDBOX/.claude/logs" ]; then
  pass "AC4_log_dir_created_under_sandbox_home"
else
  fail "AC4_log_dir_created_under_sandbox_home" "expected $SANDBOX/.claude/logs to exist"
fi

# ─── Report ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED[*]}"
  exit 1
fi
exit 0
