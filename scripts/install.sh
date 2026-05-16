#!/usr/bin/env bash
# pipelinekit installer.
# Idempotent. Re-run to update. Supports interactive and non-interactive modes.
#
# Env:
#   CLAUDE_HOME                 Target overlay dir (default: $HOME/.claude)
#   CLAUDE_INSTALL_NONINTERACTIVE=1   Skip all prompts; assume sane defaults
#   CLAUDE_INSTALL_OPTIONALS    Comma list: tresor,lsp,mcp,gstack,claude-skills,serena
#                               Default interactive prompt; non-interactive default: tresor,lsp,mcp

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
if [[ "$CLAUDE_HOME" == *'${containerEnv:HOME}'* ]]; then
  CLAUDE_HOME="${CLAUDE_HOME//\$\{containerEnv:HOME\}/$HOME}"
fi
TS="$(date +%Y%m%d-%H%M%S)"
LOG="${CLAUDE_INSTALL_LOG:-$HOME/.cache/pipelinekit-install.log}"
mkdir -p "$(dirname "$LOG")"

# Supply-chain refs. Override via env vars before running install.
# Default = `main` (rolling); CI/prod use should pin to a commit SHA.
SERENA_REF="${SERENA_REF:-main}"
CLAUDE_SKILLS_REF="${CLAUDE_SKILLS_REF:-main}"
GSTACK_REF="${GSTACK_REF:-main}"
CLAUDE_CLI_SHA256="${CLAUDE_CLI_SHA256:-}"   # optional sha256 of https://claude.ai/install.sh
LSP_FAILURES=0

log()  { printf '[install] %s\n' "$*" | tee -a "$LOG"; }
warn() { printf '[install][warn] %s\n' "$*" | tee -a "$LOG" >&2; }
die()  { printf '[install][error] %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

# ---------- optional: settings.json hook wiring ----------
# Gated by CLAUDE_INSTALL_SETTINGS=1. Off by default — safe for existing users.
# When the flag is unset and the previous install backed up a settings.json,
# restore it into the new overlay so user customizations survive the swap.
# $1 = backup dir (the $BACKUP path captured at swap time, or "" if no backup).
maybe_install_settings() {
  local backup_dir="${1:-}"
  local target="$CLAUDE_HOME/settings.json"

  if [[ "${CLAUDE_INSTALL_SETTINGS:-}" == "1" ]]; then
    # Opt-in: back up any existing settings.json (may live in the backup dir from
    # the overlay swap, since the swap moves $CLAUDE_HOME wholesale), then write
    # the hook template.
    local prev_settings=""
    if [[ -f "$target" ]]; then
      prev_settings="$target"
    elif [[ -n "$backup_dir" && -f "$backup_dir/settings.json" ]]; then
      prev_settings="$backup_dir/settings.json"
    fi
    if [[ -n "$prev_settings" ]]; then
      local bak="$target.bak-$(date +%s)"
      cp -a "$prev_settings" "$bak"
      log "Backed up existing settings.json → $bak"
    fi
    python3 - "$CLAUDE_HOME" <<'PYEOF'
import json, os, sys

h = sys.argv[1]

def hook(cmd):
    return [{"type": "command", "command": cmd}]

settings = {
    "hooks": {
        "PostToolUse": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/cost_log.py")}
        ],
        "Notification": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/denial_tracker.py")}
        ],
        "PreToolUse": [
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/env-scrub.py")},
            {"matcher": "Skill",      "hooks": hook(f"{h}/hooks/skill_budget.py")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-red-phase-gate.sh")},
            {"matcher": "Write",      "hooks": hook(f"{h}/hooks/block-bare-repo-markers.py")}
        ],
        "PostCompact": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-warning.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/post-compact-context.sh")}
        ]
    }
}

dst = os.path.join(h, "settings.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"installed: {dst} (8 hooks wired)")
PYEOF
  else
    # Flag not set: restore user's previous settings.json from backup if present.
    if [[ -n "$backup_dir" && -f "$backup_dir/settings.json" ]]; then
      cp -a "$backup_dir/settings.json" "$target"
      log "Preserved existing $target (re-run with CLAUDE_INSTALL_SETTINGS=1 to wire hooks)"
    fi
  fi
}

# ---------- preflight ----------
command -v bash    >/dev/null || die "bash required"
command -v git     >/dev/null || die "git required"
command -v python3 >/dev/null || die "python3 required (used by hooks for JSON parsing)"
command -v rsync   >/dev/null || die "rsync required"

