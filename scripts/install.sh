#!/usr/bin/env bash
# pipelinekit installer. Overlays claude/ into $CLAUDE_HOME in place.
# Idempotent: re-run to update. Never moves or deletes $CLAUDE_HOME and never
# touches projects/, sessions/, jobs/, plugins/, todos/ or credentials.
#
# Env:
#   CLAUDE_HOME     target dir (default: $HOME/.claude)
#   USER_NAME       identity for CLAUDE.md (default: git config user.name, else the login name)
#   USER_EMAIL      identity for CLAUDE.md (default: git config user.email)
#   SERENA_REF      serena commit to install (default: pinned SHA below)
#   SERENA_ALLOW_ROLLING=1  allow SERENA_REF=main
#   CLAUDE_INSTALL_SKIP_SERENA=1  skip serena install/registration
#   PIPELINEKIT_GIT_HOOKS=1|0  set (or skip) the global core.hooksPath without asking

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="$(cat "$REPO_ROOT/VERSION" 2>/dev/null || echo unknown)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"
# serena 2.1.0. Keep in sync with .mcp.json / .mcp.json.template.
SERENA_REF="${SERENA_REF:-5e4f5cd173c7ff3eed37ee3f1de6c266b937c5dc}"

KIT_SKILLS=(dotnet-conventions deploy exchange-api-keys docs-writer frontend-design mobile kit ship judge-loop)
KIT_AGENTS=(kit-planner.md kit-builder.md kit-judge.md)
# The skill files that run as programs; no other installed skill file is executable.
KIT_SKILL_SCRIPTS=(kit/check.py kit/update.py ship/ship.py judge-loop/loop.py)
# Shipped by earlier versions. Removed on upgrade only if unmodified (see kit_file).
RETIRED_SKILLS=(commit-conventions security-conventions expo ios)
RETIRED_HOOKS=(block-dangerous-commands.sh block-push-main.sh block-stage-sensitive.sh env-scrub.py
  validate-commit-msg.sh pre-edit-protect.sh scan-tool-output.sh commit-msg-wrapper.sh
  scan-secrets-staged.sh _pathguard.py _promptguard.py _never_stage_match.py denial_tracker.py __init__.py)
RETIRED_AGENTS=(docs-writer.md)

log()  { printf '[install] %s\n' "$*"; }
warn() { printf '[install][warn] %s\n' "$*" >&2; }
die()  { printf '[install][error] %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
pipelinekit v$VERSION
Usage: bash scripts/install.sh [--no-serena] [--git-hooks|--no-git-hooks] [--help]

Copies hooks, git hooks, skills, the agents kit-planner, kit-builder and
kit-judge, and config into \$CLAUDE_HOME (default ~/.claude),
keeps files of your own found in the kit's skill folders in a backup,
removes unmodified files that older kit versions installed, renders CLAUDE.md,
merges hook wiring, permissions (deny/ask) and attribution-off into
settings.json (backing it up first), installs global git hooks (asks first),
installs and registers the serena MCP server, records what it installed in
\$CLAUDE_HOME/pipelinekit/manifest.json, then runs scripts/verify.sh.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --no-serena) CLAUDE_INSTALL_SKIP_SERENA=1 ;;
    --git-hooks) PIPELINEKIT_GIT_HOOKS=1 ;;
    --no-git-hooks) PIPELINEKIT_GIT_HOOKS=0 ;;
    *) usage >&2; die "unknown argument: $arg" ;;
  esac
done

# The hooks are POSIX scripts started through their shebang; Windows cannot run them.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    die "native Windows shells are not supported. Install inside WSL and run Claude Code there (Claude Code Desktop: pick the WSL environment). See docs-source/installation.md" ;;
esac
command -v python3 >/dev/null || die "python3 is required"
log "pipelinekit v$VERSION -> $CLAUDE_HOME"

# kit_file <installed file> <repo path>: true if the installed file is
# byte-identical to a committed version of <repo path>, i.e. this kit put it
# there and nobody edited it. Needs git history; without it nothing is removed.
kit_file() {
  local h
  [[ -f "$1" ]] || return 1
  h="$(git -C "$REPO_ROOT" hash-object "$1" 2>/dev/null)" || return 1
  git -C "$REPO_ROOT" rev-list --all --objects -- "$2" 2>/dev/null | grep -qxF "$h $2"
}

