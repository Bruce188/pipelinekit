#!/usr/bin/env bash
# Codespaces / devcontainer post-create hook.
# Runs once after container build. Bootstraps claude-portable + LSPs + MCP fleet.

set -euo pipefail

REPO_ROOT="${CLAUDE_PORTABLE_ROOT:-$PWD}"
cd "$REPO_ROOT"

echo "[post-create] Bootstrapping claude-portable in $REPO_ROOT"

# Run main installer non-interactively.
CLAUDE_INSTALL_NONINTERACTIVE=1 \
CLAUDE_INSTALL_OPTIONALS="${CLAUDE_INSTALL_OPTIONALS:-tresor,lsp,mcp}" \
    bash "$REPO_ROOT/scripts/install.sh"

echo "[post-create] Done. Open a terminal and run: claude"
