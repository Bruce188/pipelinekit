# pipelinekit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml)

A small Claude Code config kit: guard hooks, a handful of skills, one docs
agent, and an installer that overlays them onto `~/.claude` without touching
anything else there.

Since v0.1.0 the kit no longer ships its own orchestrator, personas, memory
stack, or context-management hooks; current Claude Code covers those natively
(see [CHANGELOG](CHANGELOG.md)).

## What you get

**Hooks** (wired into `settings.json` by the installer)

| Hook | Event | Does |
|------|-------|------|
| `block-dangerous-commands.sh` | PreToolUse Bash | Blocks or asks on risky git, docker and destructive SQL commands |
| `block-push-main.sh` | PreToolUse Bash | Blocks direct pushes to `main`/`master` |
| `block-stage-sensitive.sh` | PreToolUse Bash | Refuses to stage paths in `config/never-stage.txt` |
| `env-scrub.py` | PreToolUse Bash | In CI (or `CLAUDE_CODE_SCRUB_SUBPROCESS=1`), blocks commands that reference secret env vars |
| `validate-commit-msg.sh` | PreToolUse Bash | Enforces conventional commits |
| `pre-edit-protect.sh` | PreToolUse Edit/Write | Blocks edits to `.env`, credentials, keys, Claude settings files |
| `block-bare-repo-markers.py` | PreToolUse Write | Blocks writing bare-repo markers (`HEAD`, `config`, ...) at a repo root |
| `post-edit-format.sh` | PostToolUse Edit/Write | Runs the project's formatter on the edited file |
| `scan-tool-output.sh` | PostToolUse WebFetch/Read | Warns on prompt-injection patterns |

`commit-msg-wrapper.sh` and `scan-secrets-staged.sh` are installed as native git
hooks in this repo.

**Skills:** `commit-conventions`, `security-conventions`, `dotnet-conventions`,
`deploy` (Vercel, Railway, Render, DigitalOcean, Azure), `docs-writer`, `expo`, `ios`.

**Agent:** `docs-writer`.

**MCP:** serena (installed with `uv` at a pinned commit, registered at user
scope). context7 is optional; see `.mcp.json.template`.

## Install

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
bash scripts/install.sh            # --no-serena to skip serena
```

The installer is idempotent. It:

- copies hooks, skills, the agent and `config/never-stage.txt` into `~/.claude` (in place; it never moves the directory),
- renders `~/.claude/CLAUDE.md` from `claude/CLAUDE.md.template` (backs up an existing one),
- merges the hooks above into `~/.claude/settings.json`, drops hook entries whose script no longer exists, and turns commit/PR attribution off; other settings are kept,
- installs and registers serena,
- runs `scripts/verify.sh`.

Identity comes from `USER_NAME` / `USER_EMAIL`, defaulting to your git config.

Cloud bootstrap scripts for Oracle and Hetzner VMs live in `scripts/cloud/`;
the devcontainer runs the installer on create.

## Upgrading from 0.0.x

The installer does not delete files from earlier versions. Remove the dropped
agents, skills, hooks, `rules/`, `modes/` and `model-overlays/` from
`~/.claude` by hand (the list is in the CHANGELOG), then re-run the installer
to prune stale hook entries from `settings.json`.

## Tests

```bash
for t in claude/hooks/tests/test_*.sh; do bash "$t"; done
python3 -m pytest claude/hooks/tests
bash claude/hooks/validate-commit-msg.sh --selftest
bash tests/test_install.sh
bash claude/skills/docs-writer/tests/test_render.sh
```

## License

MIT, see [LICENSE](LICENSE).
