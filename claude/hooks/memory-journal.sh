#!/usr/bin/env bash
# memory-journal.sh — Stop hook
#
# Captures lightweight session metadata at every Stop event for the per-project
# memory journal. The journal is a JSONL append log; one line per session-end.
# A separate, USER-INVOKED slash command (`/digest-memories`) reads the journal
# and proposes memory additions to `~/.claude/projects/<slug>/memory/`.
#
# Why this is split:
#   The previous self-reflection hook (`stop-self-reflect.sh`, removed in #117)
#   spawned `claude -p` per turn for zero useful output (0/28 proposals were
#   non-empty). The subprocess spawn also caused recursive memory pressure
#   (12GB vmmemWSL lockup until #112 added the recursion guard).
#
#   This hook does NOT spawn any subprocess and does NOT call any LLM. It
#   appends one JSON line and exits. The expensive part (synthesizing
#   learnings from session transcripts) is deferred to `/digest-memories`,
#   which runs IN THE CURRENT SESSION'S CONTEXT (the LEAD does the work)
#   rather than spawning a separate `claude -p` invocation. Cost is
#   user-controlled by when they choose to invoke the digest.
#
# Schema (one JSON object per line):
#   {
#     "ts":              "<ISO8601 UTC>",
#     "session_id":      "<from envelope>",
#     "transcript_path": "<from envelope, when provided>",
#     "cwd":             "<from envelope, or pwd as fallback>",
#     "branch":          "<git branch when in a repo, else null>",
#     "stop_hook_active":<bool, from envelope>
#   }
#
# Storage:
#   ~/.claude/projects/<slug>/memory-journal.jsonl
#
# Rotation:
#   When the journal exceeds 5 MB, rotates to memory-journal.jsonl.1 (single
#   rotation slot; .1 is overwritten). Prevents unbounded growth.
#
# Env knobs:
#   PIPELINE_NO_MEMORY_JOURNAL=1  -> skip silently (kill switch)
#   PIPELINE_MEMORY_JOURNAL_MAX_BYTES=<int>  -> override rotation threshold
#
# Stop hooks are non-blocking by contract: any exit code is treated as 0 by
# the harness. This hook always exits 0 anyway.
#
# Self-test: bash memory-journal.sh --selftest

# denial_tracker:no — Stop hooks never block per spec; opt-out is contractual

set -uo pipefail

KILL_SWITCH="${PIPELINE_NO_MEMORY_JOURNAL:-0}"
MAX_BYTES="${PIPELINE_MEMORY_JOURNAL_MAX_BYTES:-5242880}"  # 5 MB
case "$MAX_BYTES" in
  *[!0-9]*|"") MAX_BYTES=5242880 ;;
esac

# ─── Self-test ────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS=0; FAIL=0; FAILED=()
  rec() {
    if [ "$2" = "PASS" ]; then echo "PASS: $1"; PASS=$((PASS+1))
    else echo "FAIL: $1 — ${3:-}"; FAIL=$((FAIL+1)); FAILED+=("$1"); fi
  }

  SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  TMPHOME=$(mktemp -d)
  trap 'rm -rf "$TMPHOME"' EXIT

  run_envelope() {
    # $1 = JSON envelope
    printf '%s' "$1" | HOME="$TMPHOME" bash "$SCRIPT" 2>/dev/null
  }

  # Test 1: basic append creates journal file
  ENV='{"session_id":"sess-1","transcript_path":"/tmp/t.jsonl","cwd":"/tmp/proj","stop_hook_active":false}'
  run_envelope "$ENV"
  # slug for /tmp/proj is -tmp-proj
  JOURNAL="$TMPHOME/.claude/projects/-tmp-proj/memory-journal.jsonl"
  if [ -f "$JOURNAL" ] && [ "$(wc -l < "$JOURNAL")" = "1" ]; then
    rec "basic_append_creates_journal" PASS
  else
    rec "basic_append_creates_journal" FAIL "journal not created or wrong line count"
  fi

  # Test 2: JSON validity of journal entry
  if [ -f "$JOURNAL" ] && python3 -c "import sys, json; [json.loads(l) for l in open('$JOURNAL')]" 2>/dev/null; then
    rec "journal_entries_are_valid_json" PASS
  else
    rec "journal_entries_are_valid_json" FAIL "invalid JSON in journal"
  fi

  # Test 3: required fields present
  if python3 -c "
