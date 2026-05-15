FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

ARG USERNAME=vscode

# System deps for hooks, gstack, LSPs, MCP servers
RUN apt-get update && apt-get install -y --no-install-recommends \
        ripgrep \
        fd-find \
        jq \
        tree \
        bat \
        htop \
        less \
        curl \
        wget \
        ca-certificates \
        unzip \
        zstd \
        sqlite3 \
        build-essential \
        pkg-config \
        libssl-dev \
        python3-pip \
        zsh \
        fzf \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && python3 -m pip install --no-cache-dir yq \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (latest).
# Build args:
#   CLAUDE_CLI_SHA256 — optional sha256 of the install script. If set, build fails on mismatch.
# Without a pin this is curl-pipe-sh; acceptable for an opt-in sandbox, but pin it for reproducibility.
ARG CLAUDE_CLI_SHA256=""
RUN su - $USERNAME -c '\
    set -e; \
    curl -fsSL -o /tmp/claude-install.sh https://claude.ai/install.sh; \
    if [ -n "'"$CLAUDE_CLI_SHA256"'" ]; then \
        echo "'"$CLAUDE_CLI_SHA256"'  /tmp/claude-install.sh" | sha256sum -c -; \
    else \
        echo "WARNING: CLAUDE_CLI_SHA256 not set — installing unverified Claude CLI."; \
    fi; \
    bash /tmp/claude-install.sh; \
    rm -f /tmp/claude-install.sh'

# LSP servers + dev tooling installed in post-create.sh to keep image lean.

USER $USERNAME
WORKDIR /home/$USERNAME
