#!/bin/bash
# Stop hook: runs headless `claude -p` to propose CLAUDE.md amendments based on the
# work done in this session, and writes the JSON proposal to a versioned artifact
# at docs/claude-md-proposal-v<N>.md.
#
# Contract:
#   - Stop hooks are NON-BLOCKING by harness contract. This script ALWAYS exits 0,
#     even on every failure path (missing CLI, timeout, write failure).
#   - The proposal is NEVER auto-applied. The artifact is for human review only.
#   - Headless `claude -p` invocations are time-bounded (60 s); a longer run is
#     killed silently and the hook exits 0 with no artifact.
#   - Opt out per-session via PIPELINE_NO_SELF_REFLECT=1.
#   - Override the binary via CLAUDE_BIN (used by tests + power users).
#   - Output path is RELATIVE to the working directory (per Stop-hook stdin envelope
#     contract, the harness invokes the hook with cwd = session cwd). The artifact
#     lands under docs/, which is workflow-only and gitignored. Consecutive runs
#     increment the version per the Versioning Convention.
#
# Charter MVP item 4.
#
# Selftest: bash stop-self-reflect.sh --selftest

# -e omitted on purpose: every failure path swallows exit code to honor the Stop-hook non-blocking contract.
set -uo pipefail

TIMEOUT_SECS=60
REFLECTION_PROMPT_HEREDOC=$(cat <<'PROMPT'
You are auditing the work done in this Claude Code session against the project's
CLAUDE.md files (root and any sibling subdir CLAUDE.md files such as
claude/skills/CLAUDE.md, claude/agents/CLAUDE.md, claude/hooks/CLAUDE.md).

Based on the work done in this session, propose 0-3 lean amendments to CLAUDE.md
files (root or subdir) that would have helped Claude do this work better. Be
specific: each proposal should target a single file at a single line anchor and
add or revise a short, actionable rule (one or two sentences). Skip cosmetic
edits; skip rules already present.

Return ONLY a single JSON object on stdout in this exact shape:

{"proposals": [{"file": "<path from repo root>", "line_anchor": "<heading or quoted line>", "proposed_text": "<replacement or insertion text>", "reason": "<why this would have helped>"}]}

If no useful amendment is warranted, return {"proposals": []}.

Constraints:
- No prose outside the JSON object.
- Use neutral phrasing; do not reference the AI or this session in proposed_text.
- proposed_text must be valid as-is when pasted into the target file.
PROMPT
)

