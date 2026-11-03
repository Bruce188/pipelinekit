---
diataxis: how-to
---

# Installation

Install pipelinekit into `~/.claude`, or another `CLAUDE_HOME`, by running one script.

## Requirements

- `bash`, `git` and `python3`
- `uv`, only if you want serena (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Install

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
bash scripts/install.sh            # add --no-serena to skip serena
```

You can safely run the installer again. To update, run `git pull` and then run the installer again.

## What the installer does

1. Copies the hooks, the seven skills, the `docs-writer` agent and `config/never-stage.txt` into `~/.claude`. It overwrites those files in place and never moves or deletes the directory. It leaves `projects/`, `sessions/`, `plugins/` and your credentials alone.
2. Renders `~/.claude/CLAUDE.md` from `claude/CLAUDE.md.template`. If the result differs from your existing file, the old one is saved as `CLAUDE.md.bak-<timestamp>`.
3. Backs up `settings.json`, then merges in the kit's hook wiring. It removes hook entries whose script is no longer in `~/.claude/hooks/`. It also sets `attribution` to empty strings, so commits and PRs get no co-author trailer or footer. Other settings stay as they are.
4. Installs serena with `uv` at a pinned commit and registers it at user scope in `~/.claude.json`. It backs that file up first.
5. Installs `commit-msg` and `pre-commit` git hooks in the pipelinekit repo itself. Any existing hooks are renamed to `*.pre-pipelinekit.<timestamp>`.
6. Runs `scripts/verify.sh`.

## Options

| Variable / flag | Default | Purpose |
|-----------------|---------|---------|
| `--no-serena` / `CLAUDE_INSTALL_SKIP_SERENA=1` | off | Skip installing and registering serena |
| `CLAUDE_HOME` | `~/.claude` | Install target |
| `USER_NAME`, `USER_EMAIL` | your global git identity | Identity written into `CLAUDE.md` |
| `SERENA_REF` | pinned SHA | serena commit to install |
| `SERENA_ALLOW_ROLLING=1` | off | Allow `SERENA_REF=main` (not recommended) |

## Optional: context7

context7 is not installed by default. To use it in a project, copy its entry from `.mcp.json.template` into that project's `.mcp.json`. The template also shows how to pin serena for a single project, and it includes optional iOS MCP servers.

## Devcontainer and cloud VMs

- The devcontainer in `.devcontainer/` runs the installer non-interactively when the container is created.
- `scripts/cloud/` has bootstrap scripts and cloud-init files for Oracle Cloud and Hetzner VMs.

## Check the install

```bash
bash scripts/verify.sh
```

The script checks that the kit's hooks and skills are present, that every hook command in `settings.json` points to a file that exists, and that attribution is off.