# ---------- your own files in the kit's places ----------
# Everything of yours that a kit file would replace goes to a backup first, and
# only then is any kit file copied: an install that stops here has made those
# backups and changed nothing else, and it removes the backup folders it made
# and left empty.
BACKUPS="$CLAUDE_HOME/pipelinekit/backup"
made_pk=0 made_bk=0
[[ -e "$CLAUDE_HOME/pipelinekit" || -L "$CLAUDE_HOME/pipelinekit" ]] || made_pk=1
[[ -e "$BACKUPS" || -L "$BACKUPS" ]] || made_bk=1
undo_new_dirs() {
  [[ "$made_bk" == 0 ]] || rmdir "$BACKUPS" 2>/dev/null || true
  [[ "$made_pk" == 0 ]] || rmdir "$CLAUDE_HOME/pipelinekit" 2>/dev/null || true
}
stop() { undo_new_dirs; die "$1"; }

# frontend-design is a public skill name, so a user may already have a folder of
# that name; the kit owns it from now on. A link is removed (never followed); a
# folder the kit did not install and that differs from the kit's is moved to a
# backup once, and so is anything else of that name (a file is never the kit's).
# A missing or damaged manifest counts as "not installed by the kit".
FD="$CLAUDE_HOME/skills/frontend-design"
listed=0
if python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); s=m.get("skills"); sys.exit(0 if isinstance(s,list) and "frontend-design" in s else 1)' "$CLAUDE_HOME/pipelinekit/manifest.json" 2>/dev/null; then
  listed=1
fi
if [[ -L "$FD" ]]; then
  target="$(readlink "$FD" || true)"
  rm -f "$FD"
  log "removed the link skills/frontend-design -> $target"
elif [[ -e "$FD" ]] && { [[ ! -d "$FD" ]] || { [[ "$listed" == 0 ]] &&
  ! diff -rq "$FD" "$REPO_ROOT/claude/skills/frontend-design" >/dev/null 2>&1; }; }; then
  FD_BACKUP="$BACKUPS/skills-frontend-design-$(date -u +%Y%m%dT%H%M%SZ)"
  # A read-only folder or a file named backup: one line of ours, not mkdir's or mv's.
  { mkdir -p "$BACKUPS" && mv "$FD" "$FD_BACKUP"; } 2>/dev/null ||
    stop "could not move your own skills/frontend-design to $BACKUPS. It is untouched and nothing of the kit was copied. Move or rename it yourself, then run the installer again."
  log "kept your own frontend-design skill in $FD_BACKUP"
fi
# Files of your own inside a kit skill folder: each folder is replaced as a
# whole below, so every file the kit did not put there (not in the checkout's
# skill, not listed by the last install's manifest) is copied to a backup first,
# one folder per skill, and named. The kit's own files go without a backup: an
# edited copy, an older install's tests/, caches. A link is kept as a link, and
# a file in place of a skill folder is kept as it is. All skills are looked at
# before any is replaced, so a copy that fails leaves every skill as it was.
python3 - "$REPO_ROOT/claude" "$CLAUDE_HOME" "$TS" "${KIT_SKILLS[@]}" <<'PY' || { undo_new_dirs; exit 1; }
import json, os, shutil, sys

src, home, ts, skills = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
CACHES = {"__pycache__", ".pytest_cache", ".ruff_cache"}
backups = os.path.join(home, "pipelinekit", "backup")
try:
    with open(os.path.join(home, "pipelinekit", "manifest.json"), encoding="utf-8") as f:
        listed = json.load(f).get("files")
except (OSError, ValueError, AttributeError):
    listed = None
listed = set(listed) if isinstance(listed, dict) else set()


def fail(skill):
    sys.exit(
        f"[install][error] could not copy your own files in skills/{skill} to {backups}. "
        "They are untouched and nothing of the kit was copied. "
        "Move them out of the folder yourself, then run the installer again."
    )


def raise_(err):
    raise err


