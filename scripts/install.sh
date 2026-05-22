#!/usr/bin/env bash
# pipelinekit installer.
# Idempotent. Re-run to update. Supports interactive and non-interactive modes.
#
# Env:
#   CLAUDE_HOME                 Target overlay dir (default: $HOME/.claude)
#   CLAUDE_INSTALL_NONINTERACTIVE=1   Skip all prompts; assume sane defaults
#   CLAUDE_INSTALL_OPTIONALS    deprecated; flag is a no-op (kept for backward-compat). All components are installed by default.

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
      local bak
      bak="$target.bak-$(date +%s)"
      cp -a "$prev_settings" "$bak"
      log "Backed up existing settings.json → $bak"
    fi
    python3 - "$CLAUDE_HOME" <<'PYEOF'
import json, os, sys

h = sys.argv[1]

def hook(cmd, args=None):
    return [{"type": "command", "command": cmd, "args": args or []}]

settings = {
    "hooks": {
        "PostToolUse": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/cost_log.py")}
        ],
        "Stop": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PermissionRequest": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "Notification": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/denial_tracker.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PreToolUse": [
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/env-scrub.py")},
            {"matcher": "Skill",      "hooks": hook(f"{h}/hooks/skill_budget.py")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-red-phase-gate.sh")},
            {"matcher": "Write",      "hooks": hook(f"{h}/hooks/block-bare-repo-markers.py")}
        ],
        "PostCompact": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-warning.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/post-compact-context.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ]
    }
}