import json
e = json.loads(open('$JOURNAL').readline())
required = {'ts', 'session_id', 'transcript_path', 'cwd', 'branch', 'stop_hook_active'}
missing = required - set(e.keys())
exit(1 if missing else 0)
" 2>/dev/null; then
    rec "journal_entry_has_required_fields" PASS
  else
    rec "journal_entry_has_required_fields" FAIL "missing required fields"
  fi

  # Test 4: append (not overwrite) on second call
  run_envelope '{"session_id":"sess-2","cwd":"/tmp/proj"}'
  if [ "$(wc -l < "$JOURNAL")" = "2" ]; then
    rec "second_call_appends" PASS
  else
    rec "second_call_appends" FAIL "expected 2 lines, got $(wc -l < "$JOURNAL")"
  fi

  # Test 5: kill switch produces no output and no file changes
  rm -f "$JOURNAL"
  printf '%s' "$ENV" | PIPELINE_NO_MEMORY_JOURNAL=1 HOME="$TMPHOME" bash "$SCRIPT" 2>/dev/null
  if [ ! -f "$JOURNAL" ]; then
    rec "kill_switch_silent" PASS
  else
    rec "kill_switch_silent" FAIL "journal created despite kill switch"
  fi

  # Test 6: rotation when size exceeds threshold
  mkdir -p "$(dirname "$JOURNAL")"
  # Pre-fill with > MAX_BYTES of data
  python3 -c "
import sys
with open('$JOURNAL', 'w') as f:
    for _ in range(11000):
        f.write('x' * 100 + chr(10))
"
  PRE_SIZE=$(stat -c%s "$JOURNAL" 2>/dev/null || stat -f%z "$JOURNAL")
  PIPELINE_MEMORY_JOURNAL_MAX_BYTES=1048576 run_envelope "$ENV"  # 1 MB threshold
  if [ -f "$JOURNAL.1" ]; then
    NEW_SIZE=$(stat -c%s "$JOURNAL" 2>/dev/null || stat -f%z "$JOURNAL")
    if [ "$NEW_SIZE" -lt "$PRE_SIZE" ]; then
      rec "rotation_at_threshold" PASS
    else
      rec "rotation_at_threshold" FAIL "rotated but main file not truncated"
    fi
  else
    rec "rotation_at_threshold" FAIL "expected .1 rotation file"
  fi

  # Test 7: empty stdin / non-JSON envelope is tolerated (exit 0)
  EXIT=0
  printf 'not-json' | HOME="$TMPHOME" bash "$SCRIPT" >/dev/null 2>&1 || EXIT=$?
  if [ "$EXIT" = "0" ]; then
    rec "non_json_envelope_tolerated" PASS
  else
    rec "non_json_envelope_tolerated" FAIL "exit=$EXIT"
  fi

  # Test 8: cwd fallback to PWD when envelope omits cwd
  rm -f "$JOURNAL"
  rm -rf "$TMPHOME/.claude/projects/-tmp-proj"
  printf '%s' '{"session_id":"sess-3"}' | (cd /tmp && HOME="$TMPHOME" bash "$SCRIPT") >/dev/null 2>&1
  FALLBACK_JOURNAL="$TMPHOME/.claude/projects/-tmp/memory-journal.jsonl"
  if [ -f "$FALLBACK_JOURNAL" ]; then
    rec "cwd_fallback_to_pwd" PASS
  else
    rec "cwd_fallback_to_pwd" FAIL "fallback journal not created at $FALLBACK_JOURNAL"
  fi

  # Test 9: memory_save payload appears on stdout alongside JSONL append
  rm -f "$JOURNAL"
  rm -rf "$TMPHOME/.claude/projects/-tmp-proj"
  ENV9='{"session_id":"sess-9","transcript_path":"/tmp/t.jsonl","cwd":"/tmp/proj","stop_hook_active":false}'
  OUT9=$(printf '%s' "$ENV9" | HOME="$TMPHOME" bash "$SCRIPT" 2>/dev/null)
  if printf '%s' "$OUT9" | python3 -c "
import sys, json
line = sys.stdin.read().strip()
if not line:
    sys.exit(1)
obj = json.loads(line)
if obj.get('_payload_kind') != 'memory_save':
    sys.exit(1)
required = {'tags', 'category', 'content', 'ts'}
if not required.issubset(obj.keys()):
    sys.exit(1)
" 2>/dev/null; then
    rec "memory_save_emission_on_stdout" PASS
  else
    rec "memory_save_emission_on_stdout" FAIL "expected memory_save payload on stdout"
  fi

  echo "Results: $PASS PASS / $FAIL FAIL"
  [ "$FAIL" -ne 0 ] && { echo "Failed: ${FAILED[*]}"; exit 1; }
  exit 0
fi

