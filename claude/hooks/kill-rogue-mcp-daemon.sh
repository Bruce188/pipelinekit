#!/bin/bash
# SessionStart hook: reap orphan MCP daemons left behind by previous sessions.
#
# Motivation: PR #117 (vmmemWSL 12 GB lockup from runaway subprocess) + the
# codegraph v0.8.0 orphan-daemon bug. Long-running MCP daemons whose parent
# Claude Code process died (PPID=1) and that have been running > 60 minutes are
# treated as orphans and reaped.
#
# Contract:
#   - Reads JSON envelope from stdin (consumed and discarded).
#   - Pure bash + ps/pgrep/kill — NO claude -p, NO LLM subprocess (PR #117 lesson).
#   - Idempotent — no-op if no orphans match.
#   - Exits 0 unconditionally (SessionStart hooks must never block).
#   - Honours PIPELINE_NO_ROGUE_REAPER=1 as opt-out (no work, exit 0).
#   - Honours PIPELINE_ROGUE_DAEMON_AGE_SEC (default 3600) for orphan age threshold.
#
# Heuristic:
#   1. Discover daemons by pattern: codegraph serve --mcp, graphify.*--mcp,
#      agentmemory.*mcp.
#   2. For each PID, check PPID = 1 (init / WSL2-systemd).
#   3. Check elapsed running time >= PIPELINE_ROGUE_DAEMON_AGE_SEC.
#   4. If both: kill -TERM, sleep 5, kill -KILL if still alive.
#   5. Emit a summary line via notify-emit.sh JSON dispatch if any reaped.
#
# Selftest: bash kill-rogue-mcp-daemon.sh --selftest

set -uo pipefail

# Opt-out short-circuit.
if [ "${PIPELINE_NO_ROGUE_REAPER:-}" = "1" ]; then
  cat >/dev/null 2>&1 || true
  exit 0
fi

ORPHAN_AGE_SEC="${PIPELINE_ROGUE_DAEMON_AGE_SEC:-3600}"
case "$ORPHAN_AGE_SEC" in
  *[!0-9]*|"") ORPHAN_AGE_SEC=3600 ;;
esac

# Daemon-pattern table — extend here when new MCP daemons join the default stack.
DAEMON_PATTERNS=(
  "codegraph serve --mcp"
  "graphify.*--mcp"
  "agentmemory.*mcp"
)

# ─── Selftest mode ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS_COUNT=0
  FAIL_COUNT=0
  SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

  # Case 1: no-op on system with no MCP daemons (exit 0, no output noise).
  out=$(echo '{}' | bash "$SCRIPT" 2>&1)
  rc=$?
  if [ "$rc" = "0" ]; then
    echo "  [PASS] no-op exit 0 (no daemons present)"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] no-op exit code: $rc"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 2: PIPELINE_NO_ROGUE_REAPER=1 → opt-out (exit 0, no work).
  out=$(echo '{}' | PIPELINE_NO_ROGUE_REAPER=1 bash "$SCRIPT" 2>&1)
  rc=$?
  if [ "$rc" = "0" ] && [ -z "$out" ]; then
    echo "  [PASS] opt-out via PIPELINE_NO_ROGUE_REAPER=1"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] opt-out: rc=$rc, out=$out"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 3: PR #117 lesson — script body does NOT spawn an LLM CLI subprocess.
  # The forbidden token is built at runtime to avoid this selftest matching itself.
  forbidden_re="\b$(printf 'claude\\s+-p')\b|anthropic|claude_code\.api"
  if ! grep -vE '^\s*#|forbidden_re|case 3|PR #117' "$SCRIPT" | grep -qE "$forbidden_re"; then
    echo "  [PASS] PR_117_no_llm_subprocess in executable code"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] PR #117: claude -p or LLM SDK reference found"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi

  # Case 4: synthesize a sleep process matching a daemon pattern, but with PPID != 1
  # (parent = this shell) and a young age — should NOT be reaped.
  ( exec -a "codegraph serve --mcp" sleep 30 ) &
  fake_pid=$!
  sleep 0.5
  echo '{}' | bash "$SCRIPT" >/dev/null 2>&1
  # Check fake_pid still alive.
  if kill -0 "$fake_pid" 2>/dev/null; then
    echo "  [PASS] young daemon with non-init parent NOT reaped"
    PASS_COUNT=$((PASS_COUNT+1))
  else
    echo "  [FAIL] young daemon was killed (should be no-op)"
    FAIL_COUNT=$((FAIL_COUNT+1))
  fi
  kill "$fake_pid" 2>/dev/null
  wait "$fake_pid" 2>/dev/null

  echo "Results: $PASS_COUNT PASS / $FAIL_COUNT FAIL"
  [ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
fi

# ─── Hook mode ────────────────────────────────────────────────────────────────
# Consume stdin (Claude Code passes a JSON envelope we don't need).
cat >/dev/null 2>&1 || true

REAPED_COUNT=0
REAPED_LINES=""

for pattern in "${DAEMON_PATTERNS[@]}"; do
  # pgrep -f matches against full command line; -a returns "pid cmd".
  while read -r pid cmd; do
    [ -z "$pid" ] && continue

    # Check PPID — orphan = PPID 1 (init / WSL2-systemd reparent).
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
    [ "$ppid" != "1" ] && continue

    # Check elapsed time. ps etime format is [[dd-]hh:]mm:ss or mm:ss.
    etime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    [ -z "$etime" ] && continue

    # Convert etime to seconds via python3 (stdlib only).
    age=$(python3 -c "
import sys, re
s = sys.argv[1]
m = re.match(r'(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$', s)
if not m:
    print(0); sys.exit(0)
d, h, mi, se = m.groups(default='0')
total = int(d)*86400 + int(h)*3600 + int(mi)*60 + int(se)
print(total)
" "$etime" 2>/dev/null || echo 0)

    [ "$age" -lt "$ORPHAN_AGE_SEC" ] && continue

    # Reap.
    if kill -TERM "$pid" 2>/dev/null; then
      # Grace period.
      grace=0
      while [ "$grace" -lt 5 ]; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
        grace=$((grace+1))
      done
      # Force kill if still alive.
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null

      REAPED_COUNT=$((REAPED_COUNT+1))
      REAPED_LINES="$REAPED_LINES${REAPED_LINES:+\\n}reaped pid=$pid pattern=$pattern age=${age}s"
    fi
  done < <(pgrep -af "$pattern" 2>/dev/null)
done

# Emit summary via notify-emit.sh if anything reaped (best-effort; never blocks).
if [ "$REAPED_COUNT" -gt 0 ]; then
  NOTIFY_HOOK="$(dirname "$0")/notify-emit.sh"
  if [ -x "$NOTIFY_HOOK" ]; then
    NOTIFY_EVENT_TYPE=error \
    NOTIFY_TEXT="kill-rogue-mcp-daemon reaped $REAPED_COUNT orphan(s): $(printf '%b' "$REAPED_LINES" | tr '\n' ';' | cut -c1-180)" \
      bash "$NOTIFY_HOOK" --mode beacon >/dev/null 2>&1 || true
  fi
fi

exit 0
