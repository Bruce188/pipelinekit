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
# Override UNDERSTAND_ANYTHING_SHA=<commit-sha> to pin to a specific commit.
UNDERSTAND_ANYTHING_SHA="${UNDERSTAND_ANYTHING_SHA:-470cc01dc5f9236a93eb704afdd479cd5db79710}"
CLAUDE_CLI_SHA256="${CLAUDE_CLI_SHA256:-}"   # optional sha256 of https://claude.ai/install.sh
LSP_FAILURES=0

log()  { printf '[install] %s\n' "$*" | tee -a "$LOG"; }
warn() { printf '[install][warn] %s\n' "$*" | tee -a "$LOG" >&2; }
die()  { printf '[install][error] %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

# ---------- selftest harness ----------
_selftest_main() {
  local pass=0 fail=0
  # Enumerate _selftest_* functions; skip _selftest_main itself.
  local fn
  while IFS= read -r fn; do
    [[ "$fn" == "_selftest_main" ]] && continue
    if ( "$fn" ); then
      pass=$((pass+1))
      echo "  [PASS] $fn"
    else
      fail=$((fail+1))
      echo "  [FAIL] $fn"
    fi
  done < <(declare -F | awk '/_selftest_[a-z_]+$/ {print $NF}')
  echo "Results: $pass PASS / $fail FAIL"
  return "$fail"
}

_selftest_smoke_harness() {
  # Placeholder: proves the harness fires at least one case.
  return 0
}

_selftest_agentmemory_mcp_provisioned() {
  local sandbox
  sandbox=$(mktemp -d "${TMPDIR:-/tmp}/pipelinekit-selftest-XXXX") || return 1
  # shellcheck disable=SC2064
  trap "rm -rf '$sandbox'" RETURN
  local saved_home="${CLAUDE_HOME:-}"
  export CLAUDE_HOME="$sandbox/.claude"
  mkdir -p "$CLAUDE_HOME"

  # AC #2 canary: synthesize a settings.json and sha256 it.
  cat > "$CLAUDE_HOME/settings.json" <<'JSON'
{ "_canary": "agentmemory-must-not-touch-this" }
JSON
  local sha_before
  sha_before=$(python3 -c "import hashlib;print(hashlib.sha256(open('$CLAUDE_HOME/settings.json','rb').read()).hexdigest())")

  # AC #1: VOYAGE_API_KEY set → voyage provider, npx command, pinned version arg.
  ( VOYAGE_API_KEY=test_voyage OPENAI_API_KEY="" provision_agentmemory_mcp >/dev/null 2>&1 )
  python3 -c "
import json,sys
d=json.load(open('$CLAUDE_HOME/.mcp.json'))
assert 'agentmemory' in d['mcpServers'], 'AC-1 missing agentmemory key'
e=d['mcpServers']['agentmemory']
assert e['command']=='npx', 'AC-1 command not npx'
assert any('@agentmemory/agentmemory@0.9.21' in a for a in e['args']), 'AC-1 pin missing'
assert e['env']['AGENTMEMORY_EMBED_PROVIDER']=='voyage', 'AC-1 provider not voyage'
" || { echo "AC-1 FAIL"; return 1; }

  # AC #5: no API keys → local-onnx-quant + stderr contains Voyage.
  rm -f "$CLAUDE_HOME/.mcp.json"
  local ac5_stderr
  ac5_stderr=$( VOYAGE_API_KEY="" OPENAI_API_KEY="" provision_agentmemory_mcp 2>&1 >/dev/null )
  python3 -c "
import json
d=json.load(open('$CLAUDE_HOME/.mcp.json'))
assert d['mcpServers']['agentmemory']['env']['AGENTMEMORY_EMBED_PROVIDER']=='local-onnx-quant', 'AC-5 provider'
" || { echo "AC-5 FAIL provider"; return 1; }
  printf '%s\n' "$ac5_stderr" | grep -qi "voyage" || { echo "AC-5 FAIL Voyage warning missing"; return 1; }

  # AC #2: settings.json byte-identical (sha256 unchanged after provisioning).
  local sha_after
  sha_after=$(python3 -c "import hashlib;print(hashlib.sha256(open('$CLAUDE_HOME/settings.json','rb').read()).hexdigest())")
  [[ "$sha_before" == "$sha_after" ]] || { echo "AC-2 FAIL settings.json mutated"; return 1; }

  # AC #3: WSL2 + 2 GB mock → gate refuses (non-zero exit + stderr mentions WSL2 + 4 GB).
  local gate_stderr
  gate_stderr=$( { __pkit_mock_wsl_2gb=1 _wsl2_ram_gate 2>&1; echo "exit=$?"; } 2>&1 )
  printf '%s\n' "$gate_stderr" | grep -q "exit=1" || { echo "AC-3 FAIL gate accepted 2 GB"; return 1; }
  printf '%s\n' "$gate_stderr" | grep -q "WSL2" || { echo "AC-3 FAIL stderr missing WSL2"; return 1; }
  printf '%s\n' "$gate_stderr" | grep -q "4 GB" || { echo "AC-3 FAIL stderr missing 4 GB"; return 1; }

  # AC #4: same mock + PIPELINE_FORCE_INSTALL=1 → gate accepts.
  ( __pkit_mock_wsl_2gb=1 PIPELINE_FORCE_INSTALL=1 _wsl2_ram_gate ) 2>/dev/null \
    || { echo "AC-4 FAIL override rejected"; return 1; }

  # Restore env.
  [[ -n "$saved_home" ]] && export CLAUDE_HOME="$saved_home" || unset CLAUDE_HOME
  return 0
}

_selftest_understand_anything_provisioned() {
  # AC #1: marketplace-path mock — function logs invocation but does NOT execute live CLI.
  # AC #2: settings.json sha256 byte-identity before/after invocation.
  # AC #4: never-stage.txt contains `.understand-anything/`.
  # AC #5: clone-failure mock — function emits warn + exits 0 (non-fatal).
  local tmp; tmp=$(mktemp -d)
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  export CLAUDE_HOME="$tmp/.claude"
  mkdir -p "$CLAUDE_HOME"
  # Synthesize a known settings.json to detect any mutation.
  printf '{"hooks":{}}\n' > "$CLAUDE_HOME/settings.json"
  local pre_sha; pre_sha=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')

  # AC #1 marketplace mock — should not invoke live CLI.
  local m_out
  m_out=$( __pkit_mock_understand_anything_marketplace=1 provision_understand_anything 2>&1 )
  echo "$m_out" | grep -q "would invoke: claude plugin marketplace add Lum1104/Understand-Anything" \
    || { echo "FAIL: marketplace mock did not emit expected log line"; return 1; }

  # AC #5 clone-fail mock — should warn + return 0 (non-fatal).
  __pkit_mock_understand_anything_clone_fail=1 provision_understand_anything >/dev/null 2>&1
  local clone_rc=$?
  [[ $clone_rc -eq 0 ]] \
    || { echo "FAIL: clone-fail mock did not return 0 (got $clone_rc)"; return 1; }

  # AC #2 settings.json byte-identity after invocation.
  local post_sha; post_sha=$(sha256sum "$CLAUDE_HOME/settings.json" | awk '{print $1}')
  [[ "$pre_sha" == "$post_sha" ]] \
    || { echo "FAIL: settings.json sha256 changed (pre=$pre_sha post=$post_sha)"; return 1; }

  # AC #4 never-stage.txt contains the new pattern (resolve relative to repo root).
  local NEVERSTAGE; NEVERSTAGE="$(dirname "${BASH_SOURCE[0]}")/../claude/config/never-stage.txt"
  grep -q '^\.understand-anything/$' "$NEVERSTAGE" \
    || { echo "FAIL: .understand-anything/ not found in $NEVERSTAGE"; return 1; }

  echo "PASS: _selftest_understand_anything_provisioned"
  return 0
}

_wsl2_ram_gate() {
  # TEST HOOK: __pkit_mock_wsl_2gb=1 forces "WSL2 + 2 GB" path. Do not set in production.
  if [[ "${__pkit_mock_wsl_2gb:-0}" == "1" ]]; then
    [[ "${PIPELINE_FORCE_INSTALL:-0}" == "1" ]] && return 0
    printf '[install][error] WSL2 host has < 4 GB MemTotal. agentmemory MCP requires 4 GB minimum.\n' >&2
    printf '[install][error] Override via PIPELINE_FORCE_INSTALL=1.\n' >&2
    return 1
  fi
  # Skip on non-Linux (gate is a no-op for Darwin/etc.).
  [[ ! -r /proc/version ]] && return 0
  # Probe WSL2 marker.
  grep -qi microsoft /proc/version || return 0
  # Override switch.
  [[ "${PIPELINE_FORCE_INSTALL:-0}" == "1" ]] && return 0
  # Parse MemTotal in kB.
  local mem_kb
  mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
  if [[ "$mem_kb" -lt 4194304 ]]; then
    printf '[install][error] WSL2 host has < 4 GB MemTotal (%s kB). agentmemory MCP requires 4 GB minimum.\n' "$mem_kb" >&2
    printf '[install][error] Override via PIPELINE_FORCE_INSTALL=1 (caveat: install may OOM on heavy MCP load).\n' >&2
    return 1
  fi
  return 0
}

provision_agentmemory_mcp() {
  # Step 1: WSL2 RAM gate — warn-and-continue on insufficient RAM.
  if ! _wsl2_ram_gate; then
    warn "agentmemory MCP install skipped (WSL2 RAM gate)"
    return 0
  fi

  # Step 2: Resolve embedding provider via env-var probe chain.
  local EMBED_PROVIDER
  if [[ -n "${VOYAGE_API_KEY:-}" ]]; then
    EMBED_PROVIDER="voyage"
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    EMBED_PROVIDER="openai"
  else
    EMBED_PROVIDER="local-onnx-quant"
    warn "agentmemory: no VOYAGE_API_KEY / OPENAI_API_KEY in env — falling back to local-onnx-quant. Add VOYAGE_API_KEY to ~/.bashrc for better recall quality."
  fi

  # Step 3: Write MCP entry to ${CLAUDE_HOME}/.mcp.json via python3 heredoc.
  # Backup existing file first if present (mirrors maybe_install_settings lines 51-55).
  local mcp_target="${CLAUDE_HOME}/.mcp.json"
  if [[ -f "$mcp_target" ]]; then
    local mcp_bak="${mcp_target}.bak-$(date +%s)"
    cp -a "$mcp_target" "$mcp_bak"
    log "Backed up existing .mcp.json → $mcp_bak"
  fi

  python3 - "$mcp_target" "$EMBED_PROVIDER" <<'PYEOF'
import json, os, sys

dst, embed_provider = sys.argv[1], sys.argv[2]

# Load existing JSON or start fresh.
if os.path.isfile(dst):
    with open(dst, 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {"mcpServers": {}}

if "mcpServers" not in data:
    data["mcpServers"] = {}

data["mcpServers"]["agentmemory"] = {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@agentmemory/agentmemory@0.9.21", "mcp"],
    "env": {
        "AGENTMEMORY_EMBED_PROVIDER": embed_provider,
        "VOYAGE_API_KEY": "${VOYAGE_API_KEY}",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "AGENTMEMORY_EMBED_FALLBACK": "local-onnx-quant",
        "AGENTMEMORY_DB_PATH": ".agentmemory/agentmemory.db"
    }
}

# Atomic write via temp file + os.replace.
tmp = dst + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, dst)
print(f"agentmemory MCP entry written to {dst} (provider={embed_provider})")
PYEOF

  log "agentmemory MCP entry written (provider=$EMBED_PROVIDER)"

  # Step 4: Doctor smoke — warn-and-continue on failure.
  if command -v npx >/dev/null 2>&1; then
    (timeout 30 npx -y @agentmemory/agentmemory@0.9.21 doctor 2>>"$LOG" 1>>"$LOG") \
      || warn "agentmemory doctor smoke failed — first MCP-client invocation will lazily re-fetch; see $LOG"
  fi
}

# ---------- Understand-Anything plugin (Claude Code plugin, NOT MCP) ----------
# Probes for the `claude plugin marketplace add` CLI subcommand; falls back to
# git-clone + pinned-SHA when absent. Network failure is non-fatal (warn + return 0).
# AC #1/#2/#3/#5 binding — see docs/features-mem-graph-stack.md § feat/understand-anything-plugin.
provision_understand_anything() {
  local UA_URL="https://github.com/Lum1104/Understand-Anything"
  local UA_DIR="${CLAUDE_HOME:-$HOME/.claude}/plugins/understand-anything"
  local UA_SOURCE=""
  local UA_MODE=""

  # SHA-pin policy: warn if user overrides to a floating ref.
  if [[ ! "$UNDERSTAND_ANYTHING_SHA" =~ ^[0-9a-f]{40}$ ]]; then
    warn "UNDERSTAND_ANYTHING_SHA=$UNDERSTAND_ANYTHING_SHA is not a 40-char hex commit SHA (floating ref); proceeding but supply-chain pin is weakened."
  fi

  # Mock hooks for selftest (hermetic; never hit live network).
  if [[ "${__pkit_mock_understand_anything_marketplace:-0}" == "1" ]]; then
    log "[mock] understand-anything marketplace path forced; skipping live CLI."
    UA_MODE="marketplace"
    UA_SOURCE="Lum1104/Understand-Anything"
    log "[mock] would invoke: claude plugin marketplace add $UA_SOURCE"
    log "[mock] would invoke: claude plugin install understand-anything"
    return 0
  fi
  if [[ "${__pkit_mock_understand_anything_clone_fail:-0}" == "1" ]]; then
    warn "[mock] understand-anything git-clone synthesized failure; install skipped."
    return 0
  fi

  # Capability probe: NO leading slash. Spec text used `/plugin` which is an in-session
  # slash command, not a CLI subcommand — see analysis-v93 § OQ-1.
  if command -v claude >/dev/null 2>&1 \
     && claude plugin marketplace --help 2>/dev/null | grep -q "^[[:space:]]*add "; then
    UA_MODE="marketplace"
    UA_SOURCE="Lum1104/Understand-Anything"
  else
    UA_MODE="git-clone"
    UA_SOURCE="$UA_DIR"
  fi

  log "Installing Understand-Anything plugin via $UA_MODE path (SHA=$UNDERSTAND_ANYTHING_SHA)"

  if [[ "$UA_MODE" == "git-clone" ]]; then
    # Three-step pinned clone (portable across git versions; see analysis-v93 § OQ-2).
    if [[ -d "$UA_DIR/.git" ]]; then
      log "Understand-Anything already cloned at $UA_DIR; skipping clone."
    else
      mkdir -p "$(dirname "$UA_DIR")"
      git clone --depth 1 "$UA_URL" "$UA_DIR" 2>>"$LOG" \
        || { warn "Understand-Anything git clone failed (network?); continuing without plugin."; return 0; }
      git -C "$UA_DIR" fetch --depth 1 origin "$UNDERSTAND_ANYTHING_SHA" 2>>"$LOG" \
        || { warn "Understand-Anything fetch of pinned SHA failed; cloned dir left at HEAD."; }
      git -C "$UA_DIR" checkout --detach "$UNDERSTAND_ANYTHING_SHA" 2>>"$LOG" \
        || { warn "Understand-Anything checkout of pinned SHA failed; cloned dir left at HEAD."; }
    fi
  fi

  # Uniform finalize per analysis-v93 § Risk-4 (A): both paths end in
  # `claude plugin marketplace add <source>` — only `<source>` differs.
  if command -v claude >/dev/null 2>&1; then
    claude plugin marketplace add "$UA_SOURCE" 2>&1 | tee -a "$LOG" \
      || warn "Understand-Anything marketplace registration failed (exit $?); continuing."
    # Optimistic enable (Risk-3); warn-and-continue on failure.
    claude plugin install understand-anything 2>&1 | tee -a "$LOG" \
      || warn "Understand-Anything plugin enable failed; user may enable manually via /plugin."
  else
    warn "claude CLI not on PATH; Understand-Anything plugin files staged but not registered."
  fi
}

# ---------- selftest dispatcher ----------
# Short-circuit: `bash scripts/install.sh --selftest` runs only the selftest harness
# and exits before touching the filesystem (STAGE/mv/BACKUP surface).
if [[ "${1:-}" == "--selftest" ]]; then _selftest_main; exit $?; fi

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
        "SessionStart": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/session-start-context.sh")}
        ],
        "PreToolUse": [
            {"matcher": "Agent",      "hooks": hook(f"{h}/hooks/agent-caveman-gate.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-dangerous-commands.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-push-main.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/block-stage-sensitive.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/env-scrub.py")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/test-logger.sh")},
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/validate-commit-msg.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/claude-md-guard.py")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/pre-edit-protect.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-order-check.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/tdd-red-phase-gate.sh")},
            {"matcher": "Skill",      "hooks": hook(f"{h}/hooks/skill_budget.py")},
            {"matcher": "Write",      "hooks": hook(f"{h}/hooks/block-bare-repo-markers.py")}
        ],
        "PostToolUse": [
            {"matcher": "Bash",       "hooks": hook(f"{h}/hooks/strip-ai-attribution.sh")},
            {"matcher": "Edit|Write", "hooks": hook(f"{h}/hooks/post-edit-format.sh")}
        ],
        "Stop": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/memory-journal.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/stop-completion-gate.sh")}
        ],
        "SubagentStop": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/verify-worktree-commit.sh")}
        ],
        "Notification": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/denial_tracker.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PermissionRequest": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")}
        ],
        "PostCompact": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-warning.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/notify-emit.sh")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/post-compact-context.sh")}
        ],
        "UserPromptSubmit": [
            {"matcher": "*", "hooks": hook(f"{h}/hooks/context-budget-advisor.py")},
            {"matcher": "*", "hooks": hook(f"{h}/hooks/subagent-first-nudge.sh")}
        ]
    }
}

dst = os.path.join(h, "settings.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"installed: {dst} (26 hooks wired)")
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

# Agentmemory MCP (default-on; cloud embeddings preferred with local-ONNX-quant fallback).
log "Provisioning agentmemory MCP (default-on; cloud embeddings preferred)"
provision_agentmemory_mcp
provision_understand_anything

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
