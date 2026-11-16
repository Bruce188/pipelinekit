#!/usr/bin/env bash
# Codespaces / devcontainer post-create hook.
# Runs once after container build. Bootstraps pipelinekit.

set -euo pipefail

REPO_ROOT="${PIPELINEKIT_ROOT:-${CLAUDE_PORTABLE_ROOT:-$PWD}}"
cd "$REPO_ROOT"

echo "[post-create] Bootstrapping pipelinekit in $REPO_ROOT"

# Run main installer non-interactively.
CLAUDE_INSTALL_NONINTERACTIVE=1 bash "$REPO_ROOT/scripts/install.sh"

echo "[post-create] Done. Open a terminal and run: claude"
