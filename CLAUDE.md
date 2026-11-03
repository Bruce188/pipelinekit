# pipelinekit

Small Claude Code config kit: guard hooks, permission rules, global git hooks, a few skills, an installer.
Project-specific rules only; user-global rules live in `~/.claude/CLAUDE.md`.

## Map

| Path | Purpose |
|------|---------|
| `claude/hooks/` | Claude Code guard hooks (`bash-guard.py`, `block-bare-repo-markers.py`, `post-edit-format.sh`); tests for these and the git hooks in `claude/hooks/tests/` |
| `claude/git-hooks/` | Global git hooks (`commit-msg`, `pre-commit`, `pre-push`) installed to `~/.claude/git-hooks` |
| `claude/skills/` | `dotnet-conventions`, `deploy`, `exchange-api-keys`, `docs-writer`, `mobile` |
| `claude/config/never-stage.txt` | Paths `bash-guard.py` refuses to stage |
| `claude/config/settings.template.json` | Hooks, permissions, env and attribution merged into `~/.claude/settings.json` |
| `claude/CLAUDE.md.template` | Rendered to `~/.claude/CLAUDE.md` by the installer |
| `scripts/install.sh` | In-place overlay into `~/.claude`, settings merge, global git hooks, serena registration |
| `scripts/verify.sh` | Post-install checks |
| `tests/test_install.sh` | Installer test in a throwaway HOME |
| `docs-source/` | Markdown sources for the docs site |
| `documentation/` | Rendered HTML docs; regenerate with `python3 claude/skills/docs-writer/render.py` |

## Rules

- Hooks stay stdlib-only (bash, python3); no new runtime deps.
- Every hook change runs its test in `claude/hooks/tests/`.
- Installer changes run `bash tests/test_install.sh`.
- Never commit personal paths; `scripts/verify.sh` greps for leaks.
