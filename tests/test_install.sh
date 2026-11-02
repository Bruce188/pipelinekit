#!/usr/bin/env bash
# Install into a throwaway HOME and check the result. Run twice for idempotence.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export HOME="$T" CLAUDE_HOME="$T/.claude" USER_NAME="Test User" USER_EMAIL="test@example.com"
mkdir -p "$CLAUDE_HOME/hooks" "$CLAUDE_HOME/projects/keep"
echo keep > "$CLAUDE_HOME/projects/keep/f"
# Pre-existing settings with a stale hook and an unrelated key.
cat > "$CLAUDE_HOME/settings.json" <<JSON
{"model": "x", "hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "$CLAUDE_HOME/hooks/gone.sh"}]}]}}
JSON

bash "$REPO_ROOT/scripts/install.sh" --no-serena >/dev/null
bash "$REPO_ROOT/scripts/install.sh" --no-serena >/dev/null

python3 - "$CLAUDE_HOME/settings.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["model"] == "x", "unrelated key lost"
assert d["attribution"] == {"commit": "", "pr": "", "sessionUrl": False}
assert "Stop" not in d["hooks"], "stale hook not pruned"
cmds = [h["command"] for g in d["hooks"]["PreToolUse"] for h in g["hooks"]]
assert len(cmds) == len(set(cmds)), "duplicate hooks after re-run"
assert any(c.endswith("block-stage-sensitive.sh") for c in cmds)
PY
grep -q 'Test User <test@example.com>' "$CLAUDE_HOME/CLAUDE.md"
test -f "$CLAUDE_HOME/projects/keep/f"
test -f "$CLAUDE_HOME/skills/deploy/SKILL.md"
test ! -e "$CLAUDE_HOME/hooks/tests"
echo "test_install: PASS"
