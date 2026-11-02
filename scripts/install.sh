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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="$(cat "$REPO_ROOT/VERSION" 2>/dev/null || echo unknown)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"
# Keep in sync with .mcp.json / .mcp.json.template.
SERENA_REF="${SERENA_REF:-9b292a6c8b03c8306f117efeabb0ea7afdb0b3c0}"

KIT_SKILLS=(commit-conventions security-conventions dotnet-conventions deploy docs-writer expo ios)
KIT_AGENTS=(docs-writer.md)

log()  { printf '[install] %s\n' "$*"; }
warn() { printf '[install][warn] %s\n' "$*" >&2; }
die()  { printf '[install][error] %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
pipelinekit v$VERSION
Usage: bash scripts/install.sh [--no-serena] [--help]

Copies hooks, skills, agents and config into \$CLAUDE_HOME (default ~/.claude),
renders CLAUDE.md, merges hook wiring + attribution-off into settings.json
(dropping hook entries whose script no longer exists), installs and registers
the serena MCP server, then runs scripts/verify.sh.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --no-serena) CLAUDE_INSTALL_SKIP_SERENA=1 ;;
    *) usage >&2; die "unknown argument: $arg" ;;
  esac
done

command -v python3 >/dev/null || die "python3 is required"
log "pipelinekit v$VERSION -> $CLAUDE_HOME"
mkdir -p "$CLAUDE_HOME"/{hooks,skills,agents,config}

# ---------- files ----------
# Hooks: copy runtime files only (tests stay in the repo).
find "$REPO_ROOT/claude/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) \
  -exec cp -p {} "$CLAUDE_HOME/hooks/" \;
chmod +x "$CLAUDE_HOME"/hooks/*.sh "$CLAUDE_HOME"/hooks/*.py
for s in "${KIT_SKILLS[@]}"; do
  rm -rf "${CLAUDE_HOME:?}/skills/$s"
  cp -R "$REPO_ROOT/claude/skills/$s" "$CLAUDE_HOME/skills/$s"
done
find "$CLAUDE_HOME/skills" -name __pycache__ -type d -prune -exec rm -rf {} +
for a in "${KIT_AGENTS[@]}"; do cp -p "$REPO_ROOT/claude/agents/$a" "$CLAUDE_HOME/agents/$a"; done
cp -p "$REPO_ROOT/claude/config/never-stage.txt" "$CLAUDE_HOME/config/never-stage.txt"
log "copied ${#KIT_SKILLS[@]} skills, ${#KIT_AGENTS[@]} agent(s), hooks, config"

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
CLAUDE_HOME="$CLAUDE_HOME" python3 - "$SETTINGS" <<'PY'
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

KIT = {
    "PreToolUse": {
        "Bash": ["block-dangerous-commands.sh", "block-push-main.sh",
                 "block-stage-sensitive.sh", "env-scrub.py", "validate-commit-msg.sh"],
        "Edit|Write": ["pre-edit-protect.sh"],
        "Write": ["block-bare-repo-markers.py"],
    },
    "PostToolUse": {
        "Edit|Write": ["post-edit-format.sh"],
        "WebFetch|Read": ["scan-tool-output.sh"],
    },
}
# Helpers that live in hooks/ but are not hooks themselves.
NOT_HOOKS = {"denial_tracker.py", "_pathguard.py", "_promptguard.py", "_never_stage_match.py"}

prefixes = (hooks_dir + "/", "~/.claude/hooks/", "$HOME/.claude/hooks/", "${HOME}/.claude/hooks/")

def stale(cmd):
    first = (cmd or "").split()[0] if (cmd or "").split() else ""
    for p in prefixes:
        if first.startswith(p):
            name = first[len(p):]
            return name in NOT_HOOKS or not os.path.isfile(os.path.join(hooks_dir, name))
    return False

hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
removed = []
for event in list(hooks):
    groups = []
    for g in hooks[event] if isinstance(hooks[event], list) else []:
        kept = []
        for h in g.get("hooks", []):
            if stale(h.get("command")):
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
for event, by_matcher in KIT.items():
    groups = hooks.setdefault(event, [])
    present = {h.get("command") for g in groups for h in g.get("hooks", [])}
    for matcher, scripts in by_matcher.items():
        group = next((g for g in groups if g.get("matcher") == matcher), None)
        if group is None:
            group = {"matcher": matcher, "hooks": []}
            groups.append(group)
        for s in scripts:
            cmd = os.path.join(hooks_dir, s)
            if cmd not in present:
                group["hooks"].append({"type": "command", "command": cmd})
                added += 1
data["hooks"] = hooks
# No AI attribution in commits or PRs (empty strings work on all CLI versions).
data["attribution"] = {"commit": "", "pr": "", "sessionUrl": False}
data["includeCoAuthoredBy"] = False

tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, path)
print(f"[install] settings.json: +{added} kit hooks, -{len(removed)} stale hook entries, attribution off")
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

# ---------- git hooks for this repo ----------
if GIT_COMMON="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)"; then
  [[ "$GIT_COMMON" = /* ]] || GIT_COMMON="$REPO_ROOT/$GIT_COMMON"
  GHOOKS="$GIT_COMMON/hooks"
  mkdir -p "$GHOOKS"
  WRAPPER="$REPO_ROOT/claude/hooks/commit-msg-wrapper.sh"
  if [[ "$(readlink "$GHOOKS/commit-msg" 2>/dev/null)" != "$WRAPPER" ]]; then
    [[ -e "$GHOOKS/commit-msg" || -L "$GHOOKS/commit-msg" ]] && mv "$GHOOKS/commit-msg" "$GHOOKS/commit-msg.pre-pipelinekit.$TS"
    ln -sfn "$WRAPPER" "$GHOOKS/commit-msg"
  fi
  SENTINEL='# pipelinekit pre-commit dispatcher'
  if ! head -2 "$GHOOKS/pre-commit" 2>/dev/null | grep -qF "$SENTINEL"; then
    [[ -e "$GHOOKS/pre-commit" || -L "$GHOOKS/pre-commit" ]] && mv "$GHOOKS/pre-commit" "$GHOOKS/pre-commit.pre-pipelinekit.$TS"
  fi
  cat > "$GHOOKS/pre-commit" <<EOF
#!/usr/bin/env bash
$SENTINEL
SCANNER="$REPO_ROOT/claude/hooks/scan-secrets-staged.sh"
[[ -f "\$SCANNER" ]] && exec bash "\$SCANNER"
exit 0
EOF
  chmod +x "$GHOOKS/pre-commit"
  log "repo git hooks: commit-msg + pre-commit installed"
fi

# ---------- verify ----------
CLAUDE_HOME="$CLAUDE_HOME" bash "$REPO_ROOT/scripts/verify.sh"