def own(skill):
    """The user's files in the installed skill, relative to it ("" for the skill itself)."""
    top = os.path.join(home, "skills", skill)
    if os.path.islink(top) or not os.path.lexists(top):
        return []  # a link goes without its target being touched
    if not os.path.isdir(top):
        return [""]
    kit = set(listed)
    for root, _, files in os.walk(os.path.join(src, "skills", skill)):
        kit.update(os.path.relpath(os.path.join(root, n), src) for n in files)
    found = []
    for root, dirs, files in os.walk(top, onerror=raise_):
        links = [d for d in dirs if os.path.islink(os.path.join(root, d))]
        dirs[:] = sorted(d for d in dirs if d not in CACHES and d not in links)
        for n in files + links:
            p = os.path.join(root, n)
            if n.endswith(".pyc") or os.path.relpath(p, home) in kit:
                continue
            if os.path.islink(p) or os.path.isfile(p):
                found.append(os.path.relpath(p, top))
    return sorted(found)


def shown(rel):
    return "".join(c if c.isprintable() else "?" for c in rel)


for skill in skills:
    top = os.path.join(home, "skills", skill)
    dst = None
    try:
        rels = own(skill)
        if not rels:
            continue
        dst = base = os.path.join(backups, f"skills-{skill}-{ts}")
        n = 1
        while os.path.lexists(dst):
            n += 1
            dst = f"{base}-{n}"
        os.makedirs(backups, exist_ok=True)
        if rels == [""]:
            shutil.copy2(top, dst)
            print(f"[install] kept your own file skills/{skill} in {dst}")
            continue
        for rel in rels:
            s, d = os.path.join(top, rel), os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.islink(s):
                os.symlink(os.readlink(s), d)
            else:
                shutil.copy2(s, d)
    except OSError:
        # A partial copy goes; the user's files are still in place.
        if dst and os.path.isdir(dst) and not os.path.islink(dst):
            shutil.rmtree(dst, ignore_errors=True)
        elif dst and os.path.lexists(dst):
            try:
                os.remove(dst)
            except OSError:
                pass
        fail(skill)
    count = f"{len(rels)} file" + ("" if len(rels) == 1 else "s")
    print(f"[install] kept {count} of your own from skills/{skill} in {dst}")
    for rel in rels[:10]:
        print(f"[install]   {shown(rel)}")
    if len(rels) > 10:
        print(f"[install]   and {len(rels) - 10} more")
PY
# agents/ is the user's folder too: only the kit's three files are touched. A
# link is removed when the kit's files are copied (never followed). A file the
# last install did not list in its manifest and that differs from the kit's is
# moved to a backup once, and so is anything else of that name. A missing or
# damaged manifest lists nothing.
listed_files="$(python3 -c 'import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
f = m.get("files") if isinstance(m, dict) else None
for k in f if isinstance(f, dict) else ():
    if "\n" not in k and "\r" not in k:
        print(k)' "$CLAUDE_HOME/pipelinekit/manifest.json" 2>/dev/null)" || listed_files=""
for a in "${KIT_AGENTS[@]}"; do
  dst="$CLAUDE_HOME/agents/$a"
  if [[ ! -L "$dst" && -e "$dst" ]] && { [[ ! -f "$dst" ]] || { ! cmp -s "$dst" "$REPO_ROOT/claude/agents/$a" &&
    ! grep -qxF "agents/$a" <<<"$listed_files"; }; }; then
    backup="$BACKUPS/agents-$a-$TS"
    # A read-only folder or a file named backup: one line of ours, not mkdir's or mv's.
    { mkdir -p "$BACKUPS" && mv "$dst" "$backup"; } 2>/dev/null ||
      stop "could not move your own agents/$a to $BACKUPS. It is untouched and nothing of the kit was copied. Move or rename it yourself, then run the installer again."
    log "kept your own $a in $backup"
  fi
done

# ---------- files ----------
mkdir -p "$CLAUDE_HOME"/{hooks,git-hooks,skills,agents,config}
# Hooks: copy runtime files only (tests stay in the repo).
find "$REPO_ROOT/claude/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) \
  -exec cp -p {} "$CLAUDE_HOME/hooks/" \;