NONINTERACTIVE="${CLAUDE_INSTALL_NONINTERACTIVE:-0}"
ask() {
  local prompt="$1" default="$2" var
  if [[ "$NONINTERACTIVE" == "1" ]]; then
    printf '%s\n' "$default"
    return
  fi
  read -r -p "$prompt [$default]: " var
  printf '%s\n' "${var:-$default}"
}

# ---------- stage overlay atomically (avoids TOCTOU on $CLAUDE_HOME) ----------
STAGE="$CLAUDE_HOME.new-$TS"
log "Staging overlay at $STAGE"
mkdir -p "$STAGE"
rsync -a \
  --exclude='memory/projects' \
  --exclude='.credentials.json' \
  --exclude='*.bak' \
  --exclude='__pycache__' \
  "$REPO_ROOT/claude/" "$STAGE/"

# Hooks must be executable (recursive — subdirs may contain helpers).
find "$STAGE/hooks" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} +

# ---------- swap into place ----------
# Resolve actual target (symlinks rejected: stale symlinks are unsafe to follow).
if [[ -L "$CLAUDE_HOME" ]]; then
  log "Removing stale symlink at $CLAUDE_HOME"
  rm "$CLAUDE_HOME"
fi
BACKUP=""
if [[ -e "$CLAUDE_HOME" ]]; then
  BACKUP="$CLAUDE_HOME.bak-$TS"
  log "Existing $CLAUDE_HOME → backing up to $BACKUP"
  mv "$CLAUDE_HOME" "$BACKUP"
fi
mv "$STAGE" "$CLAUDE_HOME"
maybe_install_settings "$BACKUP"

# ---------- render CLAUDE.md from template ----------
# Use python3 with env-var-driven substitution; sed is unsafe when values contain
# pipe/backslash/ampersand/newline (e.g. multiline git config user.name).
if [[ -f "$CLAUDE_HOME/CLAUDE.md.template" ]]; then
  log "Rendering CLAUDE.md from template"
  export _CP_CLAUDE_HOME="$CLAUDE_HOME"
  export _CP_USER_EMAIL="${USER_EMAIL:-$(git config --global user.email 2>/dev/null || echo 'you@example.com')}"
  export _CP_USER_NAME="${USER_NAME:-$(git config --global user.name 2>/dev/null || echo 'developer')}"
  python3 - "$CLAUDE_HOME/CLAUDE.md.template" "$CLAUDE_HOME/CLAUDE.md" <<'PYEOF'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    body = f.read()
# Strip control chars from substitution values; cap length to 200 chars.
def clean(v):
    return ''.join(c for c in v if c == '\t' or c == ' ' or (c.isprintable() and ord(c) >= 32))[:200]
mapping = {
    '${CLAUDE_HOME}': clean(os.environ.get('_CP_CLAUDE_HOME', '')),
    '${USER_EMAIL}':  clean(os.environ.get('_CP_USER_EMAIL', '')),
    '${USER_NAME}':   clean(os.environ.get('_CP_USER_NAME', '')),
}
for k, v in mapping.items():
    body = body.replace(k, v)
with open(dst, 'w', encoding='utf-8') as f:
    f.write(body)
PYEOF
  unset _CP_CLAUDE_HOME _CP_USER_EMAIL _CP_USER_NAME
fi

# ---------- env file ----------
ENV_FILE="$REPO_ROOT/.env"
if [[ -f "$ENV_FILE" && "${CLAUDE_REFRESH_ENV:-0}" != "1" ]]; then
  log "Existing $ENV_FILE preserved (set CLAUDE_REFRESH_ENV=1 to overwrite)"
else
  cat > "$ENV_FILE" <<EOF
# pipelinekit local env (re-generated by install.sh)
CLAUDE_HOME=$CLAUDE_HOME
USER_EMAIL=${USER_EMAIL:-you@example.com}
USER_NAME=${USER_NAME:-developer}
PIPELINE_NIT_FIRST=0
# Supply-chain pins (override before re-running install for reproducibility)
SERENA_REF=$SERENA_REF
CLAUDE_SKILLS_REF=$CLAUDE_SKILLS_REF
GSTACK_REF=$GSTACK_REF
EOF
  log "Wrote $ENV_FILE"
fi

# ---------- optionals ----------
OPTIONALS_DEFAULT="${CLAUDE_INSTALL_OPTIONALS:-tresor,lsp,mcp}"
if [[ "$NONINTERACTIVE" != "1" ]]; then
  echo
  echo "Optional components: tresor lsp mcp gstack claude-skills serena"
  OPTIONALS="$(ask 'Comma-separated list to install' "$OPTIONALS_DEFAULT")"
