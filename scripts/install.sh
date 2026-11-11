#!/usr/bin/env bash
# pipelinekit installer. Overlays claude/ into $CLAUDE_HOME in place.
# Idempotent: re-run to update. Never moves or deletes $CLAUDE_HOME and never
# touches projects/, sessions/, jobs/, plugins/, todos/ or credentials.
#
# Env:
#   CLAUDE_HOME     target dir (default: $HOME/.claude)
#   USER_NAME       identity for CLAUDE.md (default: git config user.name)
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
# Keep in sync with .mcp.json / .mcp.json.template.
SERENA_REF="${SERENA_REF:-9b292a6c8b03c8306f117efeabb0ea7afdb0b3c0}"

KIT_SKILLS=(dotnet-conventions deploy exchange-api-keys docs-writer frontend-design mobile kit ship)
KIT_AGENTS=(kit-planner.md kit-builder.md kit-judge.md)
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
mkdir -p "$CLAUDE_HOME"/{hooks,git-hooks,skills,agents,config}

# kit_file <installed file> <repo path>: true if the installed file is
# byte-identical to a committed version of <repo path>, i.e. this kit put it
# there and nobody edited it. Needs git history; without it nothing is removed.
kit_file() {
  local h
  [[ -f "$1" ]] || return 1
  h="$(git -C "$REPO_ROOT" hash-object "$1" 2>/dev/null)" || return 1
  git -C "$REPO_ROOT" rev-list --all --objects -- "$2" 2>/dev/null | grep -qxF "$h $2"
}

# ---------- files ----------
# Hooks: copy runtime files only (tests stay in the repo).
find "$REPO_ROOT/claude/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) \
  -exec cp -p {} "$CLAUDE_HOME/hooks/" \;
