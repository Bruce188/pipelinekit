#!/usr/bin/env bash
# claude-portable installer.
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
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$REPO_ROOT/.install.log"

log()  { printf '[install] %s\n' "$*" | tee -a "$LOG"; }
warn() { printf '[install][warn] %s\n' "$*" | tee -a "$LOG" >&2; }
die()  { printf '[install][error] %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

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

# ---------- backup existing ----------
if [[ -e "$CLAUDE_HOME" && ! -L "$CLAUDE_HOME" ]]; then
  BACKUP="$CLAUDE_HOME.bak-$TS"
  log "Existing $CLAUDE_HOME → backing up to $BACKUP"
  mv "$CLAUDE_HOME" "$BACKUP"
fi
if [[ -L "$CLAUDE_HOME" ]]; then
  log "Removing stale symlink at $CLAUDE_HOME"
  rm "$CLAUDE_HOME"
fi

# ---------- copy overlay ----------
log "Installing overlay to $CLAUDE_HOME"
mkdir -p "$CLAUDE_HOME"
rsync -a \
  --exclude='memory/projects' \
  --exclude='.credentials.json' \
  --exclude='*.bak' \
  --exclude='__pycache__' \
  "$REPO_ROOT/claude/" "$CLAUDE_HOME/"

# Hooks must be executable.
find "$CLAUDE_HOME/hooks" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} +

# ---------- render CLAUDE.md from template ----------
if [[ -f "$CLAUDE_HOME/CLAUDE.md.template" ]]; then
  log "Rendering CLAUDE.md from template"
  USER_EMAIL_VAL="${USER_EMAIL:-$(git config --global user.email 2>/dev/null || echo 'you@example.com')}"
  USER_NAME_VAL="${USER_NAME:-$(git config --global user.name 2>/dev/null || echo 'developer')}"
  CLAUDE_HOME_VAL="$CLAUDE_HOME"
  sed \
    -e "s|\${CLAUDE_HOME}|$CLAUDE_HOME_VAL|g" \
    -e "s|\${USER_EMAIL}|$USER_EMAIL_VAL|g" \
    -e "s|\${USER_NAME}|$USER_NAME_VAL|g" \
    "$CLAUDE_HOME/CLAUDE.md.template" > "$CLAUDE_HOME/CLAUDE.md"
fi

# ---------- env file ----------
ENV_FILE="$REPO_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<EOF
# claude-portable local env
CLAUDE_HOME=$CLAUDE_HOME
USER_EMAIL=${USER_EMAIL:-you@example.com}
USER_NAME=${USER_NAME:-developer}
PIPELINE_NIT_FIRST=0
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

# LSP servers.
if want lsp; then
  log "Installing LSP servers (pyright, typescript, csharp, gopls, rust-analyzer)"
  if command -v npm >/dev/null; then
    npm install -g --silent pyright typescript typescript-language-server 2>>"$LOG" || warn "npm LSP install partial"
  fi
  if command -v dotnet >/dev/null; then
    dotnet tool install --global csharp-ls 2>>"$LOG" || warn "csharp-ls already installed or failed"
  fi
  if command -v go >/dev/null; then
    go install golang.org/x/tools/gopls@latest 2>>"$LOG" || warn "gopls install failed"
  fi
  if command -v rustup >/dev/null; then
    rustup component add rust-analyzer 2>>"$LOG" || warn "rust-analyzer add failed"
  fi
fi

# MCP servers (npx-based, no global install).
if want mcp; then
  log "Provisioning .mcp.json template (copy to project roots as needed)"
  if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
    log "  → cp $REPO_ROOT/.mcp.json.template <your-project>/.mcp.json"
  fi
fi

# Serena (semantic MCP).
if want serena; then
  log "Installing serena (semantic code MCP)"
  if command -v uv >/dev/null; then
    uv tool install --quiet git+https://github.com/oraios/serena 2>>"$LOG" || warn "serena install failed"
  else
    pip install --quiet git+https://github.com/oraios/serena 2>>"$LOG" || warn "serena install failed (need uv or pip)"
  fi
fi

# gstack overlay (third-party; install with --prefix to namespace as /gstack-*).
if want gstack; then
  log "Installing gstack overlay (namespaced as /gstack-*)"
  GSTACK_DIR="$HOME/.gstack"
  if [[ ! -d "$GSTACK_DIR" ]]; then
    git clone --depth 1 https://github.com/<gstack-repo> "$GSTACK_DIR" 2>>"$LOG" \
      || warn "gstack clone skipped (set repo URL in install.sh)"
  fi
  if [[ -x "$GSTACK_DIR/setup" ]]; then
    "$GSTACK_DIR/setup" --prefix gstack- 2>>"$LOG" || warn "gstack setup failed"
  fi
fi

# Third-party skill library (alirezarezvani/claude-skills).
if want claude-skills; then
  log "Installing third-party claude-skills"
  CS_DIR="$HOME/claude-skills"
  if [[ ! -d "$CS_DIR" ]]; then
    git clone --depth 1 https://github.com/alirezarezvani/claude-skills "$CS_DIR" 2>>"$LOG" \
      || warn "claude-skills clone failed"
  else
    (cd "$CS_DIR" && git pull --quiet 2>>"$LOG" || warn "claude-skills pull failed")
  fi
fi

# ---------- verify ----------
log "Verifying install"
bash "$SCRIPT_DIR/verify.sh" || warn "Verification reported issues — see $LOG"

log "Install complete. Open a new terminal and run: claude"
log "Tell Claude:  /pipeline   (after creating docs/features.md in your project)"