# ─── Kill switch ──────────────────────────────────────────────────────────────
if [ "$KILL_SWITCH" = "1" ]; then
  exit 0
fi

# ─── Read envelope ────────────────────────────────────────────────────────────
INPUT=$(cat 2>/dev/null || true)

# Extract fields via python3 (jq not installed). Tolerate non-JSON / missing
# fields — Stop hooks must never block.
PARSED=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin) if sys.stdin.isatty() == False else {}
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
sid  = d.get('session_id', '') or ''
tp   = d.get('transcript_path', '') or ''
cwd  = d.get('cwd', '') or ''
sha  = d.get('stop_hook_active', False)
# Tab-separated for safe shell parsing
print('\t'.join([sid, tp, cwd, 'true' if sha else 'false']))
" 2>/dev/null || printf '\t\t\tfalse')

SESSION_ID=$(printf '%s' "$PARSED" | cut -f1)
TRANSCRIPT=$(printf '%s' "$PARSED" | cut -f2)
CWD=$(printf '%s' "$PARSED" | cut -f3)
STOP_ACTIVE=$(printf '%s' "$PARSED" | cut -f4)

# Fallback for cwd
[ -z "$CWD" ] && CWD="$PWD"

# Derive slug — same convention as ~/.claude/projects/-home-bruce-pipelinekit/
SLUG=$(printf '%s' "$CWD" | sed 's|/|-|g')

# Resolve branch if in a git repo
BRANCH=""
if BRANCH_RAW=$(cd "$CWD" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null); then
  BRANCH="$BRANCH_RAW"
fi

# Timestamp — ISO8601 UTC
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Compose JSON line via python3 — pass fields via env to avoid shell quoting bugs
LINE=$(JE_TS="$TS" JE_SID="$SESSION_ID" JE_TP="$TRANSCRIPT" JE_CWD="$CWD" \
       JE_BR="$BRANCH" JE_SHA="$STOP_ACTIVE" python3 -c "
import json, os, sys
entry = {
    'ts': os.environ.get('JE_TS', ''),
    'session_id': os.environ.get('JE_SID', ''),
    'transcript_path': os.environ.get('JE_TP', ''),
    'cwd': os.environ.get('JE_CWD', ''),
    'branch': os.environ.get('JE_BR', '') or None,
    'stop_hook_active': os.environ.get('JE_SHA', 'false') == 'true',
}
sys.stdout.write(json.dumps(entry))
" 2>/dev/null) || exit 0

[ -z "$LINE" ] && exit 0

# Write to journal
JOURNAL_DIR="$HOME/.claude/projects/$SLUG"
JOURNAL="$JOURNAL_DIR/memory-journal.jsonl"
mkdir -p "$JOURNAL_DIR" 2>/dev/null || exit 0

# ─── Rotation check (before append) ───────────────────────────────────────────
if [ -f "$JOURNAL" ]; then
  CUR_SIZE=$(stat -c%s "$JOURNAL" 2>/dev/null || stat -f%z "$JOURNAL" 2>/dev/null || echo 0)
  if [ "$CUR_SIZE" -gt "$MAX_BYTES" ]; then
    mv -f "$JOURNAL" "$JOURNAL.1" 2>/dev/null || true
  fi
fi

# Append
printf '%s\n' "$LINE" >> "$JOURNAL" 2>/dev/null || true

# ─── Emit memory_save payload on stdout (additive, fire-and-forget) ───────────
# Routing marker: `_payload_kind: memory_save`. A harness that learns to route
# MCP RPCs from stdout can grep for this key; absent such routing, the payload
# emerges as harmless output noise on the next Claude Code output stream.
# Construction mirrors the existing JE_* env-var pattern (no subprocess spawn
# beyond the existing python3 child).
PAYLOAD=$(JE_TS="$TS" JE_SID="$SESSION_ID" JE_CWD="$CWD" JE_BR="$BRANCH" \
          JE_SLUG="$SLUG" python3 -c "
import json, os, sys
payload = {
    '_payload_kind': 'memory_save',
    'tags': ['journal', 'session-end', os.environ.get('JE_SLUG', '').lstrip('-') or 'unknown-slug'],
    'category': 'reference',
    'content': 'session-end journal entry; metadata-only',
    'session_id': os.environ.get('JE_SID', ''),
    'cwd': os.environ.get('JE_CWD', ''),
    'branch': os.environ.get('JE_BR', '') or None,
    'ts': os.environ.get('JE_TS', ''),
}
sys.stdout.write(json.dumps(payload))
" 2>/dev/null) || PAYLOAD=""

[ -n "$PAYLOAD" ] && printf '%s\n' "$PAYLOAD"

exit 0
