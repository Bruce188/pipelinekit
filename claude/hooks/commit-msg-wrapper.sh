#!/bin/bash
# Native git commit-msg hook adapter. Bridges git's argv-passed message-file to
# claude/hooks/validate-commit-msg.sh's stdin-JSON contract so the conventional-
# commit gate fires on EVERY git commit (Claude-mediated, bare, CI, IDE), not
# just commits driven through the harness PreToolUse event.
#
# Installed by scripts/install.sh as a symlink at <GIT_DIR>/hooks/commit-msg.
# Reads $1 = message-file path; constructs synthetic Claude envelope; pipes to
# the validator; propagates exit code. Worktree-compatible via rev-parse.

set -euo pipefail

MSG_FILE="${1:-}"

# Rebase reword / amend --no-edit: empty or missing message file -> silent allow.
[ -z "$MSG_FILE" ] && exit 0
[ ! -f "$MSG_FILE" ] && exit 0
[ ! -s "$MSG_FILE" ] && exit 0

# Resolve the wrapper's REAL location (follow the symlink at .git/hooks/commit-msg
# back to its install path inside the pipelinekit checkout). The validator lives
# alongside this wrapper at claude/hooks/validate-commit-msg.sh -- relative to
# the wrapper, NOT relative to whichever git repo we are committing into.
WRAPPER_REAL="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
WRAPPER_DIR="$(cd "$(dirname "$WRAPPER_REAL")" && pwd)"
VALIDATOR="$WRAPPER_DIR/validate-commit-msg.sh"

# Defensive: validator missing means the install is broken upstream. Allow the
# commit rather than block (prevents user lock-out from a stale symlink).
[ ! -x "$VALIDATOR" ] && exit 0

# Absolutise message-file path so the validator's -F sandbox check
# (validate-commit-msg.sh B2: "-F path outside repo toplevel; skipping content read")
# resolves cleanly inside the current repo. The validator runs `git rev-parse
# --show-toplevel` itself in our inherited pwd, which IS the repo we are
# committing into; the message file lives at <git_dir>/COMMIT_EDITMSG inside
# that same repo, so the in-repo check passes.
ABS_MSG="$(cd "$(dirname "$MSG_FILE")" && pwd)/$(basename "$MSG_FILE")"

# Synthesize PreToolUse envelope and pipe to validator. Use python3 (jq is not
# guaranteed present per claude/hooks/CLAUDE.md § stdlib only).
python3 -c "
import json, sys
print(json.dumps({'tool_input': {'command': sys.argv[1]}}))
" "git commit -F $ABS_MSG" | "$VALIDATOR"