chmod +x "$CLAUDE_HOME"/hooks/*.sh "$CLAUDE_HOME"/hooks/*.py
cp -p "$REPO_ROOT"/claude/git-hooks/* "$CLAUDE_HOME/git-hooks/"
chmod +x "$CLAUDE_HOME"/git-hooks/*
# Skill tests stay in the repo, as the hook tests do. A checkout on a Windows
# drive (WSL) marks every file executable, so the modes are set here.
for s in "${KIT_SKILLS[@]}"; do
  rm -rf "${CLAUDE_HOME:?}/skills/$s"
  cp -R "$REPO_ROOT/claude/skills/$s" "$CLAUDE_HOME/skills/$s"
  find "$CLAUDE_HOME/skills/$s" -name tests -type d -prune -exec rm -rf {} +
  find "$CLAUDE_HOME/skills/$s" -type f -exec chmod a-x {} +
done
find "$CLAUDE_HOME/skills" -name __pycache__ -type d -prune -exec rm -rf {} +
for f in "${KIT_SKILL_SCRIPTS[@]}"; do
  chmod +x "$CLAUDE_HOME/skills/$f"
done
# judge-loop in another home: the skill names its helper as ~/.claude/...;
# from another home that path is wrong, so the installed copy names this home
# instead, right after the copy (an install that stops later still leaves a
# skill that names its home) and before the manifest hashes it. Only an
# absolute path that a permission pattern can hold is written in.
if [[ "$CLAUDE_HOME" != "$HOME/.claude" ]]; then
  if [[ "$CLAUDE_HOME" =~ ^/[A-Za-z0-9._/@+-]+$ ]]; then
    python3 - "$CLAUDE_HOME/skills/judge-loop/SKILL.md" "$CLAUDE_HOME" <<'PY'
import sys
path, home = sys.argv[1], sys.argv[2].rstrip("/")
with open(path, encoding="utf-8") as f:
    s = f.read()
with open(path, "w", encoding="utf-8") as f:
    f.write(s.replace("~/.claude/", home + "/"))
PY
  else
    warn "judge-loop: CLAUDE_HOME is not an absolute path a permission pattern can hold; the skill still names ~/.claude and will not find loop.py from this home: install into an absolute path of letters, digits and ._/@+-"
  fi
fi
for a in "${KIT_AGENTS[@]}"; do
  dst="$CLAUDE_HOME/agents/$a"
  if [[ -L "$dst" ]]; then
    log "removed the link agents/$a (its target is untouched)"
  fi
  rm -f "$dst"
  cp "$REPO_ROOT/claude/agents/$a" "$dst"
done
cp -p "$REPO_ROOT/claude/config/never-stage.txt" "$CLAUDE_HOME/config/never-stage.txt"
log "copied ${#KIT_SKILLS[@]} skills, ${#KIT_AGENTS[@]} agents, hooks, git hooks, config"

# Files from older kit versions: remove the ones we installed, keep edited ones.
retire() { # retire <installed file> <repo path> <rm args...>
  local dst=$1 src=$2; shift 2
  if kit_file "$dst" "$src"; then
    rm "$@" && log "removed retired $src"
  else
    warn "kept $dst: not an unmodified kit copy; delete it yourself if unused"
  fi
}
for s in "${RETIRED_SKILLS[@]}"; do
  [[ -e "$CLAUDE_HOME/skills/$s" ]] || continue
  retire "$CLAUDE_HOME/skills/$s/SKILL.md" "claude/skills/$s/SKILL.md" -rf "${CLAUDE_HOME:?}/skills/$s"
done
for h in "${RETIRED_HOOKS[@]}"; do
  [[ -e "$CLAUDE_HOME/hooks/$h" ]] || continue
  retire "$CLAUDE_HOME/hooks/$h" "claude/hooks/$h" -f "$CLAUDE_HOME/hooks/$h"
done
rm -rf "${CLAUDE_HOME:?}/hooks/__pycache__"
for a in "${RETIRED_AGENTS[@]}"; do
  [[ -e "$CLAUDE_HOME/agents/$a" ]] || continue
  retire "$CLAUDE_HOME/agents/$a" "claude/agents/$a" -f "$CLAUDE_HOME/agents/$a"
done

# ---------- CLAUDE.md ----------
# Containers and cron jobs often have no USER and no git identity: fall back
# to the login name, and go on without one rather than stop half-way.
USER_NAME="${USER_NAME:-$(git config --global user.name 2>/dev/null || echo "${USER:-$(id -un 2>/dev/null || true)}")}"
[[ -n "$USER_NAME" ]] ||
  warn "no name for CLAUDE.md: set USER_NAME or git config --global user.name, then run the installer again"
USER_EMAIL="${USER_EMAIL:-$(git config --global user.email 2>/dev/null || echo "")}"
RENDERED="$(mktemp)"
CLAUDE_HOME="$CLAUDE_HOME" USER_NAME="$USER_NAME" USER_EMAIL="$USER_EMAIL" python3 - \
  "$REPO_ROOT/claude/CLAUDE.md.template" "$RENDERED" <<'PY'
import os, sys
s = open(sys.argv[1], encoding="utf-8").read()
for k in ("CLAUDE_HOME", "USER_NAME", "USER_EMAIL"):
    s = s.replace("${%s}" % k, os.environ[k])
open(sys.argv[2], "w", encoding="utf-8").write(s)
PY
if [[ -f "$CLAUDE_HOME/CLAUDE.md" ]] && ! cmp -s "$RENDERED" "$CLAUDE_HOME/CLAUDE.md"; then
  cp -p "$CLAUDE_HOME/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md.bak-$TS"
  log "backed up CLAUDE.md -> CLAUDE.md.bak-$TS"
  # A judge-loop switch line in the replaced file is lost: name it and the backup.
  python3 - "$CLAUDE_HOME/CLAUDE.md" <<'PY' |
import re, sys
keys = {"judge loop": "Judge loop:", "judge rounds": "Judge rounds:", "judges": "Judges:"}
pat = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(judge loop|judge rounds|judges)\s*:", re.I)
seen = []
for line in open(sys.argv[1], encoding="utf-8-sig", errors="replace"):
    m = pat.match(line)
    if m and keys[m.group(1).lower()] not in seen:
        seen.append(keys[m.group(1).lower()])
print("\n".join(seen))
PY
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    warn "your CLAUDE.md had the line '$key'; it is in $CLAUDE_HOME/CLAUDE.md.bak-$TS: add it again, or put it in the project's CLAUDE.md"
  done
fi
mv "$RENDERED" "$CLAUDE_HOME/CLAUDE.md"
chmod 644 "$CLAUDE_HOME/CLAUDE.md"

# ---------- settings.json ----------
SETTINGS="$CLAUDE_HOME/settings.json"
[[ -f "$SETTINGS" ]] && cp -p "$SETTINGS" "$SETTINGS.bak-$TS"
CLAUDE_HOME="$CLAUDE_HOME" python3 - "$SETTINGS" "$REPO_ROOT/claude/config/settings.template.json" \
  "$REPO_ROOT/claude/skills/kit" <<'PY'
import json, os, sys

sys.dont_write_bytecode = True  # no __pycache__ left in the checkout
sys.path.insert(0, sys.argv[3])
from check import hook_program, home_rule  # as the self-check reads hooks and rules

path = sys.argv[1]
home = os.environ["CLAUDE_HOME"]
hooks_dir = os.path.join(home, "hooks")
if os.path.exists(path):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"[install][error] {path} is not valid JSON ({exc}); fix it and re-run")
else:
    data = {}
if not isinstance(data, dict):
    sys.exit(f"[install][error] {path} is not a JSON object")

# Hook commands use ${CLAUDE_HOME}; path rules name ~/.claude/..., turned into this home below.
tmpl = json.loads(open(sys.argv[2], encoding="utf-8").read().replace("${CLAUDE_HOME}", home))
KIT_SCRIPTS = {os.path.basename(h["command"]) for gs in tmpl["hooks"].values() for g in gs for h in g["hooks"]}
# Hooks and helpers that earlier kit versions wired into settings.json.
REMOVED = {"block-dangerous-commands.sh", "block-push-main.sh", "block-stage-sensitive.sh", "env-scrub.py",
           "validate-commit-msg.sh", "pre-edit-protect.sh", "scan-tool-output.sh", "denial_tracker.py",
           "_pathguard.py", "_promptguard.py", "_never_stage_match.py"}

prefixes = (hooks_dir + "/", "~/.claude/hooks/", "$HOME/.claude/hooks/", "${HOME}/.claude/hooks/")

def script(h):
    first = hook_program(h)
    return next((first[len(p):] for p in prefixes if first.startswith(p)), None)

hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
removed = []
for event in list(hooks):
    groups = []
    for g in hooks[event] if isinstance(hooks[event], list) else []:
        kept = []
        for h in g.get("hooks", []) if isinstance(g, dict) else []:
            name = script(h)
            if name is None:
                kept.append(h)
            elif name in KIT_SCRIPTS:
                pass  # re-added from the template below
            elif name in REMOVED or not os.path.isfile(os.path.join(hooks_dir, name)):
                removed.append(h.get("command"))
            else:
                kept.append(h)
        if kept:
            groups.append({**g, "hooks": kept})
    if groups:
        hooks[event] = groups
    else:
        del hooks[event]

added = 0
for event, groups in tmpl["hooks"].items():
    hooks.setdefault(event, []).extend(groups)
    added += sum(len(g["hooks"]) for g in groups)
data["hooks"] = hooks

# Permissions: keep the user's rules and append the kit's in template order
# ("!" carve-outs must follow the rule they carve from). allow etc. untouched.
# Path rules name this home; in another home, the rules an earlier install
# wrote for ~/.claude/ guard the wrong folder and are replaced.
perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
replaced = []
for kind in ("deny", "ask"):
    mine = [home_rule(r, home) for r in tmpl["permissions"][kind]]
    stale = set(tmpl["permissions"][kind]) - set(mine)
    theirs = perms.get(kind) if isinstance(perms.get(kind), list) else []
    replaced += [r for r in theirs if r in stale]
    perms[kind] = [r for r in theirs if r not in mine and r not in stale] + mine
data["permissions"] = perms
env = data.get("env") if isinstance(data.get("env"), dict) else {}
env.update(tmpl.get("env", {}))
env.pop("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", None)  # forces default permission mode
data["env"] = env
# No AI attribution in commits or PRs (empty strings work on all CLI versions).
data["attribution"] = tmpl["attribution"]
data.pop("includeCoAuthoredBy", None)  # deprecated; attribution covers it

tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, path)
print(f"[install] settings.json: {added} kit hooks, -{len(removed)} stale hook entries, "
      f"{len(tmpl['permissions']['deny'])} deny + {len(tmpl['permissions']['ask'])} ask rules, "
      "attribution off")
for c in removed:
    print(f"[install]   removed: {c}")
for r in replaced:
    print(f"[install]   replaced: {r}")
PY

# ---------- serena MCP ----------
if [[ "${CLAUDE_INSTALL_SKIP_SERENA:-0}" == "1" ]]; then
  log "serena: skipped"
else
  if [[ "$SERENA_REF" == "main" && "${SERENA_ALLOW_ROLLING:-0}" != "1" ]]; then
    die "SERENA_REF=main is a rolling ref; pin a commit SHA or set SERENA_ALLOW_ROLLING=1"
  fi
  SERENA_SRC="git+https://github.com/oraios/serena@${SERENA_REF}"
  # serena_version: the version the serena on PATH names, empty if it names none.
  serena_version() { serena --version 2>/dev/null | sed -n 's/^Serena \([0-9][0-9.]*[^ ]*\).*/\1/p' | head -n 1 || true; }
  # serena 1.x stops on a .serena/project.yml that serena 2 wrote, and has no
  # --agent-interface; the kit's registration needs serena 2.
  serena_2() { [[ "$1" =~ ^[0-9]+\. ]] && (( 10#${1%%.*} >= 2 )); }
  if ! command -v serena >/dev/null 2>&1; then
    if command -v uv >/dev/null 2>&1; then
      log "installing serena @ $SERENA_REF"
      uv tool install --quiet "$SERENA_SRC" || warn "serena install failed"
    else
      warn "serena: uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh); skipping"
    fi
  else
    have="$(serena_version)"
    if [[ -n "$have" ]] && ! serena_2 "$have"; then
      if command -v uv >/dev/null 2>&1; then
        log "serena $have cannot read the .serena/project.yml files that serena 2 writes; upgrading to $SERENA_REF"
        log "serena 2 rewrites each registered project's .serena/project.yml on its first start; serena 1.x cannot read them afterwards"
        uv tool install --force --quiet "$SERENA_SRC" || warn "serena upgrade failed"
      else
        warn "serena $have cannot read the .serena/project.yml files that serena 2 writes; upgrade it: uv tool install --force $SERENA_SRC"
      fi
    fi
  fi
  if command -v serena >/dev/null 2>&1; then
    have="$(serena_version)"
    # The tools interface: one MCP tool per operation, as before serena 2. Its
    # default for a new config, REPL, runs Python inside the server, out of
    # reach of bash-guard.py and the sandbox.
    SERENA_ARGS=(start-mcp-server --context claude-code --project-from-cwd)
    if [[ -z "$have" ]]; then
      warn "could not read the version of $(command -v serena); registering it without --agent-interface tools. Upgrade it (uv tool install --force $SERENA_SRC) and run the installer again"
    elif serena_2 "$have"; then
      SERENA_ARGS+=(--agent-interface tools)
    else
      warn "serena $have is older than 2: registering it without --agent-interface tools. Upgrade it and run the installer again"
    fi
    CJ="$HOME/.claude.json"
    [[ -f "$CJ" ]] && cp -p "$CJ" "$CJ.bak-$TS"
    python3 - "$CJ" "${SERENA_ARGS[@]}" <<'PY'
import json, os, sys
p = sys.argv[1]
try:
    data = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
except json.JSONDecodeError as exc:
    sys.exit(f"[install][warn] {p} is not valid JSON ({exc}); serena not registered")
if not isinstance(data, dict) or not isinstance(data.setdefault("mcpServers", {}), dict):
    sys.exit(f"[install][warn] unexpected shape in {p}; serena not registered")
data["mcpServers"]["serena"] = {
    "type": "stdio",
    "command": "serena",
    "args": sys.argv[2:],
}
tmp = p + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, p)
PY
    log "serena registered in ~/.claude.json (user scope)"
  fi
fi

# ---------- global git hooks ----------
GH="$CLAUDE_HOME/git-hooks"
CUR="$(git config --global --get core.hooksPath || true)"
if [[ "$CUR" == "$GH" ]]; then
  log "git: core.hooksPath already $GH"
elif [[ -n "$CUR" ]]; then
  warn "git: global core.hooksPath is $CUR; left alone. To use the kit hooks: git config --global core.hooksPath $GH"
else
  ans="${PIPELINEKIT_GIT_HOOKS:-}"
  if [[ -z "$ans" && -t 0 ]]; then
    read -r -p "[install] Set global git core.hooksPath to $GH (commit-msg, pre-commit gitleaks, pre-push main guard)? [y/N] " ans
  fi
  if [[ "$ans" =~ ^(1|y|Y|yes)$ ]]; then
    git config --global core.hooksPath "$GH" && log "git: core.hooksPath -> $GH"
  else
    log "git: global hooks not enabled (enable later: git config --global core.hooksPath $GH)"
  fi
fi
# A repo with its own local core.hooksPath (husky, pre-commit, ...) overrides the global one.
command -v gitleaks >/dev/null || warn "gitleaks not installed: pre-commit will warn and allow"
# Old per-repo install of this kit: remove the dangling commit-msg symlink and the dispatcher.
if GIT_COMMON="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)"; then
  [[ "$GIT_COMMON" = /* ]] || GIT_COMMON="$REPO_ROOT/$GIT_COMMON"
  if [[ "$(readlink "$GIT_COMMON/hooks/commit-msg" 2>/dev/null)" == *commit-msg-wrapper.sh ]]; then
    rm -f "$GIT_COMMON/hooks/commit-msg"
  fi
  if head -2 "$GIT_COMMON/hooks/pre-commit" 2>/dev/null | grep -qF '# pipelinekit pre-commit dispatcher'; then
    rm -f "$GIT_COMMON/hooks/pre-commit"
  fi
fi

# ---------- manifest ----------
# What this install consists of; scripts/verify.sh and the /kit command compare
# the live files and settings against it. Written last so it records the final state.
CLAUDE_HOME="$CLAUDE_HOME" CLAUDE_INSTALL_SKIP_SERENA="${CLAUDE_INSTALL_SKIP_SERENA:-0}" \
  python3 "$REPO_ROOT/claude/skills/kit/check.py" --write-manifest "$REPO_ROOT"
log "manifest: $CLAUDE_HOME/pipelinekit/manifest.json"

# ---------- verify ----------
CLAUDE_HOME="$CLAUDE_HOME" bash "$REPO_ROOT/scripts/verify.sh"
log "start a new session to load the agents (kit-planner, kit-builder, kit-judge)"
