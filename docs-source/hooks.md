---
diataxis: reference
---

# Hooks and rule ids

This page lists the permission rules, guard hooks and git hooks that pipelinekit v0.1.0 installs, and the rule id of every refusal.

## Guard hooks and permissions

The installer merges `claude/config/settings.template.json` into `~/.claude/settings.json`. The hook scripts live in `~/.claude/hooks/`.

| Piece | Where | What it does |
|------|-------|--------------|
| `permissions.deny` | settings | Claude can't read or edit `.env*` (not `.env.example`), keys, `~/.ssh`, `~/.aws`, `~/.kube/config`, `~/.config/gh/hosts.yml`, credentials files. Holds in bypass mode |
| `permissions.ask` | settings | Prompts before editing Claude settings/hooks or `~/.gitconfig`, and before `reset --hard`, `clean -f`, force push, `branch -D`, `checkout/restore .`, `gh pr merge --admin`. Prompts in bypass mode too |
| `bash-guard.py` | PreToolUse `Bash` (`if`: git, docker, podman, curl, wget, psql, mysql, mariadb, sqlite3) | Blocks pushes to other remotes or main, remote changes, global git config writes, hook bypasses (`--no-verify`, `core.hooksPath`), staging `config/never-stage.txt` paths or bulk staging, sensitive docker mounts, and `curl \| sh`. Asks before `docker --privileged` and DROP/TRUNCATE |
| `block-bare-repo-markers.py` | PreToolUse `Edit\|Write` | Blocks assembling a bare git repo (HEAD + config/objects/refs) in the working directory or one level down |
| `post-edit-format.sh` | PostToolUse `Edit\|Write` | Runs the project's own prettier on ts/js/json/yaml |
| `session-check.py` | SessionStart `startup` | Runs the self-check in quick mode when a session starts. Says nothing when the install is healthy, otherwise one line with the number of problems that names `/kit`. Never blocks a session. `PIPELINEKIT_SESSION_CHECK=0` switches it off |

<details markdown="1">
<summary>How deny and ask behave in bypassPermissions mode</summary>

- `permissions.deny` blocks in every mode, bypass included. Rules are evaluated deny, then ask, then allow.
- Explicit `permissions.ask` rules still prompt in bypass mode. `allow` rules have no effect there.
- Bypass mode does not prompt for the built-in protected paths (`.git`, `.claude`, `.gitconfig`), so the template adds explicit `ask` rules for Claude's settings, hooks, git hooks and config, `~/.gitconfig` and `.git/hooks/**`.
- A hook that exits 2 blocks in every mode. Destructive git commands use native ask rules rather than hook asks.
- Read/Edit deny rules also stop `cat`, `head`, `sed`, `tee` and redirects in Bash, but not `python -c open(...)` or MCP tools. Only the sandbox closes that.
- `.env.example`, `.env.sample` and `.env.template` are carved out with `!` rules. Outside the current directory only an exact `.env` is denied.

</details>

### The never-stage list

`config/never-stage.txt` is the single list of paths that must not be committed. It is gitignore-style, with `!` negation, and covers env files, credentials, keys, and the local `docs/` workflow notes. `bash-guard.py` reads it. Edit the copy in `~/.claude/config/` to change it for your machine. The installer overwrites that copy on the next run, so put changes you want to keep in the repo's `claude/config/never-stage.txt`.

## Git hooks

`claude/git-hooks/` is installed to `~/.claude/git-hooks` and, if you agree, set as the global `core.hooksPath`. Each hook runs the repository's own `.git/hooks/<name>` or `.githooks/<name>` afterwards. `pre-merge-commit` runs `.githooks/pre-merge-commit` only when it is the executable file the current commit has: the merge has already written the incoming files, so a merge never runs a hook it brings in.

