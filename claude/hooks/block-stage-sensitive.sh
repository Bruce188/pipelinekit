#!/bin/bash
# Blocks staging of sensitive files, workflow docs, and Claude config.
# Called by PreToolUse hook on Bash commands containing 'git add'.

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

# Only check git add commands (anchored to word boundary, not substring)
echo "$COMMAND" | grep -qE '(^|\s*&&\s*|\s*;\s*|\s*\|\|\s*)git add' || exit 0

# Early defense: extract path-looking tokens from the command and run them
# through _pathguard.py (shared Python helper — normalization, case-fold,
# shell expansion rejection, glob rejection, UNC rejection).
PATHGUARD="$(dirname "$0")/_pathguard.py"
if [ -f "$PATHGUARD" ]; then
  # Isolate the git add segment only.
  # 1. Find the git add subcommand.
  # 2. Trim at the first shell operator (&&, ||, ;, |, > , <, newline) so we
  #    don't feed downstream commands to pathguard.
  GITADD_SEGMENT=$(echo "$COMMAND" | sed -E 's/.*(git add[[:space:]].*)/\1/' | awk 'BEGIN{RS="&&|\\|\\||;|\n"} /^git add/ {print; exit}')
  # Strip "git add" and any leading flags.
  PATHS=$(echo "$GITADD_SEGMENT" | sed -E 's/^git add[[:space:]]+(-[A-Za-z]+[[:space:]]+)*//' | tr ' ' '\n' | sed '/^$/d')
  if [ -n "$PATHS" ]; then
    if ! echo "$PATHS" | python3 "$PATHGUARD" --stdin 2>&1; then
      # Denial tracking: convert to ask after 3 consecutive pathguard blocks.
      TRACKER="$(dirname "$0")/denial_tracker.py"
      if [ -f "$TRACKER" ]; then
        if python3 "$TRACKER" check Bash pathguard; then
          exit 0
        fi
        python3 "$TRACKER" record Bash pathguard 2>/dev/null
      fi
      exit 2
    fi
  fi
fi

# Block 'git add -A' and 'git add .' — UNLESS inside a worktree directory
if echo "$COMMAND" | grep -qE "git add\s+(-A|--all|-u|--update|\.)(\s|$)"; then
  CWD=$(pwd)
  if echo "$CWD" | grep -q "\.claude/worktrees/"; then
    # Inside a worktree — allow bulk staging (all files are intended)
    exit 0
  fi
  echo "BLOCKED: 'git add -A' / 'git add .' may stage protected files. Use specific file paths instead." >&2
  exit 2
fi

# --- Load patterns from config file and match against COMMAND ---
# Config: ~/.claude/config/never-stage.txt -- fnmatch-style globs, one per line.
# Missing/unreadable config = default-deny (exit 2).
NEVER_STAGE_CONFIG="${HOME}/.claude/config/never-stage.txt"
if [ ! -r "$NEVER_STAGE_CONFIG" ]; then
  echo "BLOCKED: never-stage config missing at ~/.claude/config/never-stage.txt -- default-deny engaged." >&2
  exit 2
fi

# python3 match engine: tests COMMAND tokens against fnmatch patterns from config.
# Exit 1 = match found (block), exit 0 = no match (allow).
MATCH_HELPER="$(dirname "$0")/_never_stage_match.py"
python3 "$MATCH_HELPER" "$COMMAND" "$NEVER_STAGE_CONFIG"
if [ $? -ne 0 ]; then
  # Exception: tracked .claude/ paths are allowed (committed deliverables).
  # Any path returned by `git ls-files .claude/` should pass this check.
  # Runtime state directories (projects/, sessions/, todos/, paste-cache/,
  # shell-snapshots/, statsig/, debug/, logs/, memory/, file-history/,
  # backups/, cache/) are NOT listed here and continue to block.
  if echo "$COMMAND" | grep -qF ".claude/"; then
    STRIPPED=$(echo "$COMMAND" \
      | sed 's|\.claude/CLAUDE\.md||g' \
      | sed 's|\.claude/skills/[^ "]*||g' \
      | sed 's|\.claude/agents/[^ "]*\.md||g' \
      | sed 's|\.claude/hooks/[^ "]*||g' \
      | sed 's|\.claude/rules/[^ "]*\.md||g' \
      | sed 's|\.claude/workflow-guide\.md||g' \
      | sed 's|\.claude/settings\.local\.json||g' \
      | sed 's|\.claude/settings\.json||g')
    if ! echo "$STRIPPED" | grep -qF ".claude/"; then
      # Only allowed .claude/ paths were mentioned — allow
      exit 0
    fi
  fi

  # Denial tracking: before blocking, check if we've hit this rule 3+ times
  # in the last 5 minutes. If so, convert to a permission-ask advisory
  # instead of silent block so the agent stops burning tokens in retry loops.
  TRACKER="$(dirname "$0")/denial_tracker.py"
  if [ -f "$TRACKER" ]; then
    if python3 "$TRACKER" check Bash stage-sensitive; then
      # check returned 0 → retry-limit reached, ask output already emitted
      exit 0
    fi
    python3 "$TRACKER" record Bash stage-sensitive 2>/dev/null
  fi
  echo "BLOCKED: Command matches a protected file pattern. These files must not be committed." >&2
  exit 2
fi

exit 0
