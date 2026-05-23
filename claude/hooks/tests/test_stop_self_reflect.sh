#!/usr/bin/env bash
set -uo pipefail
# test_stop_self_reflect.sh — bash smoke for stop-self-reflect.sh.
#
# Asserts:
#   01: script exists, exec-bit set, bash -n clean.
#   02: opt-out env-var PIPELINE_NO_SELF_REFLECT=1 -> exit 0 + no artifact.
#   03: CLAUDE_BIN points at non-existent path -> exit 0 + no artifact, stderr informational.
#   04: happy path — mock claude -p emits stub JSON -> exit 0 + docs/claude-md-proposal-v1.md present
#       with the JSON embedded.
#   05: version increment — existing v1 -> second run writes v2; both files present.
#   06: timeout enforced — mock claude -p sleeps 90s; hook exits within 65s (still exit 0).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$(cd "$SCRIPT_DIR/.." && pwd)/stop-self-reflect.sh"

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

# Helper: build a mock `claude` binary in $1/bin/claude that emits $2 to stdout.
# Any args after $2 are appended as bash commands inside the mock (e.g. "sleep 90").
make_mock_claude() {
  local bindir="$1/bin"
  local payload="$2"
  local prelude="${3:-}"
  mkdir -p "$bindir"
  cat >"$bindir/claude" <<MOCK
#!/usr/bin/env bash
${prelude}
cat <<'JSON'
${payload}
JSON
MOCK
  chmod +x "$bindir/claude"
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
# test_02: opt-out env-var -> exit 0, no artifact created.
# ---------------------------------------------------------------------------
T2_DIR="$SANDBOX/t02"
mkdir -p "$T2_DIR/docs"
(
  cd "$T2_DIR"
  git init -q -b main >/dev/null
)
T2_EXIT=0
(cd "$T2_DIR" && PIPELINE_NO_SELF_REFLECT=1 bash "$HOOK" </dev/null >/dev/null 2>&1) || T2_EXIT=$?
T2_ARTIFACTS=$(ls "$T2_DIR/docs"/claude-md-proposal-v*.md 2>/dev/null | wc -l)
if [ "$T2_EXIT" = "0" ] && [ "$T2_ARTIFACTS" = "0" ]; then
  record "test_02_opt_out_env_var" PASS
else
  record "test_02_opt_out_env_var" FAIL "exit=$T2_EXIT, artifacts=$T2_ARTIFACTS"
fi

# ---------------------------------------------------------------------------
# test_03: missing claude binary -> exit 0, no artifact, stderr informational.
# ---------------------------------------------------------------------------
T3_DIR="$SANDBOX/t03"
mkdir -p "$T3_DIR/docs"
(
  cd "$T3_DIR"
  git init -q -b main >/dev/null
)
T3_EXIT=0
T3_ERR_FILE="$SANDBOX/t03.stderr"
(cd "$T3_DIR" && CLAUDE_BIN="/nonexistent/path/claude-binary-xyz" \
  PATH="/usr/bin:/bin" \
  bash "$HOOK" </dev/null >/dev/null 2>"$T3_ERR_FILE") || T3_EXIT=$?
T3_ARTIFACTS=$(ls "$T3_DIR/docs"/claude-md-proposal-v*.md 2>/dev/null | wc -l)
T3_HAS_INFO=0
grep -q "claude" "$T3_ERR_FILE" 2>/dev/null && T3_HAS_INFO=1
if [ "$T3_EXIT" = "0" ] && [ "$T3_ARTIFACTS" = "0" ] && [ "$T3_HAS_INFO" = "1" ]; then
  record "test_03_missing_claude_binary" PASS
else
  T3_STDERR="$(cat "$T3_ERR_FILE" 2>/dev/null || true)"
  record "test_03_missing_claude_binary" FAIL "exit=$T3_EXIT, artifacts=$T3_ARTIFACTS, stderr=$T3_STDERR"
fi

# ---------------------------------------------------------------------------
# test_04: happy path — stub claude -p emits JSON, artifact landed at v1.
# ---------------------------------------------------------------------------
T4_DIR="$SANDBOX/t04"
mkdir -p "$T4_DIR/docs"
(
  cd "$T4_DIR"
  git init -q -b main >/dev/null
)
make_mock_claude "$T4_DIR" '{"proposals":[]}'
T4_EXIT=0
(cd "$T4_DIR" && CLAUDE_BIN="$T4_DIR/bin/claude" bash "$HOOK" </dev/null >/dev/null 2>&1) || T4_EXIT=$?
T4_ARTIFACT="$T4_DIR/docs/claude-md-proposal-v1.md"
T4_HAS_JSON=0
if [ -f "$T4_ARTIFACT" ] && grep -q '"proposals"' "$T4_ARTIFACT"; then
  T4_HAS_JSON=1
fi
if [ "$T4_EXIT" = "0" ] && [ "$T4_HAS_JSON" = "1" ]; then
  record "test_04_happy_path_v1_written" PASS
else
  record "test_04_happy_path_v1_written" FAIL "exit=$T4_EXIT, artifact=$T4_ARTIFACT, hasJson=$T4_HAS_JSON"
fi

# ---------------------------------------------------------------------------
# test_05: version increment — pre-existing v1 -> second run writes v2.
# ---------------------------------------------------------------------------
T5_DIR="$SANDBOX/t05"
mkdir -p "$T5_DIR/docs"
(
  cd "$T5_DIR"
  git init -q -b main >/dev/null
)
make_mock_claude "$T5_DIR" '{"proposals":[]}'
# Seed v1.
echo "# pre-existing v1" >"$T5_DIR/docs/claude-md-proposal-v1.md"
T5_EXIT=0
(cd "$T5_DIR" && CLAUDE_BIN="$T5_DIR/bin/claude" bash "$HOOK" </dev/null >/dev/null 2>&1) || T5_EXIT=$?
T5_V1_PRESENT=0
T5_V2_PRESENT=0
[ -f "$T5_DIR/docs/claude-md-proposal-v1.md" ] && T5_V1_PRESENT=1
[ -f "$T5_DIR/docs/claude-md-proposal-v2.md" ] && T5_V2_PRESENT=1
if [ "$T5_EXIT" = "0" ] && [ "$T5_V1_PRESENT" = "1" ] && [ "$T5_V2_PRESENT" = "1" ]; then
  record "test_05_version_increment" PASS
else
  record "test_05_version_increment" FAIL "exit=$T5_EXIT, v1=$T5_V1_PRESENT, v2=$T5_V2_PRESENT"
fi

# ---------------------------------------------------------------------------
# test_06: timeout enforced — mock sleeps 90s; hook exits within 65s.
# ---------------------------------------------------------------------------
T6_DIR="$SANDBOX/t06"
mkdir -p "$T6_DIR/docs"
(
  cd "$T6_DIR"
  git init -q -b main >/dev/null
)
make_mock_claude "$T6_DIR" '{"proposals":[]}' 'sleep 90'
T6_EXIT=0
T6_START=$SECONDS
(cd "$T6_DIR" && CLAUDE_BIN="$T6_DIR/bin/claude" bash "$HOOK" </dev/null >/dev/null 2>&1) || T6_EXIT=$?
T6_ELAPSED=$((SECONDS - T6_START))
if [ "$T6_EXIT" = "0" ] && [ "$T6_ELAPSED" -lt 65 ]; then
  record "test_06_timeout_enforced" PASS
else
  record "test_06_timeout_enforced" FAIL "exit=$T6_EXIT, elapsed=${T6_ELAPSED}s"
fi

# ---------------------------------------------------------------------------
echo "Results: $PASS PASS / $FAIL FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0
