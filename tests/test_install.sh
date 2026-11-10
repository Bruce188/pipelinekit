#!/usr/bin/env bash
# Install into a throwaway HOME and check the result. Run twice for idempotence.
# Needs the repo's git history (old kit files are seeded from it).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export HOME="$T" CLAUDE_HOME="$T/.claude" USER_NAME="Test User" USER_EMAIL="test@example.com"
# Keep git's global config inside $T no matter what the caller's env says.
export GIT_CONFIG_GLOBAL="$T/.gitconfig" XDG_CONFIG_HOME="$T/.config" GIT_CONFIG_NOSYSTEM=1
export PIPELINEKIT_GIT_HOOKS=1
mkdir -p "$CLAUDE_HOME"/{hooks,agents,skills/ios,skills/commit-conventions,skills/expo} "$CLAUDE_HOME/projects/keep"
echo keep > "$CLAUDE_HOME/projects/keep/f"

# A previous install: unmodified kit copies (must go) and edited ones (must stay).
old() { # print the last committed version of a path that no longer exists
  local c
  c="$(git -C "$REPO_ROOT" rev-list -1 --all -- "$1")"
  git -C "$REPO_ROOT" show "$c:$1" 2>/dev/null || git -C "$REPO_ROOT" show "$c^:$1"
}
for f in skills/commit-conventions/SKILL.md skills/expo/SKILL.md hooks/block-push-main.sh \
         hooks/denial_tracker.py agents/docs-writer.md; do
  old "claude/$f" > "$CLAUDE_HOME/$f"
done
{ old claude/skills/ios/SKILL.md; echo "my edit"; } > "$CLAUDE_HOME/skills/ios/SKILL.md"
{ old claude/hooks/env-scrub.py; echo "# my edit"; } > "$CLAUDE_HOME/hooks/env-scrub.py"
echo "mine" > "$CLAUDE_HOME/agents/other.md"

# Pre-existing settings: stale and old-kit hooks, a user hook, user rules, an unrelated key.
H="$CLAUDE_HOME/hooks"
cat > "$CLAUDE_HOME/settings.json" <<JSON
{"model": "x", "includeCoAuthoredBy": false,
 "env": {"FOO": "1"},
 "permissions": {"allow": ["Bash(ls *)"], "deny": ["Read(secret.txt)"]},
 "hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "$H/gone.sh"}]}],
           "PreToolUse": [{"matcher": "Bash", "hooks": [
              {"type": "command", "command": "$H/block-push-main.sh"},
              {"type": "command", "command": "$H/env-scrub.py"},
              {"type": "command", "command": "echo my-hook"}]}]}}
JSON

# A native Windows shell (Git Bash, MSYS, Cygwin) is refused before anything is written.
mkdir "$T/fakebin"
printf '#!/bin/sh\necho MINGW64_NT-10.0-26200\n' > "$T/fakebin/uname"
chmod +x "$T/fakebin/uname"
if PATH="$T/fakebin:$PATH" CLAUDE_HOME="$T/win" bash "$REPO_ROOT/scripts/install.sh" --no-serena >/dev/null 2>&1; then
  echo "test_install: installer ran under a Windows uname" >&2; exit 1
fi
test ! -e "$T/win"

bash "$REPO_ROOT/scripts/install.sh" --no-serena >/dev/null 2>&1
bash "$REPO_ROOT/scripts/install.sh" --no-serena >/dev/null 2>&1

python3 - "$CLAUDE_HOME/settings.json" "$REPO_ROOT/claude/config/settings.template.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
t = json.load(open(sys.argv[2]))
assert d["model"] == "x", "unrelated key lost"
assert d["attribution"] == {"commit": "", "pr": "", "sessionUrl": False}
assert "includeCoAuthoredBy" not in d
assert d["env"] == {"FOO": "1"}
p = d["permissions"]
assert p["allow"] == ["Bash(ls *)"], "user allow rules changed"
assert p["deny"] == ["Read(secret.txt)"] + t["permissions"]["deny"], "deny merge wrong"
assert p["ask"] == t["permissions"]["ask"]
assert "Stop" not in d["hooks"], "stale hook not pruned"
hs = [h for g in d["hooks"]["PreToolUse"] for h in g["hooks"]]
cmds = [h["command"] for h in hs]
keys = [json.dumps(h, sort_keys=True) for h in hs]
assert len(keys) == len(set(keys)), "duplicate hooks after re-run"
assert sum(c.endswith("/bash-guard.py") for c in cmds) == 9
assert "echo my-hook" in cmds, "user hook lost"
assert not any(c.endswith(("block-push-main.sh", "env-scrub.py")) for c in cmds), "old kit hook kept"
assert "${CLAUDE_HOME}" not in json.dumps(d)
PY
grep -q 'Test User <test@example.com>' "$CLAUDE_HOME/CLAUDE.md"
ls "$CLAUDE_HOME"/settings.json.bak-* >/dev/null
test -f "$CLAUDE_HOME/projects/keep/f"
for s in dotnet-conventions deploy exchange-api-keys docs-writer mobile kit ship; do
  test -f "$CLAUDE_HOME/skills/$s/SKILL.md"
done
test -x "$CLAUDE_HOME/skills/ship/ship.py"
grep -q 'Merges: ask first' "$CLAUDE_HOME/CLAUDE.md"
# The helper starts from its installed place and says why it cannot go on.
(cd "$T" && python3 "$CLAUDE_HOME/skills/ship/ship.py" status --exit-zero | grep -q 'not inside a git repository')
test ! -e "$CLAUDE_HOME/skills/commit-conventions"
test ! -e "$CLAUDE_HOME/skills/expo"
test -f "$CLAUDE_HOME/skills/ios/SKILL.md"           # edited: kept
test ! -e "$CLAUDE_HOME/hooks/block-push-main.sh"
test ! -e "$CLAUDE_HOME/hooks/denial_tracker.py"
test -f "$CLAUDE_HOME/hooks/env-scrub.py"            # edited: kept
test ! -e "$CLAUDE_HOME/agents/docs-writer.md"
test -f "$CLAUDE_HOME/agents/other.md"
test ! -e "$CLAUDE_HOME/hooks/tests"
test -x "$CLAUDE_HOME/git-hooks/pre-push"
[ "$(git config --global core.hooksPath)" = "$CLAUDE_HOME/git-hooks" ]
python3 - "$CLAUDE_HOME" "$REPO_ROOT" <<'PY'
import json, subprocess, sys
home, repo = sys.argv[1:]
m = json.load(open(f"{home}/pipelinekit/manifest.json"))
head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert m["commit"] == head, "manifest commit is not the checkout's HEAD"
assert m["hooks_path"] == f"{home}/git-hooks", "manifest missed the hooks path set by this install"
assert "skills/kit/check.py" in m["files"] and all(m["files"].values()), "manifest file list incomplete"
PY
CLAUDE_HOME="$CLAUDE_HOME" bash "$REPO_ROOT/scripts/verify.sh" >/dev/null

# verify notices a hook that is present but cannot start (CRLF checkout).
G="$CLAUDE_HOME/hooks/bash-guard.py"
sed $'s/$/\r/' "$G" > "$T/crlf" && cat "$T/crlf" > "$G"
if CLAUDE_HOME="$CLAUDE_HOME" bash "$REPO_ROOT/scripts/verify.sh" >/dev/null 2>&1; then
  echo "test_install: verify passed with a CRLF hook" >&2; exit 1
fi
echo "test_install: PASS"