# ─── Selftest mode ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS_COUNT=0
  FAIL_COUNT=0
  SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

  pass() { echo "PASS  case $1: $2"; PASS_COUNT=$((PASS_COUNT + 1)); }
  fail() { echo "FAIL  case $1: $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

  # Case 1: opt-out env-var -> exit 0, no artifact.
  _tmp1=$(mktemp -d)
  mkdir -p "$_tmp1/docs"
  _exit1=0
  (cd "$_tmp1" && PIPELINE_NO_SELF_REFLECT=1 bash "$SCRIPT" </dev/null >/dev/null 2>&1) || _exit1=$?
  _arts1=$(ls "$_tmp1/docs"/claude-md-proposal-v*.md 2>/dev/null | wc -l)
  if [ "$_exit1" = "0" ] && [ "$_arts1" = "0" ]; then
    pass 1 "opt-out env-var -> exit 0 + no artifact"
  else
    fail 1 "opt-out (exit=$_exit1, arts=$_arts1)"
  fi
  rm -rf "$_tmp1"

  # Case 2: missing claude CLI -> exit 0, no artifact.
  _tmp2=$(mktemp -d)
  mkdir -p "$_tmp2/docs"
  _exit2=0
  (cd "$_tmp2" && CLAUDE_BIN="/nonexistent/claude-binary" PATH="/usr/bin:/bin" \
    bash "$SCRIPT" </dev/null >/dev/null 2>&1) || _exit2=$?
  _arts2=$(ls "$_tmp2/docs"/claude-md-proposal-v*.md 2>/dev/null | wc -l)
  if [ "$_exit2" = "0" ] && [ "$_arts2" = "0" ]; then
    pass 2 "missing CLI -> exit 0 + no artifact"
  else
    fail 2 "missing CLI (exit=$_exit2, arts=$_arts2)"
  fi
  rm -rf "$_tmp2"

  # Case 3: happy path — stub claude -> artifact v1 written with JSON embedded.
  _tmp3=$(mktemp -d)
  mkdir -p "$_tmp3/docs" "$_tmp3/bin"
  cat >"$_tmp3/bin/claude" <<'MOCK'
#!/usr/bin/env bash
cat <<'JSON'
{"proposals":[]}
JSON
MOCK
  chmod +x "$_tmp3/bin/claude"
  _exit3=0
  (cd "$_tmp3" && CLAUDE_BIN="$_tmp3/bin/claude" bash "$SCRIPT" </dev/null >/dev/null 2>&1) || _exit3=$?
  _art3="$_tmp3/docs/claude-md-proposal-v1.md"
  if [ "$_exit3" = "0" ] && [ -f "$_art3" ] && grep -q '"proposals"' "$_art3"; then
    pass 3 "happy path -> v1 artifact written"
  else
    fail 3 "happy path (exit=$_exit3, art=$_art3)"
  fi
  rm -rf "$_tmp3"

  echo ""
  echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
  [ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
fi

# ─── Normal hook mode ─────────────────────────────────────────────────────────

# Consume stdin (hook protocol — JSON envelope discarded; v1 doesn't summarise).
cat > /dev/null

# Opt-out short-circuit (must precede every side-effect).
if [ "${PIPELINE_NO_SELF_REFLECT:-0}" = "1" ]; then
  exit 0
fi

# Resolve the claude binary. Honour explicit CLAUDE_BIN; fall back to PATH lookup.
CLAUDE_BIN_RESOLVED="${CLAUDE_BIN:-}"
if [ -z "$CLAUDE_BIN_RESOLVED" ]; then
  CLAUDE_BIN_RESOLVED=$(command -v claude 2>/dev/null || true)
fi
if [ -z "$CLAUDE_BIN_RESOLVED" ] || [ ! -x "$CLAUDE_BIN_RESOLVED" ]; then
  echo "info: claude CLI not found (set CLAUDE_BIN or install claude); self-reflection skipped" >&2
  exit 0
fi

# Compute next version per the Versioning Convention.
# Find the highest existing v<N> in docs/, default N=0 if none.
HIGHEST=0
if [ -d docs ]; then
  HIGHEST=$(ls docs/claude-md-proposal-v*.md 2>/dev/null \
    | sed -E 's|.*-v([0-9]+)\.md$|\1|' \
    | grep -E '^[0-9]+$' \
    | sort -n \
    | tail -1)
  if [ -z "$HIGHEST" ]; then
    HIGHEST=0
  fi
fi
NEXT_N=$((HIGHEST + 1))
TARGET_PATH="docs/claude-md-proposal-v${NEXT_N}.md"

# Ensure docs/ exists for the write (mkdir -p never fails for an existing dir).
mkdir -p docs 2>/dev/null || {
  echo "info: cannot create docs/ directory; self-reflection skipped" >&2
  exit 0
}

SESSION_SUMMARY="Self-reflection check at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
TMP_OUT=$(mktemp 2>/dev/null) || { exit 0; }
TMP_ERR=$(mktemp 2>/dev/null) || { rm -f "$TMP_OUT"; exit 0; }
cleanup_tmps() {
  rm -f "$TMP_OUT" "$TMP_ERR" 2>/dev/null || true
}
trap cleanup_tmps EXIT

# Run claude -p with a hard timeout. `timeout` kills the child on overflow and
# returns 124. We swallow every non-zero exit (the hook is non-blocking).
CLAUDE_EXIT=0
timeout "${TIMEOUT_SECS}" "$CLAUDE_BIN_RESOLVED" -p \
  --append-system-prompt "$REFLECTION_PROMPT_HEREDOC" \
  "$SESSION_SUMMARY" >"$TMP_OUT" 2>"$TMP_ERR" || CLAUDE_EXIT=$?

if [ "$CLAUDE_EXIT" = "124" ]; then
  echo "info: claude -p self-reflection timed out after ${TIMEOUT_SECS}s; no artifact written" >&2
  exit 0
fi
if [ "$CLAUDE_EXIT" != "0" ]; then
  echo "info: claude -p self-reflection exited ${CLAUDE_EXIT}; no artifact written" >&2
  exit 0
fi

# Skip empty output.
if [ ! -s "$TMP_OUT" ]; then
  echo "info: claude -p self-reflection returned empty output; no artifact written" >&2
  exit 0
fi

CLAUDE_OUTPUT=$(cat "$TMP_OUT")
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Write the proposal artifact. Failure is non-fatal — the hook still exits 0.
{
  printf '# CLAUDE.md Proposal — v%s\n\n' "$NEXT_N"
  printf 'Generated at %s\n\n' "$TIMESTAMP"
  printf '## Raw JSON Output\n\n'
  printf '```json\n'
  printf '%s\n' "$CLAUDE_OUTPUT"
  printf '```\n\n'
  printf '## Manual Apply\n\n'
  printf 'Apply these proposals manually — they are NOT auto-applied. See\n'
  printf '`documentation/stop-self-reflect-hook.html` for guidance.\n'
} >"$TARGET_PATH" 2>/dev/null || {
  echo "info: could not write self-reflection artifact to $TARGET_PATH" >&2
  exit 0
}

exit 0
