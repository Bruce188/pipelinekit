---
diataxis: how-to
---

# Installation

Install pipelinekit into `~/.claude`, or another `CLAUDE_HOME`, by running one script.

## Requirements

- Linux, macOS or WSL 2. Native Windows shells are not supported; see [Claude Code Desktop](#claude-code-desktop)
- `bash`, `git` and `python3`
- `gitleaks`, optional, for the pre-commit secret scan
- `uv`, only if you want serena (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Install

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
bash scripts/install.sh            # add --no-serena to skip serena
```

You can safely run the installer again. To update, run `git pull` and then run the installer again.

## What the installer does

1. Copies the hooks, the global git hooks, the seven skills and `config/never-stage.txt` into `~/.claude`. It overwrites those files in place and never moves or deletes the directory. It leaves `projects/`, `sessions/`, `plugins/` and your credentials alone.
2. Removes skills, hooks and the `docs-writer` agent that earlier 0.1.0 builds installed (`commit-conventions`, `security-conventions`, `expo`, `ios`, the old guard hooks), but only if each is still byte-identical to a committed kit version. Edited copies are kept, with a warning.
3. Renders `~/.claude/CLAUDE.md` from `claude/CLAUDE.md.template`. If the result differs from your existing file, the old one is saved as `CLAUDE.md.bak-<timestamp>`.
4. Backs up `settings.json` to `settings.json.bak-<timestamp>`, then merges in `claude/config/settings.template.json`:
   - the kit's hook entries replace its older ones, and hook entries whose script is no longer in `~/.claude/hooks/` are removed; your own hooks stay;
   - the kit's `permissions.deny` and `permissions.ask` rules are added after yours; `allow` and other permission keys are untouched;
   - `attribution` is set to empty strings, so commits and PRs get no co-author trailer or footer.
5. Asks whether to set the global git `core.hooksPath` to `~/.claude/git-hooks`. It never overwrites an existing value; it prints the command instead. Without a terminal, and without `--git-hooks`, it skips this step.
6. Installs serena with `uv` at a pinned commit and registers it at user scope in `~/.claude.json`. It backs that file up first.
7. Writes `~/.claude/pipelinekit/manifest.json` (version, commit, a hash of every installed file, the kit's `settings.json` entries), then runs `scripts/verify.sh`.

<details markdown="1">
<summary>Repos that set their own core.hooksPath</summary>

A local `core.hooksPath` overrides the global one, so the kit's git hooks never run in that repo. If its hooks directory holds only `*.sample` files, unset it in your own shell (Claude's `bash-guard.py` refuses to change `core.hooksPath`):

```bash
git -C ~/path/to/repo config --local --unset core.hooksPath
git -C ~/path/to/repo config --show-origin core.hooksPath   # expect ~/.gitconfig and ~/.claude/git-hooks
```

Repo-specific hooks go in `<repo>/.git/hooks/<name>` (local) or `<repo>/.githooks/<name>` (committed). The global hooks run them after their own checks.

</details>

## Options

| Variable / flag | Default | Purpose |
|-----------------|---------|---------|
| `--no-serena` / `CLAUDE_INSTALL_SKIP_SERENA=1` | off | Skip installing and registering serena |
| `--git-hooks` / `--no-git-hooks` / `PIPELINEKIT_GIT_HOOKS=1\|0` | ask | Set, or skip setting, the global `core.hooksPath` without a prompt |
| `CLAUDE_HOME` | `~/.claude` | Install target |
| `USER_NAME`, `USER_EMAIL` | your global git identity | Identity written into `CLAUDE.md` |
| `SERENA_REF` | pinned SHA | serena commit to install |
| `SERENA_ALLOW_ROLLING=1` | off | Allow `SERENA_REF=main` (not recommended) |

## Optional: context7

context7 is not installed by default. To use it in a project, copy its entry from `.mcp.json.template` into that project's `.mcp.json`. The template also shows how to pin serena for a single project, and it includes optional iOS MCP servers.

## Devcontainer and cloud VMs

- The devcontainer in `.devcontainer/` runs the installer non-interactively when the container is created.
- `scripts/cloud/` has bootstrap scripts and cloud-init files for Oracle Cloud and Hetzner VMs.

## Claude Code Desktop

The desktop app runs the same Claude Code as the CLI. The kit is active when the session's process reads the `~/.claude` you installed into and can start POSIX scripts, and that depends on the environment you pick for the session.

| Environment | Kit active | What to do |
|-------------|------------|------------|
| Local, on macOS | yes | Nothing: it is the same `~/.claude` as the CLI |
| WSL, on Windows | yes | Install inside the distro, then pick it under **WSL** in the environment selector |
| Local, on Windows | no | Use the WSL environment instead |
| SSH | on the remote | Run the installer on the remote host; the session uses that host's `~/.claude` |
| Cloud | no | The VM starts without your `~/.claude` |

To check a session, type `/kit` in it. The check then runs with that session's PATH and home directory.

### Windows

Install the kit inside WSL 2 and start sessions in the **WSL** environment. The session is then a Linux process with the distro's `~/.claude`, PATH and git, so the hooks, the permission rules and the global git hooks behave as they do in the CLI. Clone the repo with git inside WSL as well.

A **Local** session is a Windows process, even when its folder is a `\\wsl.localhost\<distro>\...` path:

- It reads `%USERPROFILE%\.claude`, not the distro's `~/.claude`, so in most folders none of the kit is loaded. `~/...` permission rules refer to the Windows profile, which leaves `~/.ssh` and the other protected paths inside the distro uncovered.
- If the folder is your WSL home directory, the kit's `settings.json` is picked up as project settings. Windows cannot start the hook scripts, and the `PreToolUse` hooks use `onFailure: "block"`, so every `Edit`, `Write` and guarded `Bash` call is refused with `its program could not be started (ENOENT)`.
- Git for Windows has its own global config. Commits made by a Local session, GitHub Desktop or another Windows tool skip the kit's git hooks.

The installer refuses to run from Git Bash, MSYS or Cygwin for the same reason.

<details markdown="1">
<summary>Hooks fail with python3\r: No such file or directory</summary>

The hook files have CRLF line endings, usually because the repo was checked out with Git for Windows (`core.autocrlf=true`) before `.gitattributes` forced LF. The shebang no longer resolves, the hook cannot start, and the `PreToolUse` hooks block the call. Pull the current version and clone it again with git inside WSL, then run the installer again. `scripts/verify.sh` reports this as `hook does not start`.

</details>

## Check the install

Inside a Claude Code session, type `/kit`. From a shell:

```bash
bash scripts/verify.sh
```

Both run the same checker, `claude/skills/kit/check.py`. Run it after every install or update, and whenever a hook blocks something you did not expect. [Components](components.html#self-check) lists what it checks.

The script checks that the kit's hooks, git hooks and skills are present, that each hook starts when it is run the way Claude Code runs it, that every hook command in `settings.json` points to a file that exists, that attribution is off, and that the secret deny rules are in place. It reports whether the global `core.hooksPath` points at the kit and whether `gitleaks` is installed.
