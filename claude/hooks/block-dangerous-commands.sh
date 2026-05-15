#!/bin/bash
# Blocks dangerous git and docker commands:
# - git remote add (exfil via arbitrary remotes)
# - git push to non-origin remotes
# - git config --global (alters credential helpers)
# - git destructive: reset --hard, checkout --, restore, clean, branch -D
# - docker volume mounts of sensitive host paths, --privileged
# - SQL destructive: DROP TABLE/DATABASE/INDEX/SCHEMA/VIEW, TRUNCATE
# Called by PreToolUse hook — receives tool input on stdin.

INPUT=$(cat)

# Shell pre-filter: skip Python parse for irrelevant commands (case-insensitive for SQL)
echo "$INPUT" | grep -qiE '(git (remote|push|config|reset|checkout|clean|restore|branch)|docker|drop|truncate)' || exit 0

COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

[ -z "$COMMAND" ] && exit 0

# --- Git guards ---

# Block git remote add (flexible whitespace)
if echo "$COMMAND" | grep -qE 'git\s+remote\s+add\b'; then
  echo "BLOCKED: 'git remote add' is not allowed. Only 'origin' remote is permitted." >&2
  exit 2
fi

# Block git config --global (flexible whitespace)
if echo "$COMMAND" | grep -qE 'git\s+config\s+--global\b'; then
  echo "BLOCKED: 'git config --global' is not allowed." >&2
  exit 2
fi

# Block git push to non-origin remotes
# Extract remote by finding the first non-flag argument after "git push"
if echo "$COMMAND" | grep -qE 'git\s+push\b'; then
  REMOTE=$(printf '%s' "$COMMAND" | python3 -c "
import sys, re
cmd = sys.stdin.read()
m = re.search(r'git\s+push\s+(.*)', cmd)
if m:
    args = m.group(1).split()
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        # Handle --flag=value form (skip entirely)
        if a.startswith('--') and '=' in a:
            continue
        if a in ('--repo', '--push-option', '--signed', '-o', '--recurse-submodules'):
            skip_next = True
            continue
        if not a.startswith('-'):
            print(a)
            break
" 2>/dev/null)
  if [ -n "$REMOTE" ] && [ "$REMOTE" != "origin" ]; then
    echo "BLOCKED: Push to non-origin remote '$REMOTE'. Only 'origin' is permitted." >&2
    exit 2
  fi
fi

# --- Permission-ask helper ---
# Emit hookSpecificOutput JSON on stdout and exit 0. Claude Code displays
# the reason to the user and prompts for confirmation. Compatible with the
# current hooks schema — an invalid JSON emission falls through to exit 2.
ask_permission() {
  local reason="$1"
  python3 -c "
import json, sys
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'ask',
        'permissionDecisionReason': '''$reason'''
    }
}))
" && exit 0
  # If python3 failed, fall back to hard block so safety is preserved.
  echo "BLOCKED (ask-mode fallback): $reason" >&2
  exit 2
}

# --- Docker guards ---

if echo "$COMMAND" | grep -qE 'docker\s+(run|create|compose|build)'; then
  # --privileged: ask (legitimate for some toolchains)
  if echo "$COMMAND" | grep -qE -- '--privileged'; then
    ask_permission "docker --privileged grants full host access. Confirm?"
  fi

  # Block sensitive host path mounts via -v, --volume, --volume=, --mount
  # Uses Python to extract all mount paths (portable, handles multiple -v flags)
  # Only resolves paths containing / or .. — named volumes skip resolution
  MOUNT_RESULT=$(printf '%s' "$COMMAND" | python3 -c "
import sys, re, os
cmd = sys.stdin.read()
sensitive = ('/', '/home', '/root', '/etc', '/var', '/tmp', '/proc', '/sys')

def check_path(p):
    if not p:
        return False
    # Only resolve paths, not named Docker volumes
    if '/' in p or p.startswith('.'):
        try:
            p = os.path.realpath(os.path.join(os.getcwd(), p)) if not os.path.isabs(p) else os.path.realpath(p)
        except Exception:
            pass
    else:
        return False  # Named volume — skip
    # Check if resolved path matches or is under a sensitive prefix
    if p in sensitive:
        return True
    for s in sensitive:
        if s != '/' and p.startswith(s + '/'):
            return True
    if p.startswith('/') and p.count('/') == 1:
        return True  # Root itself
    return False

# Extract -v / --volume paths (host:container or host:container:opts)
for m in re.finditer(r'(?:-v|--volume)[= ]([^: ]+)', cmd):
    if check_path(m.group(1)):
        print('BLOCKED')
        sys.exit(0)

# Extract --mount source= / src= paths
for m in re.finditer(r'(?:source|src)=([^, ]+)', cmd):
    if check_path(m.group(1)):
        print('BLOCKED')
        sys.exit(0)

print('OK')
" 2>/dev/null)
  if [ "$MOUNT_RESULT" = "BLOCKED" ]; then
    echo "BLOCKED: Docker volume mount of sensitive host path is not allowed." >&2
    exit 2
  fi
fi

# --- Git destructive guards ---

# git reset --hard (irreversible state destruction) — ASK
# Matches --hard anywhere after reset (e.g. git reset HEAD --hard)
if echo "$COMMAND" | grep -qE 'git\s+reset\b.*--hard\b'; then
  ask_permission "git reset --hard discards all uncommitted changes. Confirm?"
fi

# git checkout . or git checkout -- . (discards unstaged changes) — ASK
if echo "$COMMAND" | grep -qE 'git\s+checkout\s+(-[a-zA-Z]+\s+)*(--\s+)?\.(\s|$)'; then
  ask_permission "git checkout . discards unstaged changes. Confirm?"
fi

# git restore . / git restore --worktree — ASK
if echo "$COMMAND" | grep -qE 'git\s+restore\s+(\.|\*|--worktree)'; then
  ask_permission "git restore . discards working tree changes. Confirm?"
fi

# Block git branch -D (force-deletes branches, losing unmerged work) — HARD BLOCK
# Not in F12 ask-mode convert list; user can override by running outside the hook.
if echo "$COMMAND" | grep -qE 'git\s+branch\s+(-D|--delete\s+--force)\b'; then
  echo "BLOCKED: 'git branch -D' force-deletes branches. Use 'git branch -d' (safe delete) instead." >&2
  exit 2
fi

# git clean -fd / --force (deletes untracked files irreversibly) — ASK
if echo "$COMMAND" | grep -qE 'git\s+clean\s+.*(--force|-[a-zA-Z]*f)'; then
  ask_permission "git clean --force deletes untracked files. Confirm?"
fi

# --- SQL destructive guards ---

# SQL destructive commands (DROP TABLE/DATABASE/INDEX/SCHEMA/VIEW, TRUNCATE) — ASK
if echo "$COMMAND" | grep -qiE '\b(DROP\s+(TABLE|DATABASE|INDEX|SCHEMA|VIEW)|TRUNCATE)\b'; then
  ask_permission "SQL destructive command (DROP/TRUNCATE). Confirm?"
fi

exit 0
