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

You can safely run the installer again. To update, run `git pull` and then run the installer again, or type `/kit update` in a session: it lists the new commits, asks, and then does both.

Start a new session after the install: Claude Code loads agents when a session starts, and the installer's last line says so. In Claude Code Desktop, ask the new session "which agents can you start?"; the answer names `kit-planner`, `kit-builder` and `kit-judge`.

## What the installer does

1. Copies the hooks, the global git hooks, the nine skills, the three agents (`kit-planner`, `kit-builder`, `kit-judge`) and `config/never-stage.txt` into `~/.claude`. It overwrites those files in place and never moves or deletes the directory. It leaves `projects/`, `sessions/`, `plugins/` and your credentials alone.
   The kit owns the folder `~/.claude/skills/frontend-design`: a copy of your own under that name is moved to `~/.claude/pipelinekit/backup/` once. The installer prints the folder it moved it to; a link of that name is removed, and the folder it points to is left alone.
   In `~/.claude/agents/` the kit owns only its three files. A file of your own with one of those names that differs from the kit's, and that the last install did not put there, is moved to `~/.claude/pipelinekit/backup/` once, and the installer prints where. Your edit of the kit's own copy is replaced without a backup. A link of that name is removed, and the file it points to is left alone. Other agents in the folder are not touched.
