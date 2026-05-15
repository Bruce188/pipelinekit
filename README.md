# claude-portable

Portable, sandbox-ready Claude Code overlay. Pull repo → one-command install → working multi-agent pipeline with MCP fleet, LSP stack, gstack overlay, TDD-aware `/pipeline`.

## Quick start

### GitHub Codespaces (recommended)
```
# 1. Open repo in Codespaces. Devcontainer post-create runs install automatically.
# 2. Open a terminal:
claude
# 3. Tell Claude:  "Install claude-portable from this repo."
```

### Local (any Linux / WSL / macOS bash)
```
git clone https://github.com/<you>/claude-portable.git
cd claude-portable
./scripts/install.sh
```

`install.sh` is idempotent. Run again to update.

### Pull with a prompt (existing Claude Code session)
```
"Clone https://github.com/<you>/claude-portable.git into ~/work,
 cd into it, and run ./scripts/install.sh non-interactively."
```

## What you get

| Layer | Contents |
|-------|----------|
| Rules | `CLAUDE.md`, `rules/workflow.md`, `rules/agents-worktrees.md` |
| Skills | 25 native (analyze, create-plan, implement-plan, review, ppr, pipeline, ...) |
| Agents | 14 specialized (architect, code-reviewer, security-auditor, tdd-test-writer, ...) |
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
claude-portable/
├── .devcontainer/        # Codespaces / VS Code devcontainer
├── claude/               # Overlay installed to ~/.claude/
│   ├── CLAUDE.md.template
│   ├── rules/
│   ├── skills/           # 25 native skills
│   ├── agents/           # 14 specialized agents
│   ├── hooks/            # 21 production hooks
│   ├── memory/           # Scaffold (empty by design)
│   ├── tresor-resources/ # Prompt templates + standards
│   └── config/
├── scripts/
│   ├── install.sh        # Idempotent installer
│   └── verify.sh         # Smoke test the install
├── docs/
│   ├── installation.md
│   └── pipeline.md
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

## Omissions (by design)

- No `orchestrate.sh` (subprocess pipeline driver). The in-process `/pipeline` skill is the only entry point.
- No `claude -p` subprocess invocations.
- No personal data (paths templated, memories stripped, email scrubbed).
- No marketplace plugin auto-install (use `claude plugin install` after setup if wanted).

## License

MIT. See `LICENSE`.
