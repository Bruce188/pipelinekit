FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

ARG USERNAME=vscode

# System deps for hooks, gstack, LSPs, MCP servers
RUN apt-get update && apt-get install -y --no-install-recommends \
        ripgrep \
        fd-find \
        jq \
        yq \
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
        zsh \
        fzf \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (latest)
RUN su - $USERNAME -c "curl -fsSL https://claude.ai/install.sh | sh" || true

# LSP servers + dev tooling installed in post-create.sh to keep image lean.

USER $USERNAME
WORKDIR /home/$USERNAME
