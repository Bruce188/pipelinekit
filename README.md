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
| Skills | 43 native (analyze, create-plan, implement-plan, review, ppr, pipeline, expo, ios, azure-ops, railway-ops, render-ops, digitalocean-ops, document-release, tdd, zoom-out, write-a-skill, research, learn, landing-report, incident, claude-md-enhancer, ...) |
| Agents | 31 specialized (architect, code-reviewer, security-auditor, karpathy-reviewer, tdd-test-writer, mobile-dev, azure-deployment-engineer, railway-deployment-engineer, render-deployment-engineer, digitalocean-deployment-engineer, deployment-engineer, incident-responder, architect-review, cloud-architect, claude-md-guardian, ...) |
| Hooks | 22 production hooks (validate-commit-msg, strip-ai-attribution, block-push-main, tdd-order-check, claude-md-guard, ...) |
| MCP | context7, serena (semantic), sequential-thinking, optional local-rag, claude-context (community — @zilliztech, codebase semantic RAG; uncomment in `.mcp.json.template` to enable) |
| LSP | pyright, typescript, csharp, gopls, rust-analyzer |
| Templates | tresor-resources (prompts, standards, examples); `documentation/SKILL_PIPELINE.md` + `documentation/SKILL-AUTHORING-STANDARD.md` (vendored skill authoring contract — pair with `/write-a-skill`) |
| Model overlays | 4 (claude.md generic, opus-4-7.md, sonnet-4-6.md, haiku-4-5.md) — per-model token/thinking budget tuning consumed by phase skills |
| Host adapters | 4 (claude.sh concrete, codex.sh/cursor.sh/gemini.sh stubs) — interface scaffold for future multi-host dispatch |
| Third-party | gstack (`/gstack-*` skills) and `~/claude-skills/` — install per upstream READMEs; not bundled by `scripts/install.sh` |

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
│   ├── skills/           # 43 native skills
│   │   ├── railway-ops/  # Railway deployment ops skill
│   │   ├── render-ops/   # Render deployment ops skill
│   │   ├── digitalocean-ops/ # DigitalOcean App Platform ops skill
│   │   └── research/     # Research loop + tsv-viewer.sh
│   ├── agents/           # 31 specialized agents
│   ├── hooks/            # 22 production hooks
│   ├── memory/           # Scaffold (empty by design)
│   ├── tresor-resources/ # Prompt templates + standards
│   ├── lib/sandbox/      # Pluggable SandboxProvider (worktree-only default, podman, docker)
│   │   └── sandbox_wrap.sh # Shared sandbox wrapper (extracted from orchestrate.sh + research-loop.sh)
│   ├── model-overlays/   # Per-model tuning hints (claude.md generic + opus/sonnet/haiku variants)
│   ├── host-adapters/    # Host dispatch interface (claude.sh concrete, others stub)
│   └── config/
├── scripts/
│   ├── install.sh        # Idempotent installer
│   ├── sandbox/          # Container base image build (Containerfile + build.sh)
│   └── verify.sh         # Smoke test the install
├── docs/
│   ├── installation.md
│   └── pipeline.md
├── documentation/        # Application docs (API refs, user guides, architecture) — committed
├── .mcp.json.template    # MCP server config (copied to project root on install)
├── LICENSE               # MIT
└── README.md
```

## Cloud deployment agents

Five deployment-engineer agents cover the full provider matrix. All follow the same pattern: Charter Topic 10 selects the provider; `/pipeline` routes deployment-shaped tasks to the appropriate agent and ops skill automatically.

| Agent | Skill | Provider |
|-------|-------|----------|
| `@azure-deployment-engineer` | `azure-ops` | Azure App Service / Container Apps / Function Apps |
| `@vercel-deployment-engineer` | `vercel-ops` | Vercel |
| `@railway-deployment-engineer` | `railway-ops` | Railway |
| `@render-deployment-engineer` | `render-ops` | Render |
| `@digitalocean-deployment-engineer` | `digitalocean-ops` | DigitalOcean App Platform |

`claude/agents/deployment-engineer.md` is a documentation-only base file describing the shared contract. Each named agent above is a concrete variant that extends it for its provider.

Provider-specific guides live in `documentation/`:
- [Railway](documentation/deployment-railway.html)
- [Render](documentation/deployment-render.html)
- [DigitalOcean](documentation/deployment-digitalocean.html)

## /ppr --research flag

`/ppr` accepts an optional `--research` flag for publishing research keep-rows from a TSV to a dedicated branch. Dry-run by default; pass `--no-dry-run` to publish. The TSV viewer at `documentation/` lets you sort and filter research results in-browser.

```
/ppr --research                     # dry-run (default)
/ppr --research --no-dry-run        # publish research/<tag>-YYYY-MM-DD branch
/ppr --research --research-tag <t>  # custom tag
```

See [documentation/ppr-research-flag.html](documentation/ppr-research-flag.html) for the full reference.

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
