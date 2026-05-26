#!/usr/bin/env bash
# session-start-caveman.sh -- SessionStart hook.
#
# Touches ~/.claude/.caveman-active so the agent-caveman-gate.sh PreToolUse
# hook (matcher: Agent) enforces the caveman-subagent contract on every
# onward Agent dispatch in the new session. Without this marker the gate
# short-circuits with exit 0, leaving subagents free of the three-zone
# contract documented in ~/.claude/snippets/caveman-subagent.md.
#
# Operator opt-out: `touch ~/.claude/.caveman-off`. Presence of the off
# marker suppresses this hook for all future sessions until removed.
#
# Idempotent: re-running this hook is safe -- `touch` on an existing file
# only updates mtime and never errors.

set -euo pipefail

if [[ -e "${HOME}/.claude/.caveman-off" ]]; then
  exit 0
fi

mkdir -p "${HOME}/.claude"
touch "${HOME}/.claude/.caveman-active"
exit 0
