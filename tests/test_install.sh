#!/usr/bin/env bash
# Install into a throwaway HOME and check the result. Run twice for idempotence.
# Needs the repo's git history (old kit files are seeded from it).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"
# A case that stops while a folder is read-only still leaves nothing behind.
trap 'chmod -R u+w "$T" 2>/dev/null; rm -rf "$T"' EXIT
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
# A user's own agent with a kit name (moved to a backup once), and a link with
# another kit name (removed, never followed).
echo "my own judge" > "$CLAUDE_HOME/agents/kit-judge.md"
echo "outside" > "$T/outside-agent.md"
ln -s "$T/outside-agent.md" "$CLAUDE_HOME/agents/kit-builder.md"

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

# The usage text names the agents.
help="$(bash "$REPO_ROOT/scripts/install.sh" --help)"
for a in kit-planner kit-builder kit-judge; do
  grep -qF "$a" <<<"$help"
done

bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$T/install1.out" 2>&1
bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$T/install2.out" 2>&1
grep -qF '[install] copied 8 skills' "$T/install2.out"
n_skills="$(sed -n 's/^KIT_SKILLS=(\(.*\))$/\1/p' "$REPO_ROOT/scripts/install.sh" | wc -w | tr -d ' ')"
grep -qF "[install] copied $n_skills skills, 3 agents, " "$T/install2.out"
# The closing line names the agents and says how to load them.
[ "$(tail -n 1 "$T/install2.out")" = \
  "[install] start a new session to load the agents (kit-planner, kit-builder, kit-judge)" ]

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
[ "$(cat "$CLAUDE_HOME/agents/other.md")" = "mine" ]
for a in kit-planner.md kit-builder.md kit-judge.md; do
  test -f "$CLAUDE_HOME/agents/$a"
  test ! -L "$CLAUDE_HOME/agents/$a"
  cmp "$REPO_ROOT/claude/agents/$a" "$CLAUDE_HOME/agents/$a"
done
[ "$(cat "$T/outside-agent.md")" = "outside" ]           # the link was not followed
grep -qxF "[install] removed the link agents/kit-builder.md (its target is untouched)" "$T/install1.out"
set -- "$CLAUDE_HOME"/pipelinekit/backup/*
[ "$#" -eq 1 ]                                            # the own judge only, not the link
[ -f "$1" ]
[[ "${1##*/}" =~ ^agents-kit-judge\.md-[0-9]{8}-[0-9]{6}$ ]]
[ "$(cat "$1")" = "my own judge" ]
grep -qxF "[install] kept your own kit-judge.md in $1" "$T/install1.out"
if grep -qF 'kept your own' "$T/install2.out"; then
  echo "test_install: a second install backed up the kit's own agent" >&2; exit 1
fi
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

# An installed agent edited by hand: the check lists it, an install restores it
# without a backup.
echo "my edit" >> "$CLAUDE_HOME/agents/kit-planner.md"
report="$(python3 "$CLAUDE_HOME/skills/kit/check.py" --no-remote)"
grep -qF 'changed since install: agents/kit-planner.md' <<<"$report"
bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$T/install3.out" 2>&1
cmp "$REPO_ROOT/claude/agents/kit-planner.md" "$CLAUDE_HOME/agents/kit-planner.md"
if grep -qF 'kept your own' "$T/install3.out"; then
  echo "test_install: an edited kit agent was backed up" >&2; exit 1
