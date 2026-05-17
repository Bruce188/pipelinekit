# pipelinekit

Portable, sandbox-ready Claude Code overlay. Pull repo → one-command install → working multi-agent pipeline with MCP fleet, LSP stack, gstack overlay, TDD-aware `/pipeline`.

## Quick start

### Local (any Linux / WSL / macOS bash)
```
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
./scripts/install.sh
```

`install.sh` is idempotent. Run again to update.

### Cloud cold-start (Oracle / Hetzner)

Bootstrap a fresh cloud VM and install pipelinekit in one step. See [docs/cloud-setup.md](docs/cloud-setup.md) for the full walkthrough.

**Oracle Cloud Free Tier ARM A1 (aarch64, 24 GB RAM):**
```bash
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/oracle-bootstrap.sh | bash
```

**Hetzner CX22 (x86_64, 4 GB RAM — swap created automatically):**
```bash
curl -fsSL https://raw.githubusercontent.com/Bruce188/pipelinekit/main/scripts/cloud/hetzner-bootstrap.sh | bash
```

Both scripts are idempotent: re-run to update. Secrets are read from env — never baked in. See [scripts/cloud/](scripts/cloud/) for source and cloud-init YAMLs.

### GitHub Codespaces
```
# 1. Open repo in Codespaces. Devcontainer post-create runs install automatically.
# 2. Open a terminal:
claude
# 3. Tell Claude:  "Install pipelinekit from this repo."
```

### Pull with a prompt (existing Claude Code session)
```
"Clone https://github.com/Bruce188/pipelinekit.git into ~/work,
 cd into it, and run ./scripts/install.sh non-interactively."
```

## What you get

| Layer | Contents |
|-------|----------|
| Rules | `CLAUDE.md`, `rules/workflow.md`, `rules/agents-worktrees.md` |
| Skills | 34 native (analyze, create-plan, implement-plan, review, ppr, pipeline, expo, ios, azure-ops, document-release, tdd, zoom-out, write-a-skill, ...) |
| Agents | 15 specialized (architect, code-reviewer, security-auditor, tdd-test-writer, mobile-dev, azure-deployment-engineer, ...) |
| Hooks | 21 production hooks (validate-commit-msg, strip-ai-attribution, block-push-main, tdd-order-check, ...) |
| MCP | context7, serena (semantic), sequential-thinking, optional local-rag |
| LSP | pyright, typescript, csharp, gopls, rust-analyzer |
| Templates | tresor-resources (prompts, standards, examples) |
| Optional | gstack overlay (`/gstack-*` skills) and `~/claude-skills/` via setup flags |

## Pipeline modes

`/pipeline` routes per feature based on `<type>/<name>` prefix in `docs/features.md`:

| Prefix | Mode | TDD |
|--------|------|-----|
| `feat`, `fix`, `refactor`, `perf`, `test` | dev | yes — tdd-test-writer → tdd-implementer |
| `docs`, `chore`, `style`, `build`, `ci`, `content`, `ops`, `research` | non-dev | skipped |

Override with `**Type:** dev|non-dev` per-feature line in `docs/features.md`.

## Layout

```
pipelinekit/
├── .devcontainer/        # Codespaces / VS Code devcontainer
├── claude/               # Overlay installed to ~/.claude/
│   ├── CLAUDE.md.template
│   ├── rules/
│   ├── skills/           # 34 native skills
│   ├── agents/           # 15 specialized agents
│   ├── hooks/            # 21 production hooks
│   ├── memory/           # Scaffold (empty by design)
│   ├── tresor-resources/ # Prompt templates + standards
│   ├── lib/sandbox/      # Pluggable SandboxProvider (worktree-only default, podman, docker)
│   └── config/
├── scripts/
│   ├── install.sh        # Idempotent installer
│   └── verify.sh         # Smoke test the install
├── docs/
│   ├── installation.md
│   └── pipeline.md
├── documentation/        # Application docs (API refs, user guides, architecture) — committed
├── .mcp.json.template    # MCP server config (copied to project root on install)
├── LICENSE               # MIT
└── README.md
```

## Caveman mode (wenyan-ultra)

Default verbosity: caveman wenyan-ultra. Drops articles, filler, hedging. Code/commits/security remain normal English.

Toggle in-session:
```
/caveman lite | full | ultra
stop caveman     # revert to normal
```

## Memory

Memory ships as an empty scaffold. After install, Claude builds memory in `~/.claude/projects/<project-slug>/memory/`. See `claude/memory/MEMORY.md` for schema reference.


## License

MIT. See `LICENSE`.
