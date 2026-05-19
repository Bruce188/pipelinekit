# Installation

## Local install (Linux / WSL / macOS bash)

<div data-snippet="chooser-quiz" data-question-set="deploy"></div>

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
./scripts/install.sh
```

Interactive prompts ask which optional components to install.

Non-interactive:
```bash
CLAUDE_INSTALL_NONINTERACTIVE=1 \
CLAUDE_INSTALL_OPTIONALS=tresor,lsp,mcp,serena \
  ./scripts/install.sh
```

## Cloud cold-start (Oracle / Hetzner)

Bootstrap a fresh cloud VM and install pipelinekit in one step. See [cloud-setup.md](cloud-setup.md) for the full walkthrough including image selection, SSH, firewall, and troubleshooting.

**Oracle Cloud Free Tier ARM A1 (aarch64):**
```bash
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh | bash
```

**Hetzner CX22 (x86_64, creates 2 GB swap automatically):**
```bash
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh | bash
```

Both scripts are idempotent; re-run to update. Secrets read from env — never baked in.

## Codespaces / Devcontainer

1. Open the repo in Codespaces (or VS Code "Reopen in Container").
2. The devcontainer builds. `post-create.sh` runs `scripts/install.sh` non-interactively.
3. Open a terminal: `claude`
4. The overlay is at `~/.claude/`. Project-level MCP: copy `.mcp.json.template` to a project root as `.mcp.json`.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `CLAUDE_HOME` | `$HOME/.claude` | Target overlay dir |
| `CLAUDE_INSTALL_NONINTERACTIVE` | `0` | Skip prompts |
| `CLAUDE_INSTALL_OPTIONALS` | `tresor,lsp,mcp` | Comma list |
| `USER_EMAIL` | git config or `you@example.com` | Substituted into `CLAUDE.md` |
| `USER_NAME` | git config or `developer` | Substituted into `CLAUDE.md` |

## Optional components

| Component | What it installs |
|-----------|-----------------|
| `tresor` | Prompt templates + standards into `$CLAUDE_HOME/tresor-resources/` (bundled, idempotent) |
| `lsp` | pyright, typescript-language-server, csharp-ls, gopls, rust-analyzer |
| `mcp` | Prints MCP template path (npx-based servers, no install) |
| `serena` | github.com/oraios/serena semantic MCP via uv/pip |
| `gstack` | gstack overlay namespaced as `/gstack-*` |
| `claude-skills` | github.com/alirezarezvani/claude-skills into `~/claude-skills/` |

## Verify

```bash
./scripts/verify.sh
```

Smoke-tests overlay presence, hook executability, sanitization invariants, and claude CLI availability.

## Update

```bash
git pull
./scripts/install.sh   # Idempotent; backs up existing overlay before rewriting.
```

Previous overlay is preserved at `$CLAUDE_HOME.bak-<timestamp>` per install.