dst = os.path.join(h, "settings.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"installed: {dst} (12 hooks wired)")
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
EOF
  log "Wrote $ENV_FILE"
fi

# ---------- optionals (deprecated env-var, all components default-on) ----------
[[ -n "${CLAUDE_INSTALL_OPTIONALS:-}" ]] && log "CLAUDE_INSTALL_OPTIONALS is deprecated; flag is a no-op (kept for backward-compat). All components install by default."

# tresor already bundled in overlay copy step; no-op confirmation.
log "Tresor resources present at $CLAUDE_HOME/tresor-resources"

# LSP servers. Each failure increments LSP_FAILURES; summary printed at end.
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

# Swift LSP (macOS only; ships with Xcode — no separate install).
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v xcrun >/dev/null && xcrun --find sourcekit-lsp >/dev/null 2>&1; then
    log "sourcekit-lsp present (bundled with Xcode)"
  else
    warn "sourcekit-lsp not found — install full Xcode (App Store) to enable Swift LSP"
    # Intentionally not incrementing LSP_FAILURES — sourcekit-lsp ships with Xcode, not a separate install.
  fi
else
  warn "sourcekit-lsp is macOS-only (ships with Xcode); skipping on $(uname -s)"
  # Intentionally not incrementing LSP_FAILURES — platform-skip is not a failure.
fi

# Kotlin LSP (cross-platform). On Darwin use brew; elsewhere fall back to pinned binary release.
if command -v kotlin-language-server >/dev/null; then
  log "kotlin-language-server already installed; skipping"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null; then
  brew install kotlin-language-server 2>>"$LOG" \
    || { warn "kotlin-language-server brew install failed"; LSP_FAILURES=$((LSP_FAILURES+1)); }
else
  KLS_VERSION="${KLS_VERSION:-1.3.13}"
  KLS_URL="https://github.com/fwcd/kotlin-language-server/releases/download/${KLS_VERSION}/server.zip"
  KLS_DIR="$HOME/.local/share/kotlin-language-server"
  mkdir -p "$HOME/.local/bin" "$KLS_DIR"
  if command -v curl >/dev/null && command -v unzip >/dev/null \
     && curl -fsSL -o /tmp/kls.zip "$KLS_URL" \
     && unzip -q -o /tmp/kls.zip -d "$KLS_DIR" \
     && ln -sf "$KLS_DIR/server/bin/kotlin-language-server" "$HOME/.local/bin/kotlin-language-server" \
     && chmod +x "$HOME/.local/bin/kotlin-language-server"; then
    log "kotlin-language-server installed to $HOME/.local/bin (v${KLS_VERSION})"
    rm -f /tmp/kls.zip
  else
    warn "kotlin-language-server install failed (curl/unzip missing or download failed)"
    LSP_FAILURES=$((LSP_FAILURES+1))
    rm -f /tmp/kls.zip
  fi
fi

# MCP servers (npx-based, no global install).
log "Provisioning .mcp.json template (copy to project roots as needed)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> cp $REPO_ROOT/.mcp.json.template <your-project>/.mcp.json"
fi

# Serena (semantic MCP). Pinnable via $SERENA_REF.
log "Installing serena (semantic code MCP) @ ref=$SERENA_REF"
if [[ "$SERENA_REF" == "main" ]]; then
  warn "serena pinned to 'main' (rolling). Override with SERENA_REF=<commit-sha> for reproducibility."
fi
if command -v uv >/dev/null; then
  uv tool install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed"
else
  pip install --quiet "git+https://github.com/oraios/serena@${SERENA_REF}" 2>>"$LOG" || warn "serena install failed (need uv or pip)"
fi

# gstack is a third-party overlay project (alirezarezvani/gstack); install instructions live in its own README.
log "gstack is a third-party overlay; for install instructions see https://github.com/alirezarezvani/gstack"

# Mobile MCPs (XcodeBuildMCP + ios-simulator-mcp). Both pulled JIT via npx/uvx — no global install.
log "Mobile MCPs available as advisory uncomment-to-enable in .mcp.json.template:"
log "  - XcodeBuildMCP      (iOS build automation; requires Xcode on host)"
log "  - ios-simulator-mcp  (iOS Simulator control; requires Xcode on host)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> Uncomment the _mobile_mcpServers block in .mcp.json.template before copying into <your-project>/.mcp.json"
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "Mobile MCPs require Xcode on host. $(uname -s) detected — XcodeBuildMCP supports remote macOS builds; ios-simulator-mcp will not function locally."
fi

# Azure CLI. Auto-installed via Microsoft-published one-liner on Debian/Ubuntu.
# Trust pattern: curl-to-bash; Microsoft does not publish a sha256 for this script —
# verify https origin only. User is responsible for `az login` afterwards — the install
# does NOT authenticate.
if command -v az >/dev/null; then
  log "az already installed; skipping (run 'az version' to check version)"
elif [[ "$(uname -s)" == "Linux" ]]; then
  if [[ -f /etc/os-release ]] && grep -qE 'ID(_LIKE)?=.*(ubuntu|debian)' /etc/os-release; then
    log "Installing Azure CLI via Microsoft one-liner (https://aka.ms/InstallAzureCLIDeb)"
    if curl -sL https://aka.ms/InstallAzureCLIDeb | bash 2>>"$LOG"; then
      log "Azure CLI installed. Authenticate yourself with the standard interactive sign-in (the installer does not log you in)."
    else
      warn "Azure CLI install failed — see $LOG. Manual install: https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
    fi
  else
    warn "Azure CLI auto-install supports Debian/Ubuntu only. Other Linux distros: see https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  warn "Azure CLI on macOS: install via Homebrew — 'brew install azure-cli' (auto-install is Debian/Ubuntu-only)"
else
  warn "Azure CLI auto-install skipped on $(uname -s). See https://learn.microsoft.com/cli/azure/install-azure-cli"
fi

# Vercel CLI. Probed via PATH; install + authenticate manually outside Claude.
# Prints the official npm install one-liner and reminds the user to run
# `vercel login` themselves. Never auto-installs the CLI and NEVER auto-authenticates.
# NEVER auto-run `vercel login` — user authenticates manually outside Claude.
if command -v vercel >/dev/null 2>&1; then
  log "vercel CLI already installed; skipping (run 'vercel --version' to check version)"
else
  warn "Vercel CLI not on PATH. Install: npm i -g vercel"
fi
log "Authenticate via: vercel login   (run outside Claude before invoking /pipeline)"

# Claude-Context MCP (community — @zilliztech, NOT Anthropic). Codebase semantic RAG via npx;
# AST-aware chunking + Merkle-tree incremental indexing. local-mode (no Milvus account) is
# documented in .mcp.json.template; cloud-mode uses Milvus/Zilliz creds via env vars.
# Skip below ~50k LOC: indexing adds latency with no semantic-retrieval benefit at that scale.
log "Claude-Context MCP available (community — @zilliztech/claude-context, NOT Anthropic)."
log "  - Codebase semantic RAG: AST-aware chunking + Merkle-tree incremental indexing"
log "  - local-mode setup: see .mcp.json.template _claude_context_mcpServers block for env-var skeleton"
log "  - cloud-mode setup: same block — swap in MILVUS_ADDRESS / MILVUS_TOKEN for Zilliz cloud"
log "  - 50k LOC heuristic: /analyze skips semantic retrieval below 50000 LOC; opt-in indexing on smaller repos via direct MCP query"
log "  - Re-indexing budget: <5s per 'git pull' (upstream benchmark; not a guarantee)"
if [[ -f "$REPO_ROOT/.mcp.json.template" ]]; then
  log "  -> Uncomment the _claude_context_mcpServers block in .mcp.json.template before copying into <your-project>/.mcp.json"
fi
warn "@zilliztech/claude-context is a community MCP (NOT Anthropic-official). Review upstream before sandbox use; PIN the npx package to a specific version for reproducibility."


# claude-skills is a third-party skill collection (alirezarezvani/claude-skills); install instructions live in its own README.
log "claude-skills is a third-party skill collection; for install instructions see https://github.com/alirezarezvani/claude-skills"

# Claude CLI version-floor check for EnterWorktree / ExitWorktree (v2.1.72+).
# Soft: warn only. Below-floor users keep working via the manual `git worktree add` fallback.
if command -v claude >/dev/null 2>&1; then
  CLAUDE_VER=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  if [[ -z "$CLAUDE_VER" ]]; then
    warn "could not parse Claude CLI version from 'claude --version' output"
  else
    MIN_VER="2.1.72"
    LOWEST=$(printf '%s\n%s\n' "$CLAUDE_VER" "$MIN_VER" | sort -V | head -1)
    if [[ "$LOWEST" != "$MIN_VER" ]]; then
      warn "Claude CLI ${CLAUDE_VER} is below ${MIN_VER}. Native EnterWorktree / ExitWorktree tools will be unavailable; pipelinekit will fall back to manual 'git worktree add'. Upgrade with: https://claude.ai/install.sh"
    fi
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
log "Tip: to wire the optional hooks (cost logging, env scrubbing, TDD gate, notify-emit, etc.), re-run with CLAUDE_INSTALL_SETTINGS=1"