| Hook | What it does |
|------|--------------|
| `commit-msg` | Conventional commits (`feat fix refactor docs test chore perf style build ci revert`, scopes, `!`). Rejects wip (outside `.claude/worktrees/`), AI attribution and emoji. Lets `Merge`, `Revert "`, `fixup!`/`squash!`/`amend!` through |
| `pre-commit` | `gitleaks` scan of staged changes. Warns and allows if gitleaks is missing. `PIPELINEKIT_ALLOW_SECRET=1` skips one commit. Then the [file size limit](#file-size-limit) |
| `pre-merge-commit` | Run by `git merge` before it records a merge it made without conflicts, which skips `pre-commit`: the same [file size limit](#file-size-limit) on the merged files |
| `pre-push` | Refuses pushes to `main`/`master`. `ALLOW_MAIN_PUSH=1` overrides (humans only; bash-guard refuses it for Claude) |

A repo with its own local `core.hooksPath` (husky, the pre-commit framework, or a manual setting) bypasses these. Run `git config --show-origin core.hooksPath` inside it to check.

### File size limit

`pre-commit` and `pre-merge-commit` refuse a commit or a merge that adds a hand-written file over 1,500 lines or 50,000 bytes, or takes one past that; a file already over the limit only warns. It leaves out generated, vendored, lock and data files, and the project and designer files an IDE writes. [File size limit](file-size.html) says what is counted, which files are exempt by default and how a project exempts more.

## Rule ids and the event log

Every refusal ends with the id of its rule in square brackets, for example `BLOCKED: git commit --no-verify skips the git hooks [git.no-verify]`. The hooks also record each block, ask, override and error in an event log, and `/kit` reads it back under Activity (see [Self-check](self-check.html)).

The log is `~/.local/state/pipelinekit/events.jsonl`. `$XDG_STATE_HOME` moves it as usual, and `PIPELINEKIT_STATE_DIR` names the directory outright. One line per event holds the time, the hook, the kind, the rule id, the hook's reason and, when known, the session and the working directory. The command text is never written. A reason can name the path, the branch or the name of the remote it is about. A push to a URL is recorded without the URL, and what a URL in any other reason can carry as a secret (a user and password, a query string, a fragment) is removed first, and so are control and direction characters. Only you can read the file (mode 600). At 1 MB it moves to `events.jsonl.1`, so there are never more than two files. `PIPELINEKIT_LOG=0` switches the log off. A log that cannot be written never changes what a hook decides.

| Rule id | Hook | Kind | When |
|---------|------|------|------|
| `parse.unparsable` | `bash-guard` | block | The command could not be parsed, for example unbalanced quotes |
| `git.no-verify` | `bash-guard` | block | `--no-verify`, or `git commit -n` |
| `git.hookspath-option` | `bash-guard` | block | `git -c core.hooksPath=...` |
| `git.config-hookspath` | `bash-guard` | block | Changing `core.hooksPath`, also through a `GIT_CONFIG_*` variable |
| `git.config-global` | `bash-guard` | block | A write with `git config --global` or `--system` |
| `git.override-variable` | `bash-guard` | block | Setting a human-only override such as `ALLOW_MAIN_PUSH` |
| `git.remote-change` | `bash-guard` | block | `git remote add` or `git remote set-url` |
| `git.push-remote` | `bash-guard` | block | A push to a remote other than `origin` |
| `git.push-protected` | `bash-guard` | block | A direct push to `main` or `master` |
| `git.push-all` | `bash-guard` | block | `git push --all`, `--mirror` or `--branches` |
| `git.never-stage` | `bash-guard` | block | Staging or committing a path on the never-stage list |
| `git.never-stage-missing` | `bash-guard` | block | The never-stage list is missing, so nothing is staged |
| `git.bulk-staging` | `bash-guard` | block | `git add -A`, `git add .`, `git commit -a` and other bulk staging |
| `git.add-expansion` | `bash-guard` | block | A `git add` path with `$` or a backtick in it |
| `git.pathspec-file` | `bash-guard` | block | `--pathspec-from-file` on `git add` or `git commit` |
| `docker.mount-sensitive` | `bash-guard` | block | A mount of a sensitive host path such as `/etc` |
| `docker.mount-variable` | `bash-guard` | block | A mount source with an unresolved variable |
| `docker.privileged` | `bash-guard` | ask | `docker run --privileged` |
| `fetch.pipe-to-shell` | `bash-guard` | block | A download piped into a shell or interpreter |
| `fetch.substitution` | `bash-guard` | block | Downloaded code run through substitution, as in `bash -c "$(curl ...)"` |
| `fetch.process-substitution` | `bash-guard` | block | Downloaded code run through process substitution, as in `bash <(curl ...)` |
| `sql.destructive` | `bash-guard` | ask | `DROP` or `TRUNCATE` sent to a database client |
| `bare-repo.marker` | `block-bare-repo-markers` | block | A file that would complete a bare git repository |
| `input.invalid` | `bash-guard`, `block-bare-repo-markers` | error | The hook got input it could not read |
| `internal.crash` | `bash-guard`, `block-bare-repo-markers` | error | The hook itself failed, so the command was not checked |
| `session-check.timeout` | `session-check` | error | The session-start check took longer than 4 seconds and was dropped |
| `session-check.failed` | `session-check` | error | The session-start check could not run: `check.py` is missing or gave no report |
| `commit-msg.format` | `commit-msg` | block | The subject is not a conventional commit |
| `commit-msg.subject-length` | `commit-msg` | block | The subject is longer than 100 characters |
| `commit-msg.wip` | `commit-msg` | block | A wip commit outside `.claude/worktrees/` |
| `commit-msg.ai-attribution` | `commit-msg` | block | An AI attribution line in the message |
| `commit-msg.emoji` | `commit-msg` | block | An emoji in the message |
| `pre-commit.secret` | `pre-commit` | block | gitleaks found a secret in the staged changes |
| `pre-commit.gitleaks-failed` | `pre-commit` | error | gitleaks itself failed |
| `pre-commit.allow-secret` | `pre-commit` | override | `PIPELINEKIT_ALLOW_SECRET=1` skipped the scan |
| `pre-commit.file-size` | `pre-commit`, `pre-merge-commit` | block | The commit or merge adds a file over the [file size limit](file-size.html) or takes one past it |
| `pre-commit.file-size-over` | `pre-commit`, `pre-merge-commit` | warning, not logged | A file already over the limit changed; the commit or merge goes on |
| `pre-commit.file-size-exempt-local` | `pre-commit`, `pre-merge-commit` | override | A file over the limit passes only because the unstaged `.file-size-exempt` in the working tree lists it |
| `pre-commit.file-size-failed` | `pre-commit`, `pre-merge-commit` | error | The file size check failed, so file sizes were not checked |
| `pre-push.protected-branch` | `pre-push` | block | A push to `main` or `master` |
| `pre-push.allow-main` | `pre-push` | override | `ALLOW_MAIN_PUSH=1` let such a push through |

With `ask`, Claude Code prompts you instead of refusing. `warning, not logged` means the hook prints a warning and lets the commit or merge go on, with nothing in the event log. `override` means a human-only variable let something through. `error` means the hook could not do its job: a guard hook then refuses the command or commit, while the session-start check and the file size check step aside and let it through.

