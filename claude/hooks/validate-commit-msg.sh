#!/bin/bash
# Validates commit messages against conventional-commit + AI-token-ban rules.
# Called by PreToolUse hook -- receives tool input on stdin.
# Also called as: bash validate-commit-msg.sh --selftest

set -euo pipefail

# ─── Selftest mode ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  PASS_COUNT=0
  FAIL_COUNT=0
  SCRIPT="$0"

  run_case() {
    local case_num="$1"
    local expected_exit="$2"
    local cmd="$3"
    local env_override="${4:-}"
    local description="$5"

    local payload
    payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$cmd")

    local actual_exit=0
    local stderr_out=""
    if [ -n "$env_override" ]; then
      local env_val="${env_override#*=}"
      # B3: selftest path must opt in via VALIDATE_COMMIT_MSG_SELFTEST=1 for override to take effect.
      stderr_out=$(VALIDATE_COMMIT_MSG_SELFTEST=1 VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE="$env_val" bash "$SCRIPT" <<< "$payload" 2>&1) || actual_exit=$?
    else
      stderr_out=$(bash "$SCRIPT" <<< "$payload" 2>&1) || actual_exit=$?
    fi

    if [ "$actual_exit" = "$expected_exit" ]; then
      echo "PASS  case $case_num: $description"
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      echo "FAIL  case $case_num: $description"
      echo "      expected exit=$expected_exit, got exit=$actual_exit"
      [ -n "$stderr_out" ] && echo "      stderr: $stderr_out"
      FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
  }

  # Case 1: valid type + valid subject -> allow
  run_case 1 0 \
    'git commit -m "chore: bump deps"' \
    "" \
    "valid type + subject -> exit 0"

  # Case 2: invalid type "feature:" -> reject, cite invalid type
  run_case 2 1 \
    'git commit -m "feature: bump deps"' \
    "" \
    "invalid type 'feature' -> exit 1"

  # Case 3: forbidden token 'wip' in message body outside worktree -> reject
  run_case 3 1 \
    'git commit -m "chore: wip thing"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test" \
    "forbidden token 'wip' in body outside worktree -> exit 1"

  # Case 4: 'wip: bits' inside worktree path -> allow
  run_case 4 0 \
    'git commit -m "wip: bits"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test/.claude/worktrees/agent-1" \
    "wip: inside worktree path -> exit 0"

  # Case 5: emoji codepoint in message -> reject
  run_case 5 1 \
    'git commit -m "chore: ship 🚀 feature"' \
    "" \
    "emoji codepoint -> exit 1"

  # Case 6: git commit --amend (no -m/-F) -> pass through
  run_case 6 0 \
    'git commit --amend' \
    "" \
    "git commit --amend without -m -> exit 0 (pass-through)"

  # Case 7: git log --oneline -> pass through (not a commit)
  run_case 7 0 \
    'git log --oneline' \
    "" \
    "git log --oneline -> exit 0 (not a commit)"

  # Case 8: 'parallel streams' forbidden token -> reject
  run_case 8 1 \
    'git commit -m "chore: merge parallel streams into one"' \
    "" \
    "forbidden token 'parallel streams' -> exit 1"

  # Case 9: git commit-tree plumbing -> pass through (not porcelain commit)
  run_case 9 0 \
    'git commit-tree abc123 -m "tree msg"' \
    "" \
    "git commit-tree -> exit 0 (not a porcelain commit)"

  # Case 10: -F nonexistent file -> exit 0 with stderr diagnostic
  run_case 10 0 \
    'git commit -F /nonexistent/path/msg.txt' \
    "" \
    "-F unreadable file -> exit 0 (pass-through with stderr)"

  # Case 11: readable -F inside repo with valid message -> exit 0 (NB5)
  # B2: -F is only read when inside repo toplevel, so fixtures must live there.
  _toplevel_for_selftest=$(git rev-parse --show-toplevel 2>/dev/null || echo "/tmp")
  _tmp11=$(mktemp "$_toplevel_for_selftest/.validate-selftest-11.XXXXXX")
  printf 'chore: bump deps\n' > "$_tmp11"
  run_case 11 0 \
    "git commit -F $_tmp11" \
    "" \
    "-F readable in-repo file with valid message -> exit 0"
  rm -f "$_tmp11"

  # Case 12: readable -F inside repo with emoji -> exit 1 (NB5)
  _tmp12=$(mktemp "$_toplevel_for_selftest/.validate-selftest-12.XXXXXX")
  printf 'chore: ship \xf0\x9f\x9a\x80 feature\n' > "$_tmp12"
  run_case 12 1 \
    "git commit -F $_tmp12" \
    "" \
    "-F readable in-repo file with emoji -> exit 1"
  rm -f "$_tmp12"

  # Case 13: multi-m with forbidden token in second -m -> exit 1 (N4)
  run_case 13 1 \
    'git commit -m "feat: ok" -m "wip parallel streams"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test" \
    "multi-m: forbidden token in second -m outside worktree -> exit 1"

  # Case 14: valid type with incidental 'wip' body word inside worktree -> exit 0 (N5)
  run_case 14 0 \
    'git commit -m "chore: fix wip thing"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test/.claude/worktrees/agent-1" \
    "valid type with incidental wip word inside worktree -> exit 0"

  # Case 15 (B1): uppercase WIP outside worktree -> reject (case-insensitive scan)
  run_case 15 1 \
    'git commit -m "chore: ship WIP feature"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test" \
    "uppercase WIP outside worktree -> exit 1"

  # Case 16 (B1): 'Parallel Streams' mixed case -> reject
  run_case 16 1 \
    'git commit -m "chore: merge Parallel Streams rollout"' \
    "" \
    "mixed-case Parallel Streams -> exit 1"

  # Case 17 (B1): 'Stream A' mixed case -> reject
  run_case 17 1 \
    'git commit -m "fix: resolve Stream A conflicts"' \
    "" \
    "mixed-case Stream A -> exit 1"

  # Case 18 (B3): override without SELFTEST flag -> rejected (override not honoured)
  _case18_payload=$(python3 -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" 'git commit -m "wip: bypass"')
  _case18_exit=0
  VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test/.claude/worktrees/fake bash "$SCRIPT" <<< "$_case18_payload" >/dev/null 2>&1 || _case18_exit=$?
  if [ "$_case18_exit" = "1" ]; then
    echo "PASS  case 18: B3 override without SELFTEST flag -> exit 1"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "FAIL  case 18: B3 override without SELFTEST flag -> exit 1 (got $_case18_exit)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  # Case 19 (B4): --message=value form with forbidden token -> reject
  run_case 19 1 \
    'git commit --message=wip-stuff' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test" \
    "--message=value form with wip -> exit 1"

  # Case 20 (B4): escaped inner quotes with forbidden second -m -> reject
  run_case 20 1 \
    'git commit -m "feat: \"q\"" -m "wip parallel streams"' \
    "VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE=/tmp/wt-test" \
    "escaped quotes + multi-m wip -> exit 1"

  # Case 21 (B2): -F path outside repo toplevel -> exit 0 with diagnostic, no file contents
  _case21_out=$(python3 -c "import json,sys; print(json.dumps({'tool_input':{'command':'git commit -F /etc/passwd'}}))" | bash "$SCRIPT" 2>&1)
  _case21_exit=$?
  if [ "$_case21_exit" = "0" ] && ! echo "$_case21_out" | grep -qE '(root:|daemon:)'; then
    echo "PASS  case 21: B2 -F outside repo -> exit 0, no content leak"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "FAIL  case 21: B2 -F outside repo (exit=$_case21_exit, leak check failed)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  echo ""
  echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
  [ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
fi

# ─── Normal hook mode ─────────────────────────────────────────────────────────

INPUT=$(cat)

# N2/NB3: use bash builtins to pre-filter without spawning subshells.
# Skip Python parse for non-git-commit commands.
[[ "$INPUT" == *'git '* && "$INPUT" == *'commit'* ]] || exit 0

COMMAND=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('command', ''))
" 2>/dev/null)

[ -z "$COMMAND" ] && exit 0

# ─── Only act on git commit invocations ───────────────────────────────────────
# N2: use bash regex instead of echo | grep fork.
if ! [[ "$COMMAND" =~ (^|[[:space:]])git[[:space:]]+commit([[:space:]]|$) ]]; then
  exit 0
fi

# Compute real repo toplevel once; passed to python for -F sandboxing.
TOPLEVEL_REAL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")

# ─── Extract commit message from -m or -F ─────────────────────────────────────
# B4: tokenise with shlex (handles escaped quotes, quoted/unquoted mix, --message=value).
# B2: restrict -F reads to paths inside repo toplevel; never echo file contents outside repo.
MSG=$(REPO_TOPLEVEL="$TOPLEVEL_REAL" python3 -c "
import sys, os, shlex

cmd = sys.stdin.read().strip()

try:
    tokens = shlex.split(cmd, posix=True)
except ValueError:
    sys.exit(0)

messages = []
file_path = None
i = 0
while i < len(tokens):
    tok = tokens[i]
    if tok in ('-m', '--message'):
        if i + 1 < len(tokens):
            messages.append(tokens[i + 1])
            i += 2
            continue
    elif tok.startswith('-m=') or tok.startswith('--message='):
        messages.append(tok.split('=', 1)[1])
        i += 1
        continue
    elif tok in ('-F', '--file'):
        if i + 1 < len(tokens):
            file_path = tokens[i + 1]
            i += 2
            continue
    elif tok.startswith('-F=') or tok.startswith('--file='):
        file_path = tok.split('=', 1)[1]
        i += 1
        continue
    i += 1

if messages:
    print('\n\n'.join(messages))
    sys.exit(0)

if file_path is not None:
    if file_path == '-':
        sys.exit(0)
    toplevel = os.environ.get('REPO_TOPLEVEL', '')
    abs_path = os.path.realpath(file_path)
    in_repo = False
    if toplevel:
        real_top = os.path.realpath(toplevel)
        in_repo = abs_path == real_top or abs_path.startswith(real_top + os.sep)
    if not in_repo:
        print('validate-commit-msg: -F path outside repo toplevel; skipping content read', file=sys.stderr)
        sys.exit(0)
    try:
        with open(abs_path) as f:
            print(f.read())
        sys.exit(0)
    except Exception as e:
        print(f'validate-commit-msg: could not read -F file: {e}', file=sys.stderr)
        sys.exit(0)

sys.exit(0)
" <<< "$COMMAND" 2>/dev/null) || exit 0

[ -z "$MSG" ] && exit 0

# ─── Rule set ─────────────────────────────────────────────────────────────────
# Extract subject (first line)
SUBJECT=$(printf '%s' "$MSG" | head -1)
# N1: sanitize SUBJECT for error messages -- truncate to 120 chars and strip control chars.
SUBJECT_SAFE=$(printf '%s' "$SUBJECT" | head -c 120 | tr -d '[:cntrl:]')

# ─── Worktree carve-out check (must happen before conventional regex) ──────────
# B1: case-insensitive -- catches WIP, Wip, wip in any casing.
WIP_IN_MSG=0
if echo "$MSG" | grep -iqE '\bwip\b'; then
  WIP_IN_MSG=1
fi

if [ "$WIP_IN_MSG" -eq 1 ]; then
  # B3: honour override only when selftest flag is explicitly set.
  if [ "${VALIDATE_COMMIT_MSG_SELFTEST:-0}" = "1" ] && [ -n "${VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE:-}" ]; then
    TOPLEVEL="$VALIDATE_COMMIT_MSG_TOPLEVEL_OVERRIDE"
  else
    TOPLEVEL="$TOPLEVEL_REAL"
  fi

  # B2: anchor the worktree path match -- require /.claude/worktrees/<name>(/ or end).
  # Escape the literal dot in '.claude' to prevent matching '/Xclaude/worktrees/'.
  if echo "$TOPLEVEL" | grep -qE '/\.claude/worktrees/[^/]+(/|$)'; then
    # Inside worktree: wip is allowed. Still check other forbidden tokens and emoji.
    # Skip the conventional regex -- wip: messages are intentionally non-conventional.
    SKIP_CONVENTIONAL=1
  else
    # Outside worktree: wip is forbidden
    echo "error: forbidden-token: 'wip:' is only allowed inside /.claude/worktrees/ paths; current toplevel: $TOPLEVEL" >&2
    exit 1
  fi
else
  SKIP_CONVENTIONAL=0
fi

# 1. Conventional commit regex (subject = first line) -- skipped for wip inside worktree
if [ "$SKIP_CONVENTIONAL" -eq 0 ]; then
  CONVENTIONAL_REGEX='^(feat|fix|refactor|docs|test|chore|perf|style|build|ci)(\([^)]+\))?: [a-z].{1,99}$'
  if ! echo "$SUBJECT" | grep -qE "$CONVENTIONAL_REGEX"; then
    echo "error: conventional-commit: subject '$SUBJECT_SAFE' does not match required format (feat|fix|refactor|docs|test|chore|perf|style|build|ci)[optional scope]: <lowercase message>" >&2
    exit 1
  fi
fi

# 2. Other forbidden tokens (wip already handled above). B1: case-insensitive.
FORBIDDEN_PATTERN='(\bstream [A-E]\b|review-v[0-9]+|apply review|[0-9]+ findings|\bparallel\s+streams\b|merge: stream|across [0-9]+ streams)'
if echo "$MSG" | grep -iqE "$FORBIDDEN_PATTERN"; then
  OTHER_FORBIDDEN=$(echo "$MSG" | grep -ioE "$FORBIDDEN_PATTERN" | head -1)
  echo "error: forbidden-token: message contains AI workflow token '$OTHER_FORBIDDEN' -- see ~/.claude/rules/agents-worktrees.md § Commit Message Hygiene" >&2
  exit 1
fi

# 3. Emoji ban (unicode codepoint ranges)
EMOJI_RESULT=$(python3 -c "
import sys

msg = sys.stdin.read()

# Emoji and pictographic codepoint ranges to reject
RANGES = [
    (0x1F300, 0x1FAFF),  # Misc symbols, emoticons, transport, etc.
    (0x2600,  0x27BF),   # Misc symbols, dingbats
    (0x1F000, 0x1F02F),  # Mahjong tiles
    (0x1F0A0, 0x1F0FF),  # Playing cards
    (0x1F100, 0x1F1FF),  # Enclosed alphanumeric supplement
    (0xFE0F,  0xFE0F),   # Variation selector-16 (emoji presentation)
]

for ch in msg:
    cp = ord(ch)
    for lo, hi in RANGES:
        if lo <= cp <= hi:
            print(f'EMOJI:{hex(cp)}:{ch}')
            sys.exit(0)

print('OK')
" <<< "$MSG" 2>/dev/null)

if [ "${EMOJI_RESULT:0:5}" = "EMOJI" ]; then
  EMOJI_INFO="${EMOJI_RESULT#EMOJI:}"
  echo "error: emoji-ban: message contains emoji/pictographic character ($EMOJI_INFO) -- use plain ASCII text" >&2
  exit 1
fi

exit 0
