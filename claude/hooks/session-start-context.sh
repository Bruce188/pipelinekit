#!/bin/bash
# Loads git context (branch, status, recent commits, unstaged diff summary)
# into the session at startup. Wired via SessionStart hook in scripts/install.sh.
# Charter MVP item 3.
#
# Contract:
#   - Reads JSON envelope from stdin (consumed and discarded).
#   - Writes a Markdown context block to stdout.
#   - Output capped at 8 KB.
#   - Exits 0 unconditionally (SessionStart hooks must never block).
#   - Honours PIPELINE_NO_SESSION_START_CONTEXT=1 as opt-out (empty stdout).
#   - Honours PIPELINE_SESSION_START_DIFF_LINES (default 200) for diff-stat cap.
#
# Selftest: bash session-start-context.sh --selftest

set -uo pipefail

DIFF_LINES_CAP="${PIPELINE_SESSION_START_DIFF_LINES:-200}"
case "$DIFF_LINES_CAP" in
    *[!0-9]*|"") DIFF_LINES_CAP=200 ;;
esac
STATUS_LINES_CAP=30
OUTPUT_BYTE_CAP=8192
TRUNCATE_TARGET=7900

# ─── Selftest mode ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS_COUNT=0
  FAIL_COUNT=0
  SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

  pass() { echo "PASS  case $1: $2"; PASS_COUNT=$((PASS_COUNT + 1)); }
  fail() { echo "FAIL  case $1: $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

  # Case 1: not a git repo — exit 0, "(not a git repo)" in output.
  _tmp1=$(mktemp -d)
  _out1=$(cd "$_tmp1" && bash "$SCRIPT" </dev/null 2>&1)
  _exit1=$?
  if [ "$_exit1" = "0" ] && echo "$_out1" | grep -q '(not a git repo)'; then
    pass 1 "not a git repo -> exit 0 + advisory"
  else
    fail 1 "not a git repo (exit=$_exit1, output=$_out1)"
  fi
  rm -rf "$_tmp1"

  # Case 2: opt-out env-var — exit 0, empty stdout.
  _out2=$(PIPELINE_NO_SESSION_START_CONTEXT=1 bash "$SCRIPT" </dev/null 2>/dev/null)
  _exit2=$?
  if [ "$_exit2" = "0" ] && [ -z "$_out2" ]; then
    pass 2 "opt-out env-var -> exit 0 + empty stdout"
  else
    fail 2 "opt-out env-var (exit=$_exit2, output=$_out2)"
  fi

  # Case 3: tiny temp git repo — all 4 H2 sections present.
  _tmp3=$(mktemp -d)
  (
    cd "$_tmp3"
    git init -q -b main
    git config user.email "test@example.com"
    git config user.name "Test"
    echo "hello" > a.txt
    git add a.txt
    git commit -q -m "chore: initial commit"
    echo "world" >> a.txt
  )
  _out3=$(cd "$_tmp3" && bash "$SCRIPT" </dev/null 2>/dev/null)
  _exit3=$?
  _missing=""
  for hdr in '## Branch' '## Working Tree' '## Recent Commits' '## Unstaged Diff Summary'; do
    echo "$_out3" | grep -qF "$hdr" || _missing="$_missing $hdr"
  done
  if [ "$_exit3" = "0" ] && [ -z "$_missing" ]; then
    pass 3 "tiny git repo -> all 4 H2 sections present"
  else
    fail 3 "tiny git repo (exit=$_exit3, missing:$_missing)"
  fi
  rm -rf "$_tmp3"

  # Case 4: repo with > 1000 unstaged-diff lines — output ≤ 8192 bytes.
  _tmp4=$(mktemp -d)
  (
    cd "$_tmp4"
    git init -q -b main
    git config user.email "test@example.com"
    git config user.name "Test"
    for i in $(seq 1 50); do
      printf 'line %d\n' "$i" > "file_$i.txt"
    done
    git add .
    git commit -q -m "chore: seed"
    for i in $(seq 1 50); do
      for j in $(seq 1 30); do
        printf 'extra line %d-%d\n' "$i" "$j" >> "file_$i.txt"
      done
    done
  )
  _out4=$(cd "$_tmp4" && bash "$SCRIPT" </dev/null 2>/dev/null)
  _exit4=$?
  _bytes=$(printf '%s' "$_out4" | wc -c)
  if [ "$_exit4" = "0" ] && [ "$_bytes" -le 8192 ]; then
    pass 4 "large diff -> output ${_bytes} bytes <= 8192"
  else
    fail 4 "large diff (exit=$_exit4, bytes=$_bytes)"
  fi
  rm -rf "$_tmp4"

  echo ""
  echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
  [ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
fi

# ─── Normal hook mode ─────────────────────────────────────────────────────────

# Consume stdin (hook protocol).
cat > /dev/null

# Opt-out check.
if [ "${PIPELINE_NO_SESSION_START_CONTEXT:-0}" = "1" ]; then
  exit 0
fi

# Clear the subagent-nudge marker so the first prompt of a fresh session
# re-emits the default-mode banner. See claude/hooks/subagent-first-nudge.sh
# for the once-per-session cap mechanism.
rm -f "$HOME/.claude/.subagent-nudge-fired" 2>/dev/null || true

# Not a git repo — print advisory and exit 0.
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  printf '# Session Context\n\n(not a git repo)\n'
  exit 0
fi

# ─── Gather context ───────────────────────────────────────────────────────────

# Branch (handle detached HEAD + empty-repo edge — git rev-parse can emit "HEAD" on stdout while exiting non-zero).
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -z "$CURRENT_BRANCH" ] || [ "$CURRENT_BRANCH" = "HEAD" ]; then
    CURRENT_BRANCH="(detached)"
fi

# Base branch (canonical snippet from ~/.claude/rules/workflow.md § Base Branch Detection).
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
[ -z "$BASE" ] && BASE=$(git branch -l main master 2>/dev/null | head -1 | awk '{print $NF}')
[ -z "$BASE" ] && BASE="main"

# git status --short, first STATUS_LINES_CAP lines.
STATUS_RAW=$(git status --short 2>/dev/null || echo "")
STATUS_TOTAL_LINES=$(printf '%s\n' "$STATUS_RAW" | grep -c '' 2>/dev/null || echo 0)
# Empty status: grep -c may report 1 for empty string; normalize.
if [ -z "$STATUS_RAW" ]; then
  STATUS_TOTAL_LINES=0
fi
STATUS_BLOCK=$(printf '%s\n' "$STATUS_RAW" | head -n "$STATUS_LINES_CAP")
if [ "$STATUS_TOTAL_LINES" -gt "$STATUS_LINES_CAP" ]; then
  STATUS_EXTRA=$((STATUS_TOTAL_LINES - STATUS_LINES_CAP))
  STATUS_BLOCK=$(printf '%s\n... (%d more lines)' "$STATUS_BLOCK" "$STATUS_EXTRA")
fi
if [ -z "$STATUS_RAW" ]; then
  STATUS_BLOCK="(working tree clean)"
fi

# Recent commits (graceful on empty repo).
COMMITS_RAW=$(git log -5 --oneline 2>/dev/null || echo "")
if [ -z "$COMMITS_RAW" ]; then
  COMMITS_BLOCK="(no commits)"
else
  COMMITS_BLOCK="$COMMITS_RAW"
fi

# Unstaged diff summary. Prefer `git diff --stat HEAD` when HEAD exists; fall back to `git diff --stat`.
if git rev-parse --verify HEAD >/dev/null 2>&1; then
  DIFF_RAW=$(git diff --stat HEAD 2>/dev/null || echo "")
else
  DIFF_RAW=$(git diff --stat 2>/dev/null || echo "")
fi
DIFF_TOTAL_LINES=$(printf '%s\n' "$DIFF_RAW" | grep -c '' 2>/dev/null || echo 0)
if [ -z "$DIFF_RAW" ]; then
  DIFF_TOTAL_LINES=0
fi
DIFF_BLOCK=$(printf '%s\n' "$DIFF_RAW" | head -n "$DIFF_LINES_CAP")
if [ "$DIFF_TOTAL_LINES" -gt "$DIFF_LINES_CAP" ]; then
  DIFF_EXTRA=$((DIFF_TOTAL_LINES - DIFF_LINES_CAP))
  DIFF_BLOCK=$(printf '%s\n... (%d more lines)' "$DIFF_BLOCK" "$DIFF_EXTRA")
fi
if [ -z "$DIFF_RAW" ]; then
  DIFF_BLOCK="(no unstaged changes)"
fi

# ─── Build output ─────────────────────────────────────────────────────────────
OUT=$(cat <<EOF
# Session Context

## Branch
Branch: $CURRENT_BRANCH
Base: $BASE

## Working Tree
\`\`\`
$STATUS_BLOCK
\`\`\`

## Recent Commits
\`\`\`
$COMMITS_BLOCK
\`\`\`

## Unstaged Diff Summary
\`\`\`
$DIFF_BLOCK
\`\`\`
EOF
)

# Optional 5th section: Caveman state — only when the marker file exists.
if [ -f "$HOME/.claude/.caveman-active" ]; then
  CAVEMAN_LEVEL=$(head -n1 "$HOME/.claude/.caveman-active" 2>/dev/null || echo "")
  [ -z "$CAVEMAN_LEVEL" ] && CAVEMAN_LEVEL="wenyan-ultra"
  CAVEMAN_BLOCK=$(cat <<EOF

## Caveman state

Active level: \`$CAVEMAN_LEVEL\`. The three-zone content split below applies BOTH to your own narrative prose AND to every subagent dispatch — not subagents only.

- Zone 1 (code / paths / commits / errors): normal English, exact strings.
- Zone 2 (narrative prose): real classical Chinese 文言, Han characters mandatory.
- Zone 3 (fragments / status / beacons): ultra English, drop articles + filler.

The zone labels \`Zone 1\`/\`Zone 2\`/\`Zone 3\` are internal scaffolding — NEVER write them as headers, prefixes, or section titles in your reply. Blend the three content kinds inline so the reader never sees the literal word "Zone".

Snippet contract: \`~/.claude/snippets/caveman-subagent.md\` (repo: \`claude/snippets/caveman-subagent.md\`).

### Subagent dispatch protocol (MANDATORY while caveman is active)

The harness does NOT auto-inject the contract. When you call the \`Agent\` tool you MUST prepend this block to the \`prompt\` parameter, then put your task instructions below it:

\`\`\`
<caveman-inherited level="$CAVEMAN_LEVEL">
(full contents of ~/.claude/snippets/caveman-subagent.md)
</caveman-inherited>

---

(your original task prompt)
\`\`\`

A PreToolUse gate (\`agent-caveman-gate.sh\`) enforces this — Agent calls missing the contract get blocked with \`exit 2\` and the dispatching agent retries with the header prepended. The rule applies recursively: subagents that dispatch further subagents prepend the contract too.
EOF
  )
  OUT="$OUT$CAVEMAN_BLOCK"
fi

# ─── Enforce 8 KB cap ─────────────────────────────────────────────────────────
OUT_BYTES=$(printf '%s' "$OUT" | wc -c)
if [ "$OUT_BYTES" -gt "$OUTPUT_BYTE_CAP" ]; then
  OUT="${OUT:0:$TRUNCATE_TARGET}"
  OUT="$OUT
... (output truncated — exceeded 8 KB cap)"
fi

printf '%s\n' "$OUT"
exit 0