chmod +x "$CLAUDE_HOME"/hooks/*.sh "$CLAUDE_HOME"/hooks/*.py
cp -p "$REPO_ROOT"/claude/git-hooks/* "$CLAUDE_HOME/git-hooks/"
chmod +x "$CLAUDE_HOME"/git-hooks/*
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
  FD_BACKUPS="$CLAUDE_HOME/pipelinekit/backup"
  FD_BACKUP="$FD_BACKUPS/skills-frontend-design-$(date -u +%Y%m%dT%H%M%SZ)"
  # A read-only folder or a file named backup: one line of ours, not mkdir's or mv's.
  { mkdir -p "$FD_BACKUPS" && mv "$FD" "$FD_BACKUP"; } 2>/dev/null ||
    die "could not move your own skills/frontend-design to $FD_BACKUPS. It is untouched and the skills were not installed. Move or rename it yourself, then run the installer again."
  log "kept your own frontend-design skill in $FD_BACKUP"
fi
for s in "${KIT_SKILLS[@]}"; do
  rm -rf "${CLAUDE_HOME:?}/skills/$s"
  cp -R "$REPO_ROOT/claude/skills/$s" "$CLAUDE_HOME/skills/$s"
done
find "$CLAUDE_HOME/skills" -name __pycache__ -type d -prune -exec rm -rf {} +
chmod +x "$CLAUDE_HOME/skills/kit/check.py" "$CLAUDE_HOME/skills/ship/ship.py"
# agents/ is the user's folder too: only the kit's three files are touched. A
# link is removed (never followed). A file the last install did not list in its
# manifest and that differs from the kit's is moved to a backup once, and so is
# anything else of that name. A missing or damaged manifest lists nothing.
listed_files="$(python3 -c 'import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
f = m.get("files") if isinstance(m, dict) else None
for k in f if isinstance(f, dict) else ():
    if "\n" not in k and "\r" not in k:
        print(k)' "$CLAUDE_HOME/pipelinekit/manifest.json" 2>/dev/null)" || listed_files=""
for a in "${KIT_AGENTS[@]}"; do
  dst="$CLAUDE_HOME/agents/$a"
  if [[ -L "$dst" ]]; then
    rm -f "$dst"
    log "removed the link agents/$a"
  elif [[ -e "$dst" ]] && { [[ ! -f "$dst" ]] || { ! cmp -s "$dst" "$REPO_ROOT/claude/agents/$a" &&
    ! grep -qxF "agents/$a" <<<"$listed_files"; }; }; then
    backup="$CLAUDE_HOME/pipelinekit/backup/agents-$a-$TS"
    mkdir -p "$CLAUDE_HOME/pipelinekit/backup"
    mv "$dst" "$backup"
    log "kept your own $a in $backup"
  fi
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
USER_NAME="${USER_NAME:-$(git config --global user.name 2>/dev/null || echo "$USER")}"
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
fi
mv "$RENDERED" "$CLAUDE_HOME/CLAUDE.md"
chmod 644 "$CLAUDE_HOME/CLAUDE.md"

# ---------- settings.json ----------
SETTINGS="$CLAUDE_HOME/settings.json"
[[ -f "$SETTINGS" ]] && cp -p "$SETTINGS" "$SETTINGS.bak-$TS"
CLAUDE_HOME="$CLAUDE_HOME" python3 - "$SETTINGS" "$REPO_ROOT/claude/config/settings.template.json" <<'PY'
import json, os, sys

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

# Hook commands use ${CLAUDE_HOME}; permission rules keep a literal ~/.claude/...
tmpl = json.loads(open(sys.argv[2], encoding="utf-8").read().replace("${CLAUDE_HOME}", home))
KIT_SCRIPTS = {os.path.basename(h["command"]) for gs in tmpl["hooks"].values() for g in gs for h in g["hooks"]}
# Hooks and helpers that earlier kit versions wired into settings.json.
REMOVED = {"block-dangerous-commands.sh", "block-push-main.sh", "block-stage-sensitive.sh", "env-scrub.py",
           "validate-commit-msg.sh", "pre-edit-protect.sh", "scan-tool-output.sh", "denial_tracker.py",
           "_pathguard.py", "_promptguard.py", "_never_stage_match.py"}

prefixes = (hooks_dir + "/", "~/.claude/hooks/", "$HOME/.claude/hooks/", "${HOME}/.claude/hooks/")

def script(cmd):
    words = (cmd or "").split()
    first = words[0] if words else ""
    return next((first[len(p):] for p in prefixes if first.startswith(p)), None)

hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
removed = []
for event in list(hooks):
    groups = []
    for g in hooks[event] if isinstance(hooks[event], list) else []:
        kept = []
        for h in g.get("hooks", []) if isinstance(g, dict) else []:
            name = script(h.get("command"))
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
perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
for kind in ("deny", "ask"):
    mine = tmpl["permissions"][kind]
    theirs = perms.get(kind) if isinstance(perms.get(kind), list) else []
    perms[kind] = [r for r in theirs if r not in mine] + mine
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
PY

# ---------- serena MCP ----------
if [[ "${CLAUDE_INSTALL_SKIP_SERENA:-0}" == "1" ]]; then
  log "serena: skipped"
else
  if [[ "$SERENA_REF" == "main" && "${SERENA_ALLOW_ROLLING:-0}" != "1" ]]; then
    die "SERENA_REF=main is a rolling ref; pin a commit SHA or set SERENA_ALLOW_ROLLING=1"
  fi
  if ! command -v serena >/dev/null 2>&1; then
    if command -v uv >/dev/null 2>&1; then
      log "installing serena @ $SERENA_REF"
      uv tool install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" || warn "serena install failed"
    else
      warn "serena: uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh); skipping"
    fi
  fi
  if command -v serena >/dev/null 2>&1; then
    CJ="$HOME/.claude.json"
    [[ -f "$CJ" ]] && cp -p "$CJ" "$CJ.bak-$TS"
    python3 - "$CJ" <<'PY'
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
    "args": ["start-mcp-server", "--context", "claude-code", "--project-from-cwd"],
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