2. Removes skills, hooks and the `docs-writer` agent that earlier 0.1.0 builds installed (`commit-conventions`, `security-conventions`, `expo`, `ios`, the old guard hooks), but only if each is still byte-identical to a committed kit version. Edited copies are kept, with a warning.
3. Renders `~/.claude/CLAUDE.md` from `claude/CLAUDE.md.template`. If the result differs from your existing file, the old one is saved as `CLAUDE.md.bak-<timestamp>`. When the old file held a `Judge loop:`, `Judge rounds:` or `Judges:` line, the installer names it and the backup: add it again, or put it in the project's `CLAUDE.md`.
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
| `CLAUDE_HOME` | `~/.claude` | Install target. Another target is written into the `judge-loop` and `ship` skills; see [The judge loop](#the-judge-loop) |
| `USER_NAME`, `USER_EMAIL` | your global git identity | Identity written into `CLAUDE.md` |
| `SERENA_REF` | pinned SHA | serena commit to install |
| `SERENA_ALLOW_ROLLING=1` | off | Allow `SERENA_REF=main` (not recommended) |

## The judge loop

The `judge-loop` skill plans and builds a change on Opus and has fresh Fable judges score both; see [Plan, build, judge](components.html#plan-build-judge).

- **Models.** The loop needs both a Fable and an Opus model. An account without one gets a one-line stop when an agent cannot start; put `Judge loop: off` in the project's `CLAUDE.md` to turn the rule off there.
- **Switch lines.** `Judge loop: off`, `Judge rounds: N` and `Judges: ...` belong in the project's `CLAUDE.md` (or `.claude/CLAUDE.md`) on its base branch. The same lines in `~/.claude/CLAUDE.md` work only until the next install replaces that file.
- **Another `CLAUDE_HOME`.** The skill names `loop.py` by its path. With `CLAUDE_HOME` set to another folder, the installer writes that folder into the installed `SKILL.md`, as long as it is an absolute path that holds only letters, digits and `. _ / @ + -`; otherwise it warns, and the skill keeps `~/.claude`. Keep `CLAUDE_HOME` set in the environment the session runs in; the helper reads the user-level switch lines from `$CLAUDE_HOME/CLAUDE.md`, else from `~/.claude/CLAUDE.md`.
- **Permissions.** The session writes one answer file per judge with the Write tool. In the default permission mode each write may ask; "allow edits for this session" avoids one prompt per file.
- **The record.** A loop keeps its record in `docs/loops/` of the checkout or worktree it runs in. A build in another worktree needs the plan loop's folder (`docs/loops/<name>/plan/`) copied there first. `docs/loops/` is not committed, so work judged in one checkout and shipped from another must be judged again there, or recorded there with `loop.py skip --reason ...`. Nothing removes old loop folders: delete one once its work is merged.
- **The merge gate.** `ship.py` merges only once its `judged` gate holds (see [Shipping a pull request](components.html#shipping-a-pull-request)). It reads the branch's build record and does not run the loop. Its limits: the record says results were saved, not that a judge ran or judged well, and the session can write or remove it; `accept`, `settle`, `skip` and `--user-ok` rest on the session's word, like `ship.py record --tester session`. A build needs no plan loop, and commits after the judged one are covered by the acceptance test; the panel and the size are taken once, at `start`, and the pass reason shows the size since the judged commit. The user-level `Judge loop: off` is a local file the session can edit and no permission rule of the kit guards; the pass reason names where the line stands. The agent files, the role files and `loop.py` are local files as well: a session can edit them without a prompt, and only `/kit` shows it, under "Changes since install". After an update to this version, an open branch without a record shows `judged FAIL no judge record ...`; work built before the update is recorded with `loop.py skip --reason "built before the judge loop" --user-ok`, after asking the user.
- **Agents load at session start.** After an install, start a new session so `kit-planner`, `kit-builder` and `kit-judge` show in the agent list. Where they do not show, the skill starts general-purpose agents with the same models and the installed agent text (`--agents fallback`), and `loop.py start` says so: "fallback: the judge is not limited to reading by its tools".

## Issue links

GitHub closes an issue when a pull request that names it after a closing keyword merges into the default branch, and only then. A pull request into any other branch, a stacked one into `feat/12-base` for example, merges without closing its issue. `ship.py` has a `linked` gate for this (see [Shipping a pull request](components.html#shipping-a-pull-request)) and follows up the issues after a merge.

- **Where the issue numbers come from.** The number in the branch name (`<type>/<issue#>-<slug>`, so `feat/260-issue-links` is #260) and every issue the pull request body names after `Close`, `Closes`, `Closed`, `Fix`, `Fixes`, `Fixed`, `Resolve`, `Resolves` or `Resolved`, or after a word that looks like a misspelt one (`Closing #4`, `Fixs #4`). Text inside HTML comments, inline code and fenced code blocks does not count, as GitHub ignores keywords there.
- **Part of an issue.** A pull request that does only part of its branch's issue says `Part of #N` or `Refs #N` instead of `Closes #N`. The gate passes and says that this merge does not close the issue, and the helper carries no `Closes` line for it to the release pull request.
- **One keyword per issue.** `Closes #1, #2` and `Fixes #1 and #2` close only #1. Write each issue on a line of its own: `Closes #1`, then `Closes #2`.
- **Into the default branch.** The gate passes when GitHub lists every issue named among the issues the pull request closes (`gh pr view --json closingIssuesReferences`), and otherwise fails with the reason for each issue: no keyword, a misspelt one, an issue listed after another, or an issue GitHub does not list. After the merge the helper reads each issue again for up to 15 seconds, as GitHub closes issues in a background job, and names those still open with the commands to check and close them.
- **Into another branch.** A misspelt keyword fails the gate here too, so that no `Closes` line goes to the release pull request for an issue the body did not close. Otherwise the gate passes and says that GitHub will not close the issues on this merge, and names the open release pull request from that branch into the default one, if there is one. After the merge the helper adds one `Closes #N` line per issue to that release pull request when your GitHub account opened it, keeping its text and skipping lines it already has. When someone else opened it, or none is open yet, the helper prints the lines to add. It never merges, approves or marks the release pull request ready.
- **Limits.** Only issues of the same repository are followed. An issue linked by hand in the sidebar is not asked for. A pull request that names no issue at all passes. When GitHub cannot answer, the gate fails with the reason and nothing merges; a failure after the merge is printed, and the merge stands.

## Up to date with the base

A branch is tested and judged as it will merge, so it first takes in what landed on its base. The base is the branch its pull request targets, which is not always `main`: a stacked pull request into `feat/12-base` is compared with `origin/feat/12-base`.

- **The rule.** Before a pull request is written up or updated, Claude fetches and brings the branch up to date with that base. A branch that was never pushed is rebased onto it (`git rebase origin/<base>`). A branch that counts as pushed (below) gets the base merged in (`git merge origin/<base>`), so its published commits are never rewritten. Nothing is ever force pushed. Then the tests run again, before the pull request text is written. The `CLAUDE.md` template, the `ship` and `judge-loop` skills and the `kit-builder` agent state the rule in the same words.
- **What `ship.py` checks.** The `up-to-date` gate fetches the base from the remote, counts the commits the branch lacks and names the next command: `1 commit behind origin/main: the branch was never pushed: git rebase origin/main, run the tests again, then git push -u origin <branch>`, or for a pushed branch `git merge origin/main (no rebase, no force push)`. It also fails on a conflict GitHub reports. `ship.py` never rebases, merges or pushes to fix this itself.
- **Blocking.** While the gate fails, the `ship` skill does not start the acceptance test, `ship.py record --result pass` refuses to record a pass, and `ship.py merge` refuses to merge. When the base cannot be checked (a failed fetch or `gh` call), `record` refuses too, and runs again once it can, with no new test.
- **Before there is a pull request.** The base is `--base BRANCH` (`ship.py status --base feat/12-base`), else `branch.<name>.gh-merge-base`, which `gh pr create` reads too, else the repository's default branch. A pull request's own base always wins.
- **Pushed or not.** A branch counts as pushed when it has a pull request, a remote branch of the same name (fetched here or only on the remote), an upstream of the same name, or a judge record on the branch (a build loop record that names one of its commits); an upstream on another branch does not count. A judge record counts because its results cite the branch's commits: a rebase would void them and cost a new judge loop. `git switch -c feat origin/main` sets `origin/main` as the upstream of a branch that was never pushed.
- **After the update.** A judge-loop result stays valid across a merge; a skip names one commit, so after a merge or a rebase record the skip again with `loop.py skip`.
- **Limits.** A conflict is the session's to resolve: it says so in the pull request, and stops and asks when the conflict cannot be resolved safely. A base that moves after the test makes the gate fail again.

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

The script checks that the kit's hooks, git hooks, skills and agents are present, that `kit-judge.md` may only read (`Read, Grep, Glob`), that each hook starts when it is run the way Claude Code runs it, that every hook command in `settings.json` points to a file that exists, that attribution is off, and that the secret deny rules are in place. It reports whether the global `core.hooksPath` points at the kit and whether `gitleaks` is installed.
