#!/bin/bash
# SessionStart hook: sum RSS of known MCP daemons. Warn (NOT kill) if over cap.
#
# Motivation: WSL2 RAM ceiling. The default MCP stack (agentmemory + codegraph +
# graphify + understand-anything) lives at ~150-200 MB sustained per daemon, and
# serena drags heavy language servers (EclipseJDTLS alone is Xmx3G). Each Claude
# session spawns its OWN copy of every stdio MCP, so N concurrent sessions multiply
# the footprint N-fold. The cap therefore scales by detected session count; a sum
# over the effective cap indicates leakage or runaway state — emit a warning so the
# user can disable a tool via PIPELINE_DISABLE_<TOOL>=1, scope serena to a
# per-project .mcp.json, or close idle sessions.
#
# Contract:
#   - Reads JSON envelope from stdin (consumed and discarded).
#   - Pure bash + ps + python3 stdlib — NO claude -p, NO LLM subprocess.
#   - Idempotent — emits identical output on identical RSS state.
#   - Exits 0 unconditionally (SessionStart hooks must never block).
#   - DOES NOT KILL processes — only warns. Killing live daemons would interrupt
#     active sessions.
#   - Honours PIPELINE_NO_RSS_CAP=1 as opt-out (no work, exit 0).
#   - Honours PIPELINE_MAX_MCP_RSS_MB (default 800, per-session; scaled by session count).
#
# Selftest: bash mcp-rss-cap.sh --selftest

set -uo pipefail

if [ "${PIPELINE_NO_RSS_CAP:-}" = "1" ]; then
  cat >/dev/null 2>&1 || true
  exit 0
fi

CAP_MB="${PIPELINE_MAX_MCP_RSS_MB:-800}"
case "$CAP_MB" in
  *[!0-9]*|"") CAP_MB=800 ;;
esac

DAEMON_PATTERNS=(
  "codegraph serve --mcp"
  "graphify.*--mcp"
  "agentmemory.*mcp"
  "serena start-mcp-server"
  "serena/language_servers"
)

# ─── Selftest mode ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS_COUNT=0
  FAIL_COUNT=0
  SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

  # Case 1: under-cap no-op on system with no MCP daemons.
  out=$(echo '{}' | bash "$SCRIPT" 2>&1)
  rc=$?
  if [ "$rc" = "0" ]; then
    echo "  [PASS] under-cap no-op exit 0"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] under-cap rc=$rc"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 2: opt-out via PIPELINE_NO_RSS_CAP=1.
  out=$(echo '{}' | PIPELINE_NO_RSS_CAP=1 bash "$SCRIPT" 2>&1)
  rc=$?
  if [ "$rc" = "0" ] && [ -z "$out" ]; then
    echo "  [PASS] opt-out via PIPELINE_NO_RSS_CAP=1"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] opt-out: rc=$rc out=$out"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 3: PR #117 lesson — script body does NOT spawn an LLM CLI subprocess.
  # The forbidden token is built at runtime to avoid this selftest matching itself.
  forbidden_re="\b$(printf 'claude\\s+-p')\b|anthropic|claude_code\.api"
  if ! grep -vE '^\s*#|forbidden_re|case 3|PR #117' "$SCRIPT" | grep -qE "$forbidden_re"; then
    echo "  [PASS] PR_117_no_llm_subprocess in executable code"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] PR #117: claude -p / LLM SDK reference found"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 4: hook MUST NOT contain `kill` invocations on user processes.
  # Only `pgrep` / `ps` allowed for discovery; warning emission is the only side-effect.
  if grep -qE '^\s*(kill\s+-[A-Z0-9]+|kill\s+\$)' "$SCRIPT"; then
    echo "  [FAIL] hook contains kill — RSS cap MUST NOT kill processes"
    FAIL_COUNT=$((FAIL_COUNT+1))
  else
    echo "  [PASS] no kill calls (RSS cap warns only)"
    PASS_COUNT=$((PASS_COUNT+1))
  fi

  # Case 5: synthesized over-cap mock (pinned to 1 session) emits PIPELINE_DISABLE_ guidance.
  out=$(echo '{}' | __pkit_mock_rss_total_mb=1200 __pkit_mock_session_count=1 bash "${SCRIPT}" 2>&1)
  if echo "${out}" | grep -q "PIPELINE_DISABLE_"; then
    echo "  [PASS] over-cap mock emits PIPELINE_DISABLE_ guidance"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] over-cap mock: no PIPELINE_DISABLE_ in output"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 6: multi-session scaling — 1200 MB across 3 sessions (effective cap 2400) → no warn.
  out=$(echo '{}' | __pkit_mock_rss_total_mb=1200 __pkit_mock_session_count=3 bash "${SCRIPT}" 2>&1)
  if echo "${out}" | grep -q "PIPELINE_DISABLE_"; then
    echo "  [FAIL] multi-session scaling warned under effective cap"
    FAIL_COUNT=$((FAIL_COUNT+1))
  else
    echo "  [PASS] multi-session scaling suppresses false alarm"
    PASS_COUNT=$((PASS_COUNT+1))
  fi

  echo "Results: $PASS_COUNT PASS / $FAIL_COUNT FAIL"
  [ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
fi

# ─── Hook mode ────────────────────────────────────────────────────────────────
cat >/dev/null 2>&1 || true

# Test-mode override: __pkit_mock_rss_total_mb forces the sum without touching ps.
if [ -n "${__pkit_mock_rss_total_mb:-}" ]; then
  TOTAL_MB="$__pkit_mock_rss_total_mb"
else
  TOTAL_KB=0
  for pattern in "${DAEMON_PATTERNS[@]}"; do
    while read -r pid; do
      [ -z "$pid" ] && continue
      rss=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
      [ -z "$rss" ] && continue
      case "$rss" in
        *[!0-9]*) continue ;;
      esac
      TOTAL_KB=$((TOTAL_KB + rss))
    done < <(pgrep -f "$pattern" 2>/dev/null)
  done
  TOTAL_MB=$((TOTAL_KB / 1024))
fi

# Each Claude session spawns its own MCP stack — scale the cap by live session
# count so N sessions don't false-alarm. __pkit_mock_session_count overrides for selftest.
if [ -n "${__pkit_mock_session_count:-}" ]; then
  SESSIONS="${__pkit_mock_session_count}"
else
  SESSIONS=$(pgrep -fc 'claude --' 2>/dev/null)
fi
case "${SESSIONS}" in *[!0-9]*|"") SESSIONS=1 ;; esac
[ "${SESSIONS}" -lt 1 ] && SESSIONS=1
EFFECTIVE_CAP=$((CAP_MB * SESSIONS))

if [ "${TOTAL_MB}" -gt "${EFFECTIVE_CAP}" ]; then
  NOTIFY_HOOK="$(dirname "$0")/notify-emit.sh"
  MSG="mcp-rss-cap: cumulative MCP RSS = ${TOTAL_MB} MB over ${SESSIONS} session(s) (cap=${EFFECTIVE_CAP} MB = ${CAP_MB}/session). Reduce: set PIPELINE_DISABLE_AGENTMEMORY=1 / PIPELINE_DISABLE_CODEGRAPH=1 / PIPELINE_DISABLE_GRAPHIFY=1, scope serena to a per-project .mcp.json, or close idle sessions."
  printf '%s\n' "$MSG" >&2
  if [ -x "$NOTIFY_HOOK" ]; then
    NOTIFY_EVENT_TYPE=error NOTIFY_TEXT="$MSG" \
      bash "$NOTIFY_HOOK" --mode beacon >/dev/null 2>&1 || true
  fi
fi

exit 0
