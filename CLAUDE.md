# pipelinekit

Small Claude Code config kit: guard hooks, a few skills, one agent, an installer.
Project-specific rules only; user-global rules live in `~/.claude/CLAUDE.md`.

## Map

| Path | Purpose |
|------|---------|
| `claude/hooks/` | Guard hooks (bash + python) and their tests in `claude/hooks/tests/` |
| `claude/skills/` | `commit-conventions`, `security-conventions`, `dotnet-conventions`, `deploy`, `docs-writer`, `expo`, `ios` |
| `claude/agents/` | `docs-writer.md` |
| `claude/config/never-stage.txt` | Paths `block-stage-sensitive.sh` refuses to stage |
| `claude/CLAUDE.md.template` | Rendered to `~/.claude/CLAUDE.md` by the installer |
| `scripts/install.sh` | In-place overlay into `~/.claude`, settings merge, serena registration |
| `scripts/verify.sh` | Post-install checks |
| `tests/test_install.sh` | Installer test in a throwaway HOME |
| `docs-source/` | Markdown sources for the docs site |
| `documentation/` | Rendered HTML docs; regenerate with `python3 claude/skills/docs-writer/render.py` |

## Rules

- Hooks stay stdlib-only (bash, python3); no new runtime deps.
- Every hook change runs its test in `claude/hooks/tests/`.
- Installer changes run `bash tests/test_install.sh`.
- Never commit personal paths; `scripts/verify.sh` greps for leaks.
