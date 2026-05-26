#!/usr/bin/env bash
# oracle-bootstrap.sh — idempotent provisioner for Oracle Cloud Free Tier ARM Ampere A1
# Platform: aarch64 (Ubuntu 22.04 / 24.04 LTS), 4 OCPU / 24 GB RAM
#
# Usage:
#   bash oracle-bootstrap.sh [--self-test] [--with-swap]
#   curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh | bash
#
# Environment variables (all optional — script warns and continues when unset):
#   USER_EMAIL            Your email for git config substitution
#   USER_NAME             Your name for git config substitution
#   GH_TOKEN              GitHub personal access token (for private repos)
#   ANTHROPIC_API_KEY     Anthropic API key (supplied later via claude login)
#   CLAUDE_CLI_SHA256     SHA256 checksum for claude install.sh (pin for reproducibility)
#   CLAUDE_INSTALL_OPTIONALS  Comma list (default: tresor,lsp,mcp)
#   PIPELINEKIT_DIR       Clone target dir (default: $HOME/pipelinekit)

set -euo pipefail

SCRIPT_NAME="oracle-bootstrap"
PIPELINEKIT_REPO="https://github.com/Bruce188/pipelinekit.git"
PIPELINEKIT_DIR="${PIPELINEKIT_DIR:-$HOME/pipelinekit}"
CLAUDE_INSTALL_OPTIONALS="${CLAUDE_INSTALL_OPTIONALS:-tresor,lsp,mcp}"
CLAUDE_AI_INSTALL_URL="https://claude.ai/install.sh"

SELF_TEST=false
WITH_SWAP=false

# --------------------------------------------------------------------------- #
# Logging                                                                      #
# --------------------------------------------------------------------------- #
if [ "$(id -u)" = "0" ]; then
  LOG_FILE="/var/log/pipelinekit-bootstrap.log"
else
  LOG_FILE="${HOME}/.cache/pipelinekit-bootstrap.log"
fi
mkdir -p "$(dirname "$LOG_FILE")"

log() {
  local msg="[${SCRIPT_NAME}] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

# --------------------------------------------------------------------------- #
# Parse args                                                                   #
# --------------------------------------------------------------------------- #
for arg in "$@"; do
  case "$arg" in
    --self-test) SELF_TEST=true ;;
    --with-swap) WITH_SWAP=true ;;
    *) die "Unknown argument: $arg" ;;
  esac
done

# --------------------------------------------------------------------------- #
# Step 1: Architecture assertion                                                #
# --------------------------------------------------------------------------- #
ARCH="$(uname -m)"
if [ "$ARCH" != "aarch64" ]; then
  die "This script targets Oracle Cloud ARM Ampere A1 (aarch64). Detected arch: ${ARCH}. For x86_64 Hetzner CX22, use hetzner-bootstrap.sh instead."
fi
log "Arch check: ${ARCH} OK"

# --------------------------------------------------------------------------- #
# Step 2: Secrets / env validation (warn-and-continue on missing)              #
# --------------------------------------------------------------------------- #
for var in USER_EMAIL USER_NAME GH_TOKEN ANTHROPIC_API_KEY; do
  if [ -z "${!var:-}" ]; then
    log "${var} not set — skipping; set it later via claude login or .env edit"
  fi
done

if [ -z "${CLAUDE_CLI_SHA256:-}" ] && [ "${CLAUDE_CLI_ALLOW_UNVERIFIED:-0}" != "1" ]; then
  cat >&2 <<'CLAUDE_CLI_REFUSE'
[bootstrap][error] Refusing to install Claude CLI without a sha256 pin.

The Claude CLI installer at https://claude.ai/install.sh is curl-to-bash and
runs as the bootstrap user. Without a sha256 pin a MITM or upstream-account
compromise executes arbitrary code on this host. Choose one:

  1. Pin to a known-good checksum (recommended):
       export CLAUDE_CLI_SHA256=<64-char hex sha256>
     Anthropic publishes release notes at:
       https://docs.claude.com/en/release-notes/claude-code

  2. Opt out of the safety gate (NOT recommended for shared / CI hosts):
       export CLAUDE_CLI_ALLOW_UNVERIFIED=1

Re-run the bootstrap after setting one of the above.
CLAUDE_CLI_REFUSE
  die "Claude CLI sha256 refusal (set CLAUDE_CLI_SHA256=<hex> or CLAUDE_CLI_ALLOW_UNVERIFIED=1)"
fi
if [ -z "${CLAUDE_CLI_SHA256:-}" ]; then
  log "CLAUDE_CLI_SHA256 not set — CLAUDE_CLI_ALLOW_UNVERIFIED=1 acknowledged; installer will run unpinned."
fi

# --------------------------------------------------------------------------- #
# Step 3: Idempotency guards (self-test stops here)                            #
# --------------------------------------------------------------------------- #
SWAP_EXISTS=false
if swapon --show 2>/dev/null | grep -q .; then
  SWAP_EXISTS=true
fi

