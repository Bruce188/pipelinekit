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
# The hooks' event log stays inside $T as well.
export PIPELINEKIT_STATE_DIR="$T/state"
unset PIPELINEKIT_LOG
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
out="$(bash "$REPO_ROOT/scripts/install.sh" --no-serena 2>&1)"
grep -qF '[install] copied 8 skills' <<<"$out"

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
(start,) = d["hooks"]["SessionStart"]
assert start["matcher"] == "startup" and len(start["hooks"]) == 1, "session check wired twice"
assert start["hooks"][0]["command"].endswith("/hooks/session-check.py")
PY
grep -q 'Test User <test@example.com>' "$CLAUDE_HOME/CLAUDE.md"
ls "$CLAUDE_HOME"/settings.json.bak-* >/dev/null
test -f "$CLAUDE_HOME/projects/keep/f"
for s in dotnet-conventions deploy exchange-api-keys docs-writer frontend-design mobile kit ship; do
  test -f "$CLAUDE_HOME/skills/$s/SKILL.md"
done
test -x "$CLAUDE_HOME/skills/ship/ship.py"
for f in SKILL.md LICENSE.txt SOURCE.md; do
  cmp "$REPO_ROOT/claude/skills/frontend-design/$f" "$CLAUDE_HOME/skills/frontend-design/$f"
done
grep -q 'Merges: ask first' "$CLAUDE_HOME/CLAUDE.md"
grep -qx '## Design' "$CLAUDE_HOME/CLAUDE.md"
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
# The session-start check has nothing to say about a fresh install.
[ -z "$(echo '{}' | "$CLAUDE_HOME/hooks/session-check.py")" ]

# verify notices a hook that is present but cannot start (CRLF checkout).
G="$CLAUDE_HOME/hooks/bash-guard.py"
sed $'s/$/\r/' "$G" > "$T/crlf" && cat "$T/crlf" > "$G"
if CLAUDE_HOME="$CLAUDE_HOME" bash "$REPO_ROOT/scripts/verify.sh" >/dev/null 2>&1; then
  echo "test_install: verify passed with a CRLF hook" >&2; exit 1
fi
# The session-start check names /kit once a hook is broken.
echo '{}' | "$CLAUDE_HOME/hooks/session-check.py" | grep -q 'Run /kit for the report'

# frontend-design: a folder of that name that the kit did not install. Each case
# runs in its own throwaway home below $T.
KIT_FD="$REPO_ROOT/claude/skills/frontend-design"
fd_home() { # fd_home <case>: a fresh home in $FH
  FH="$T/fd-$1"
  mkdir -p "$FH/.claude/skills"
}
fd_install() { # output in $FH/out
  HOME="$FH" CLAUDE_HOME="$FH/.claude" GIT_CONFIG_GLOBAL="$FH/.gitconfig" \
    XDG_CONFIG_HOME="$FH/.config" PIPELINEKIT_STATE_DIR="$FH/state" PIPELINEKIT_GIT_HOOKS=0 \
    bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$FH/out" 2>&1
}
fd_backups() {
  local d="$FH/.claude/pipelinekit/backup"
  if [[ -d "$d" ]]; then find "$d" -mindepth 1 -maxdepth 1 | wc -l; else echo 0; fi
}
fd_is_kit() { diff -r "$KIT_FD" "$FH/.claude/skills/frontend-design" >/dev/null; }

# (a) A hand-made skill before the first install: moved to a backup once.
fd_home a
mkdir "$FH/.claude/skills/frontend-design"
echo "my own design notes" >"$FH/.claude/skills/frontend-design/SKILL.md"
fd_install
fd_is_kit
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/*)
[[ "${B[0]##*/}" =~ ^skills-frontend-design-[0-9]{8}T[0-9]{6}Z$ ]]
grep -qx "my own design notes" "${B[0]}/SKILL.md"
grep -qxF "[install] kept your own frontend-design skill in ${B[0]}" "$FH/out"
fd_install
[ "$(fd_backups)" -eq 1 ]
if grep -qF 'kept your own' "$FH/out"; then
  echo "test_install: a second install backed up the kit's own copy" >&2; exit 1
fi

# (b) The kit's own copy, edited after the install: replaced, no backup.
fd_home b
fd_install
echo "my edit" >>"$FH/.claude/skills/frontend-design/SKILL.md"
fd_install
[ "$(fd_backups)" -eq 0 ]
fd_is_kit

# (c) A byte-identical copy and no manifest: replaced, no backup.
fd_home c
cp -R "$KIT_FD" "$FH/.claude/skills/frontend-design"
fd_install
[ "$(fd_backups)" -eq 0 ]
fd_is_kit

# (d) A link to a folder outside the home: only the link goes.
fd_home d
mkdir "$T/fd-outside"
echo "theirs" >"$T/fd-outside/SKILL.md"
ln -s "$T/fd-outside" "$FH/.claude/skills/frontend-design"
fd_install
test ! -L "$FH/.claude/skills/frontend-design"
fd_is_kit
[ "$(ls -A "$T/fd-outside")" = "SKILL.md" ]
[ "$(cat "$T/fd-outside/SKILL.md")" = "theirs" ]
[ "$(fd_backups)" -eq 0 ]
grep -qxF "[install] removed the link skills/frontend-design -> $T/fd-outside" "$FH/out"

# (e) A hand-made folder and a manifest that is not JSON: backed up, install ends well.
fd_home e
mkdir -p "$FH/.claude/skills/frontend-design" "$FH/.claude/pipelinekit"
echo "mine" >"$FH/.claude/skills/frontend-design/SKILL.md"
echo "{not json" >"$FH/.claude/pipelinekit/manifest.json"
fd_install || { echo "test_install: install failed with a damaged manifest" >&2; cat "$FH/out" >&2; exit 1; }
[ "$(fd_backups)" -eq 1 ]
fd_is_kit
echo "test_install: PASS"
