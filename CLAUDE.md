# pipelinekit

Small Claude Code config kit: guard hooks, permission rules, global git hooks, a few skills, an installer.
Project-specific rules only; user-global rules live in `~/.claude/CLAUDE.md`.

## Map

| Path | Purpose |
|------|---------|
| `claude/hooks/` | Claude Code guard hooks (`bash-guard.py`, `block-bare-repo-markers.py`, `post-edit-format.sh`) and `kitlog.py`, the event log they and the git hooks write to; tests for these and the git hooks in `claude/hooks/tests/` |
| `claude/git-hooks/` | Global git hooks (`commit-msg`, `pre-commit`, `pre-push`) installed to `~/.claude/git-hooks` |
| `claude/skills/` | `dotnet-conventions`, `deploy`, `exchange-api-keys`, `docs-writer`, `mobile`, `kit` (self-check: `check.py`, tests in `claude/skills/kit/tests/`), `ship` (test, fix and merge your own pull request: `ship.py`, tests in `claude/skills/ship/tests/`) |
| `claude/config/never-stage.txt` | Paths `bash-guard.py` refuses to stage |
| `claude/config/settings.template.json` | Hooks, permissions, env and attribution merged into `~/.claude/settings.json` |
| `claude/CLAUDE.md.template` | Rendered to `~/.claude/CLAUDE.md` by the installer |
| `scripts/install.sh` | In-place overlay into `~/.claude`, settings merge, global git hooks, serena registration |
| `scripts/verify.sh` | Post-install checks: runs `claude/skills/kit/check.py`, then greps for personal paths |
| `tests/test_install.sh` | Installer test in a throwaway HOME |
| `docs-source/` | Markdown sources for the docs site |
| `documentation/` | Rendered HTML docs; regenerate with `python3 claude/skills/docs-writer/render.py` |

## Rules

- Hooks stay stdlib-only (bash, python3); no new runtime deps.
- Every hook change runs its test in `claude/hooks/tests/`.
- A refusal carries a rule id (`group.name`) and is logged through `kitlog.py`, never with the command text. Every id is listed in `docs-source/components.md`; a test holds that.
- Installer changes run `bash tests/test_install.sh`.
- Self-check changes run `python3 -m pytest -q claude/skills/kit/tests`. A new hook or skill goes into the lists at the top of `check.py`, with a live probe for a hook.
- Changes to the ship skill run `python3 -m pytest -q claude/skills/ship/tests`. `ship.py` gets no way past a review or branch protection (no `--admin`); a test holds that.
- Never commit personal paths; `scripts/verify.sh` greps for leaks.