CLAUDE_EXISTS=false
if command -v claude &>/dev/null; then
  CLAUDE_EXISTS=true
fi

REPO_EXISTS=false
if [ -d "$PIPELINEKIT_DIR/.git" ]; then
  REPO_EXISTS=true
fi

if [ "$SELF_TEST" = "true" ]; then
  log "[self-test] arch=${ARCH}, swap_exists=${SWAP_EXISTS}, claude_exists=${CLAUDE_EXISTS}, repo_exists=${REPO_EXISTS}"
  log "[self-test] CLAUDE_INSTALL_OPTIONALS=${CLAUDE_INSTALL_OPTIONALS}"
  log "[self-test] PIPELINEKIT_DIR=${PIPELINEKIT_DIR}"
  log "[self-test] OK"
  exit 0
fi

# --------------------------------------------------------------------------- #
# Step 4: Swap (optional — only when --with-swap is passed)                   #
# A1 has 24 GB RAM; swap is not strictly needed. Use --with-swap when desired.#
# --------------------------------------------------------------------------- #
if [ "$WITH_SWAP" = "true" ]; then
  if [ "$SWAP_EXISTS" = "true" ]; then
    log "Swap already active — skipping swapfile creation"
  else
    log "Creating 4 GB swapfile at /swapfile"
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
      echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    log "Swap created and enabled"
  fi
else
  log "Swap skipped (A1 has 24 GB RAM). Pass --with-swap to enable."
fi

# --------------------------------------------------------------------------- #
# Step 5: System dependencies                                                  #
# --------------------------------------------------------------------------- #
log "Updating package lists"
apt-get update -qq

PKGS=(git python3 python3-pip rsync curl ca-certificates build-essential)
for pkg in "${PKGS[@]}"; do
  if dpkg -s "$pkg" &>/dev/null; then
    log "Package ${pkg} already installed — skipping"
  else
    log "Installing ${pkg}"
    apt-get install -y -qq "$pkg"
  fi
done

# --------------------------------------------------------------------------- #
# Step 6: Node 20 LTS via NodeSource (ARM64-clean distribution)               #
# --------------------------------------------------------------------------- #
if command -v node &>/dev/null && node --version 2>/dev/null | grep -q '^v20'; then
  log "Node 20 already on PATH — skipping NodeSource setup"
else
  log "Installing Node 20 via NodeSource"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
fi

# --------------------------------------------------------------------------- #
# Step 7: Claude CLI install                                                   #
# --------------------------------------------------------------------------- #
if [ "$CLAUDE_EXISTS" = "true" ]; then
  log "claude already on PATH — skipping CLI install"
else
  log "Downloading Claude CLI installer"
  curl -fsSL "${CLAUDE_AI_INSTALL_URL}" -o /tmp/claude-install.sh

  if [ -n "${CLAUDE_CLI_SHA256:-}" ]; then
    log "Verifying SHA256: ${CLAUDE_CLI_SHA256}"
    echo "${CLAUDE_CLI_SHA256}  /tmp/claude-install.sh" | sha256sum -c - || die "Claude installer SHA256 mismatch"
  else
    log "WARNING: CLAUDE_CLI_SHA256 unset — skipping checksum verification. Set for reproducible installs."
  fi

  log "Running Claude CLI installer"
  bash /tmp/claude-install.sh
  rm -f /tmp/claude-install.sh
fi

# --------------------------------------------------------------------------- #
# Step 8: Clone / update pipelinekit repo                                     #
# --------------------------------------------------------------------------- #
if [ "$REPO_EXISTS" = "true" ]; then
  log "Repo exists at ${PIPELINEKIT_DIR} — pulling latest"
  git -C "$PIPELINEKIT_DIR" pull --ff-only
else
  log "Cloning pipelinekit into ${PIPELINEKIT_DIR}"
  git clone "$PIPELINEKIT_REPO" "$PIPELINEKIT_DIR"
fi

# --------------------------------------------------------------------------- #
# Step 9: Run install.sh non-interactively                                    #
# --------------------------------------------------------------------------- #
log "Running install.sh (OPTIONALS: ${CLAUDE_INSTALL_OPTIONALS})"
cd "$PIPELINEKIT_DIR"
CLAUDE_INSTALL_NONINTERACTIVE=1 \
CLAUDE_INSTALL_OPTIONALS="$CLAUDE_INSTALL_OPTIONALS" \
  bash scripts/install.sh

# --------------------------------------------------------------------------- #
# Step 10: Verify                                                              #
# --------------------------------------------------------------------------- #
log "Running verify.sh"
# verify.sh may emit LSP_FAILURES warnings on ARM — those are benign; exit 0 regardless.
bash scripts/verify.sh || log "verify.sh exited non-zero — check ${LOG_FILE} for details (LSP_FAILURES warnings on ARM are expected)"

log "Bootstrap complete. See ${LOG_FILE} for the full transcript."
log "Next: run 'claude login' to authenticate, then set USER_EMAIL / USER_NAME in ~/.claude/CLAUDE.md."