else
  OPTIONALS="$OPTIONALS_DEFAULT"
fi

want() { [[ ",$OPTIONALS," == *",$1,"* ]]; }

# tresor already bundled in overlay copy step; no-op confirmation.
if want tresor; then
  log "Tresor resources present at $CLAUDE_HOME/tresor-resources"
fi

# LSP servers. Each failure increments LSP_FAILURES; summary printed at end.
if want lsp; then
  log "Installing LSP servers (pyright, typescript, csharp, gopls, rust-analyzer)"
  # --ignore-scripts denies postinstall RCE from typosquats; safe for these known packages.
  if command -v npm >/dev/null; then
    npm install -g --silent --ignore-scripts pyright typescript typescript-language-server 2>>"$LOG" \
      || { warn "npm LSP install partial"; LSP_FAILURES=$((LSP_FAILURES+1)); }
  fi
  if command -v dotnet >/dev/null; then
    dotnet tool install --global csharp-ls 2>>"$LOG" \
      || warn "csharp-ls already installed or failed"
  fi
  if command -v go >/dev/null; then
    go install golang.org/x/tools/gopls@latest 2>>"$LOG" \
      || { warn "gopls install failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
  fi
  if command -v rustup >/dev/null; then
    rustup component add rust-analyzer 2>>"$LOG" \
      || { warn "rust-analyzer add failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
  fi
fi

# MCP servers (npx-based, no global install).
if want mcp; then
  log "Provisioning .mcp.json template (copy to project roots as needed)"
  if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
    log "  → cp $REPO_ROOT/.mcp.json.template <your-project>/.mcp.json"
  fi
fi

# Serena (semantic MCP). Pinnable via $SERENA_REF.
if want serena; then
  log "Installing serena (semantic code MCP) @ ref=$SERENA_REF"
  if [[ "$SERENA_REF" == "main" ]]; then
    warn "serena pinned to 'main' (rolling). Override with SERENA_REF=<commit-sha> for reproducibility."
  fi
  if command -v uv >/dev/null; then
    uv tool install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed"
  else
    pip install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed (need uv or pip)"
  fi
fi

# gstack overlay (third-party; install with --prefix to namespace as /gstack-*).
# Requires GSTACK_REPO env var (full https URL). No default to prevent typosquat risk.
if want gstack; then
  if [[ -z "${GSTACK_REPO:-}" ]]; then
    warn "gstack requested but GSTACK_REPO env var not set. Skipping. Set GSTACK_REPO=https://github.com/<owner>/<repo> to enable."
  else
    log "Installing gstack overlay from $GSTACK_REPO @ ref=$GSTACK_REF (namespaced as /gstack-*)"
    GSTACK_DIR="$HOME/.gstack"
    if [[ ! -d "$GSTACK_DIR" ]]; then
      git clone --branch "$GSTACK_REF" --depth 1 "$GSTACK_REPO" "$GSTACK_DIR" 2>>"$LOG" \
        || warn "gstack clone failed (check GSTACK_REPO + GSTACK_REF)"
    fi
    if [[ -x "$GSTACK_DIR/setup" ]]; then
      "$GSTACK_DIR/setup" --prefix gstack- 2>>"$LOG" || warn "gstack setup failed"
    fi
  fi
fi

# Third-party skill library (alirezarezvani/claude-skills). Pinnable via $CLAUDE_SKILLS_REF.
if want claude-skills; then
  log "Installing third-party claude-skills @ ref=$CLAUDE_SKILLS_REF"
  if [[ "$CLAUDE_SKILLS_REF" == "main" ]]; then
    warn "claude-skills pinned to 'main' (rolling). Override with CLAUDE_SKILLS_REF=<commit-sha>."
  fi
  CS_DIR="$HOME/claude-skills"
  if [[ ! -d "$CS_DIR" ]]; then
    git clone --branch "$CLAUDE_SKILLS_REF" --depth 1 \
      https://github.com/alirezarezvani/claude-skills "$CS_DIR" 2>>"$LOG" \
      || warn "claude-skills clone failed"
  else
    log "claude-skills already present — not auto-pulling (re-clone manually to update)"
  fi
fi

# ---------- verify ----------
log "Verifying install"
bash "$SCRIPT_DIR/verify.sh" || warn "Verification reported issues — see $LOG"

if [[ "$LSP_FAILURES" -gt 0 ]]; then
  warn "LSP install had $LSP_FAILURES failure(s) — language-server features will be limited until fixed. See $LOG."
fi

log "Install complete. Open a new terminal and run: claude"
log "Tell Claude:  /pipeline   (after creating docs/features.md in your project)"