fi
set -- "${CLAUDE_HOME}"/pipelinekit/backup/agents-*
[ "$#" -eq 1 ]
[ -f "$1" ]

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
B=("$FH"/.claude/pipelinekit/backup/*)
grep -qx "mine" "${B[0]}/SKILL.md"
fd_is_kit

# (f) A hand-made folder and a manifest whose skills entry is not a list: backed up.
fd_home f
mkdir -p "$FH/.claude/skills/frontend-design" "$FH/.claude/pipelinekit"
echo "mine as well" >"$FH/.claude/skills/frontend-design/SKILL.md"
echo '{"skills": "frontend-design"}' >"$FH/.claude/pipelinekit/manifest.json"
fd_install || { echo "test_install: install failed with a misshapen manifest" >&2; cat "$FH/out" >&2; exit 1; }
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/*)
grep -qx "mine as well" "${B[0]}/SKILL.md"
fd_is_kit

# (g) A file of that name: moved to a backup, also once the manifest lists the skill.
fd_home g
echo "a file, not a skill" >"$FH/.claude/skills/frontend-design"
fd_install || { echo "test_install: install failed with a file in place of the skill" >&2; cat "$FH/out" >&2; exit 1; }
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/*)
test -f "${B[0]}"
grep -qx "a file, not a skill" "${B[0]}"
grep -qxF "[install] kept your own frontend-design skill in ${B[0]}" "$FH/out"
test -d "$FH/.claude/skills/frontend-design"
fd_is_kit
python3 - "$FH/.claude/pipelinekit/manifest.json" <<'PY'
import json, sys
assert "frontend-design" in json.load(open(sys.argv[1]))["skills"], "manifest misses the skill"
PY
rm -rf "$FH/.claude/pipelinekit/backup" "$FH/.claude/skills/frontend-design"
echo "a second file" >"$FH/.claude/skills/frontend-design"
fd_install
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/*)
grep -qx "a second file" "${B[0]}"
fd_is_kit
# (h), (i): the own folder cannot be moved. The installer stops with one line of
# its own, without mkdir's or mv's text, and leaves the folder as it was.
fd_cannot_move() { # fd_cannot_move <tool whose text must not show>
  local own="$FH/.claude/skills/frontend-design" rc=0
  HOME="$FH" CLAUDE_HOME="$FH/.claude" GIT_CONFIG_GLOBAL="$FH/.gitconfig" \
    XDG_CONFIG_HOME="$FH/.config" PIPELINEKIT_STATE_DIR="$FH/state" PIPELINEKIT_GIT_HOOKS=0 \
    bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$FH/out" 2>"$FH/err" || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "test_install: install went on with an own folder it could not move" >&2; exit 1
  fi
  if ! grep -qxF "[install][error] could not move your own skills/frontend-design to $FH/.claude/pipelinekit/backup. It is untouched and the skills were not installed. Move or rename it yourself, then run the installer again." "$FH/err"; then
    echo "test_install: no line saying the own folder could not be moved" >&2; cat "$FH/err" >&2; exit 1
  fi
  if grep -qF "$1:" "$FH/err"; then
    echo "test_install: the raw $1 error was shown" >&2; cat "$FH/err" >&2; exit 1
  fi
  if [ "$(ls -A "$own")" != "SKILL.md" ] || [ "$(cat "$own/SKILL.md")" != "my own, kept" ]; then
    echo "test_install: the own folder changed" >&2; exit 1
  fi
}

# (h) The own folder and skills/ are read-only. Root is not stopped by the mode.
if [ "$(id -u)" -ne 0 ]; then
  fd_home h
  mkdir "$FH/.claude/skills/frontend-design"
  echo "my own, kept" >"$FH/.claude/skills/frontend-design/SKILL.md"
  chmod 555 "$FH/.claude/skills/frontend-design" "$FH/.claude/skills"
  fd_cannot_move mv
  chmod 755 "$FH/.claude/skills/frontend-design" "$FH/.claude/skills"
fi

# (i) A file where the backup folder goes.
fd_home i
mkdir -p "$FH/.claude/skills/frontend-design" "$FH/.claude/pipelinekit"
echo "my own, kept" >"$FH/.claude/skills/frontend-design/SKILL.md"
echo "not a folder" >"$FH/.claude/pipelinekit/backup"
fd_cannot_move mkdir
test -f "$FH/.claude/pipelinekit/backup"

# (j) A manifest holding only "{" and a user's own kit-judge.md: the manifest
# lists nothing, so the file is backed up, and the install ends well.
fd_home j
mkdir -p "$FH/.claude/agents" "$FH/.claude/pipelinekit"
echo "{" >"$FH/.claude/pipelinekit/manifest.json"
echo "my own judge" >"$FH/.claude/agents/kit-judge.md"
fd_install || { echo "test_install: install failed with a broken manifest" >&2; cat "$FH/out" >&2; exit 1; }
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/agents-kit-judge.md-*)
[ "$(cat "${B[0]}")" = "my own judge" ]
cmp "$REPO_ROOT/claude/agents/kit-judge.md" "$FH/.claude/agents/kit-judge.md"
python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$FH/.claude/pipelinekit/manifest.json"

# (k) A byte-identical copy of the kit's kit-judge.md and no manifest, (l) the
# same with a manifest holding only "{": the kit's own file, so no backup.
for c in k l; do
  fd_home "$c"
  mkdir -p "$FH/.claude/agents"
  cp "$REPO_ROOT/claude/agents/kit-judge.md" "$FH/.claude/agents/kit-judge.md"
  if [ "$c" = l ]; then
    mkdir -p "$FH/.claude/pipelinekit"
    echo "{" >"$FH/.claude/pipelinekit/manifest.json"
  fi
  fd_install || { echo "test_install: install failed with the kit's own kit-judge.md ($c)" >&2; cat "$FH/out" >&2; exit 1; }
  [ "$(fd_backups)" -eq 0 ]
  if grep -qF 'kept your own' "$FH/out"; then
    echo "test_install: a copy of the kit's own kit-judge.md was backed up ($c)" >&2; exit 1
  fi
  cmp "$REPO_ROOT/claude/agents/kit-judge.md" "$FH/.claude/agents/kit-judge.md"
done

# (m) A file where the backup folder goes and a user's own kit-judge.md: the
# installer stops with one line of its own and leaves the file as it was.
fd_home m
mkdir -p "$FH/.claude/agents" "$FH/.claude/pipelinekit"
echo "my own judge, kept" >"$FH/.claude/agents/kit-judge.md"
echo "not a folder" >"$FH/.claude/pipelinekit/backup"
rc=0
HOME="$FH" CLAUDE_HOME="$FH/.claude" GIT_CONFIG_GLOBAL="$FH/.gitconfig" \
  XDG_CONFIG_HOME="$FH/.config" PIPELINEKIT_STATE_DIR="$FH/state" PIPELINEKIT_GIT_HOOKS=0 \
  bash "$REPO_ROOT/scripts/install.sh" --no-serena >"$FH/out" 2>"$FH/err" || rc=$?
if [ "$rc" -eq 0 ]; then
  echo "test_install: install went on with an own agent it could not move" >&2; exit 1
fi
if [ "$(cat "$FH/err")" != "[install][error] could not move your own agents/kit-judge.md to $FH/.claude/pipelinekit/backup. It is untouched and the kit's kit-judge.md was not installed. Move or rename it yourself, then run the installer again." ]; then
  echo "test_install: stderr is not the one line about the own agent" >&2; cat "$FH/err" >&2; exit 1
fi
if grep -qE '(mkdir|mv):' "$FH/err"; then
  echo "test_install: the raw mkdir or mv error was shown" >&2; cat "$FH/err" >&2; exit 1
fi
[ "$(cat "$FH/.claude/agents/kit-judge.md")" = "my own judge, kept" ]
test -f "$FH/.claude/pipelinekit/backup"

# (n) A folder named kit-planner.md holding one file: moved to a backup with its
# file, and the kit's file is installed.
fd_home n
mkdir -p "$FH/.claude/agents/kit-planner.md"
echo "inside" >"$FH/.claude/agents/kit-planner.md/note.txt"
fd_install || { echo "test_install: install failed with a folder in place of an agent" >&2; cat "$FH/out" >&2; exit 1; }
[ "$(fd_backups)" -eq 1 ]
B=("$FH"/.claude/pipelinekit/backup/agents-kit-planner.md-*)
test -d "${B[0]}"
[ "$(ls -A "${B[0]}")" = "note.txt" ]
[ "$(cat "${B[0]}/note.txt")" = "inside" ]
test -f "$FH/.claude/agents/kit-planner.md"
cmp "$REPO_ROOT/claude/agents/kit-planner.md" "$FH/.claude/agents/kit-planner.md"
[ "$(grep -c 'kept your own' "$FH/out")" -eq 1 ]
grep -qxF "[install] kept your own kit-planner.md in ${B[0]}" "$FH/out"
echo "test_install: PASS"
