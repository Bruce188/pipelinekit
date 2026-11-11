---
diataxis: reference
---

# Components

This page lists what pipelinekit v0.1.0 installs and what each part does.

> The hooks and skills are still being reviewed, so details may change in later releases. The hooks are guardrails that catch common mistakes. They are not a security boundary, and they do not replace review.

## Overview

The kit has five layers. Hover a chip for a one-line summary, or use the buttons to focus on one layer.

<div data-snippet="architecture-diagram">
<script type="application/json">
{"layers": [
  {"name": "Settings rules", "color": "#ef4444", "count": "settings.json",
   "chips": [{"label": "permissions.deny", "tip": "No reading or editing secrets, keys or credentials"},
             {"label": "permissions.ask", "tip": "Prompt before editing Claude config or destructive git"},
             {"label": "attribution off", "tip": "No co-author trailer or PR footer"}]},
  {"name": "Claude Code hooks", "color": "#f59e0b", "count": "4 scripts",
   "chips": [{"label": "bash-guard.py", "tip": "PreToolUse Bash: git, docker, fetch and SQL rules"},
             {"label": "block-bare-repo-markers.py", "tip": "PreToolUse Edit/Write"},
             {"label": "post-edit-format.sh", "tip": "PostToolUse Edit/Write: prettier"},
             {"label": "session-check.py", "tip": "SessionStart: quick self-check, silent when healthy"}]},
  {"name": "Git hooks", "color": "#3b82f6", "count": "global core.hooksPath",
   "chips": [{"label": "commit-msg", "tip": "Conventional commits, no attribution or emoji"},
             {"label": "pre-commit", "tip": "gitleaks on staged changes"},
             {"label": "pre-push", "tip": "No pushes to main or master"}]},
  {"name": "Skills", "color": "#10b981", "count": "7 skills",
   "chips": [{"label": "dotnet-conventions"}, {"label": "deploy"}, {"label": "exchange-api-keys"},
             {"label": "docs-writer"}, {"label": "mobile"},
             {"label": "kit", "tip": "Self-check, run as /kit"},
             {"label": "ship", "tip": "Test, fix and merge your own pull request"}]},
  {"name": "MCP", "color": "#8b5cf6",
   "chips": [{"label": "serena", "tip": "Installed by default at a pinned commit"},
             {"label": "context7", "tip": "Optional, per project"}]}]}
</script>
</div>

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

`claude/git-hooks/` is installed to `~/.claude/git-hooks` and, if you agree, set as the global `core.hooksPath`. Each hook runs the repository's own `.git/hooks/<name>` or `.githooks/<name>` afterwards.

| Hook | What it does |
|------|--------------|
| `commit-msg` | Conventional commits (`feat fix refactor docs test chore perf style build ci revert`, scopes, `!`). Rejects wip (outside `.claude/worktrees/`), AI attribution and emoji. Lets `Merge`, `Revert "`, `fixup!`/`squash!`/`amend!` through |
| `pre-commit` | `gitleaks` scan of staged changes. Warns and allows if gitleaks is missing. `PIPELINEKIT_ALLOW_SECRET=1` skips one commit |
| `pre-push` | Refuses pushes to `main`/`master`. `ALLOW_MAIN_PUSH=1` overrides (humans only; bash-guard refuses it for Claude) |

A repo with its own local `core.hooksPath` (husky, the pre-commit framework, or a manual setting) bypasses these. Run `git config --show-origin core.hooksPath` inside it to check.

## Rule ids and the event log

Every refusal ends with the id of its rule in square brackets, for example `BLOCKED: git commit --no-verify skips the git hooks [git.no-verify]`. The hooks also record each block, ask, override and error in an event log, and `/kit` reads it back under Activity (see [Self-check](#self-check)).

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
| `pre-push.protected-branch` | `pre-push` | block | A push to `main` or `master` |
| `pre-push.allow-main` | `pre-push` | override | `ALLOW_MAIN_PUSH=1` let such a push through |

With `ask`, Claude Code prompts you instead of refusing. `override` means a human-only variable let something through. `error` means the hook could not do its job: a guard hook then refuses the command or commit, while the session-start check only steps aside.

## Skills

| Skill | Use it for |
|-------|------------|
| `dotnet-conventions` | .NET layering, DI, EF Core migrations, testing (FluentAssertions 7.x pin), BackgroundService rules, target-framework support dates, plus ASP.NET Core security in `references/security.md` |
| `deploy` | Router for Vercel, Railway, Render, DigitalOcean App Platform and Azure (Container Apps, App Service): auth check, deploy, secrets without argv, verify, logs, rollback, and trading-bot overlap. Per-provider detail in `references/`. If a CLI is missing or not logged in, it stops and asks you |
| `exchange-api-keys` | Exchange API keys for CryptoBargain and FundingRateArb: where they load from, never logging them, testnet vs mainnet, withdrawal-disabled and IP-restricted scopes, storage, rotation, leak runbook |
| `docs-writer` | Render `docs-source/*.md` into self-contained HTML pages under `documentation/` with `render.py` and `template.html`, with optional data-driven interactive snippets |
| `mobile` | Android (Kotlin/Compose) builds and device access from WSL2, iPhone home-screen web apps, Expo/EAS cloud builds for iOS, release and security checklist |
| `kit` | Self-check, run as `/kit`: reports missing or changed kit files, hooks that no longer block or allow what they should, kit entries missing from `settings.json`, environment conflicts, and what the hooks blocked or failed on in the last days |
| `ship` | Run as `/ship`: Claude finishes the pull requests it opens. A fresh agent acceptance-tests the change against the issue's criteria, findings are fixed and tested again, then `ship.py` merges once every gate holds (own pull request, not a release, no required review, a passed test for exactly this commit, green CI). A project opts out with `Merges: ask first` in its `CLAUDE.md` |

In 0.1.0, `deploy` replaces the five separate `*-ops` skills and the per-provider deployment agents, `mobile` replaces `expo` and `ios`, and the ASP.NET Core security rules moved into `dotnet-conventions`.

## Self-check

`/kit` answers one question: is anything in this install not working? Run it after installing or updating the kit, and when a hook blocks something you did not expect or fails to start. Claude can also run it on its own when a kit hook misbehaves.

| Section | What is checked |
|---------|-----------------|
| Install | Every hook, the event-log helper, git hook and skill is present; hooks are executable and have LF line endings; `settings.json` is valid, its hook commands point to files that exist, attribution is off and the secret deny rules are there; the global `core.hooksPath` |
| Changes since install | Each installed file against the hash recorded at install time; the kit's hook entries and deny/ask rules in `settings.json` |
| Live probe | Each hook gets input it must block and input it must allow: `git commit --no-verify`, a `docker` mount of `/etc`, `curl` piped into `sh`, `DROP TABLE` through `psql`, a `HEAD` file next to `refs/`, a non-conventional commit message, a push to `main`. The session-start check must report an install with nothing in it and say nothing about this one. Each refusal must also arrive in an event log, which the probe keeps in a temporary directory |
| Environment | python3, Claude Code and gitleaks versions; whether `gh` and Playwright are available; WSL; a repository that sets its own `core.hooksPath` |
| Activity | What the kit's hooks did in the last 7 days, read from the event log: each rule that blocked, asked, was overridden or failed, with a count and the last time. The 20 newest rules are listed, and a hook that failed is listed however old it is. See [Rule ids and the event log](#rule-ids-and-the-event-log). Not part of `--quick` |

A line is `[fail]` when a guard is missing or does the wrong thing, `[warn]` when something changed but still works (for example a skill file you edited) or a hook failed while it ran, and `[info]` for context. The report ends with `Result: healthy`, or with the number of problems and the command that repairs the install. The check itself changes nothing in `~/.claude`.

The report repeats a name from `settings.json` or the install manifest only when it reads as a plain name: a hook's file name, an event, a rule, a version, a branch. Anything else is counted and not quoted, so a line that sits in one of those files cannot show up as a line of the report. Characters that draw as nothing or change how a line reads are removed. A plain name can still spell a word, so read the report as a list of names, not as advice.

The same check runs when a session starts. `session-check.py` is a SessionStart hook that runs `check.py --quick` on `startup` (not on resume or after `/clear`); it takes about 0.2 seconds. A healthy install, warnings included, gives no output. With a `[fail]` you get one line with the number of problems and no text from the report, and Claude is told the same:

```text
pipelinekit: 2 problems in this install. Run /kit for the report.
```

The hook never blocks a session. A check that takes longer than 4 seconds is dropped, together with anything it started, and shows up under Activity as `session-check.timeout`. `PIPELINEKIT_SESSION_CHECK=0` in the environment switches it off, and `/kit` then says so.

The checker is `claude/skills/kit/check.py`, stdlib only. It also runs outside a session:

```bash
python3 ~/.claude/skills/kit/check.py            # full report, about a second
python3 ~/.claude/skills/kit/check.py --quick    # no live probes
python3 ~/.claude/skills/kit/check.py --verbose  # also list the checks that passed
python3 ~/.claude/skills/kit/check.py --json     # for scripts
python3 ~/.claude/skills/kit/check.py --days 30  # activity of the last 30 days (1 to 365)
python3 ~/.claude/skills/kit/check.py --session ID  # activity of one session
```

Exit code 0 means healthy, 1 means problems were found, 2 means the checker itself failed. `scripts/verify.sh` runs the same file. The JSON output has an `activity` list with every rule; the text report shows the 20 most recent.

The comparison data is `~/.claude/pipelinekit/manifest.json`, which the installer writes: kit version and commit, the checkout path, a SHA-256 of every installed file, and the `settings.json` entries the kit owns. An install made before this file existed reports `install manifest not found`; run the installer once.

Two things are outside its reach. A `permissions.deny` match, or a prompt you declined, leaves no trace to report: Activity lists only what the kit's own hooks did. And the report describes the environment it runs in: another WSL distro, an SSH host or a sandboxed session can differ, so run the check there.

## Shipping a pull request

With the kit installed, Claude finishes the pull requests it opens instead of handing each one to you to merge. The `ship` skill (`/ship`) describes the loop, and `claude/skills/ship/ship.py` holds the conditions for the merge.

1. The issue lists acceptance criteria as a checklist.
2. Claude builds the change, runs the project's tests and opens a draft pull request.
3. A fresh agent tests the change. It gets the criteria and the running build, not the code or the builder's notes. A web page is driven with Playwright, a command-line tool or installer runs in a throwaway directory, an API is started and called. A change with nothing user-visible gets a smoke run instead.
4. Findings are fixed, each bug with a regression test, and the test runs again until it passes.
5. `ship.py record` notes the result for the tested commit, and with a pass whether the pull request is a release (`--release yes` or `--release no`). `ship.py merge` waits for CI and merges.

`ship.py merge` refuses unless every gate holds:

| Gate | Holds when |
|------|------------|
| `pr` | The branch has an open pull request |
| `own` | Your GitHub account opened it, and it is not from a fork |
| `policy` | The project has not opted out |
| `release` | It is not a release. A release is: a release, stage or version branch (`release/1.0`, `develop`, `staging`, `v2`, `chore/release-0.2.0`) into the default branch or into another long-lived branch; the default branch into another branch; anything into a deploy branch such as `production`, `prod-eu` or `gh-pages`; anything into `main` where another branch is the default; anything into a branch that is neither the default nor a known working branch; a branch that pull requests were merged into; a title that names a release or a version; a diff that sets a version or changes a release file of the project; a test record that says it is one (all below) |
| `review` | No review is required, requested or asking for changes |
| `current` | The local commit is the pull request's head and nothing tracked is uncommitted |
| `up-to-date` | The branch contains its base branch and does not conflict with it |
| `tested` | The last test record is a pass for exactly this commit, and the loop is not stuck |
| `ci` | Every check has finished and passed. A pull request with no check at all passes only where no workflow runs on pull requests, or with `--allow-no-checks` |

The merge command names the tested commit (`--match-head-commit`), so a commit pushed in between is not merged. The helper has no `--admin` option, and `gh pr merge --admin` is on the `permissions.ask` list. The merge method follows the base branch: a merge commit where the branch already has them, squash otherwise.

A draft has to be marked ready before GitHub merges it, and that can start checks, add reviewers or turn on branch protection. The helper therefore watches the pull request after marking it ready and merges only when it stayed mergeable for the whole settle time: 30 seconds, or 90 (the `--grace` time) where a check is still to come, because none has run yet or a workflow starts on `ready_for_review`. `--settle S` sets the time. Where a workflow runs on pull requests, a check must really have run by then: one that was skipped on the draft does not count, and only `--allow-no-checks` lifts that. If something showed up, the pull request stays ready and unmerged. The last line of output is always the outcome: `Merged #12 into main ...`, `Not merged: ...` or `STOP: ...`.

The release gate leans towards asking. A feature branch into a release branch such as `release/v1.0` is an ordinary change and merges; the release branch into `main` does not. A title counts when it is made of release words (`chore: prepare 0.3.0`, `Bump version: 1.2.3 to 1.2.4`, `chore: release kit 1.2.0`, `chore: bump version in package.json`, `chore: weekly release`, `chore: patch`, `Deploy`), not when it is about a release (`fix: release 1.2.0 broke the installer`, `chore: release script`), about a dependency (`chore(deps): bump lodash to 4.17.21`) or about a tool (`ci: bump python version to 3.12`); `docs`, `test`, `style`, `refactor` and `perf` titles never count.

The gate also reads the diff against the base branch. It does not work from a list of known manifests: a version is ordinary in the places known to hold the versions of other things, and held anywhere else, whatever the file format.

Held are:

- any change to a version file (`VERSION`, `version.txt`, `.bumpversion.cfg`, `.release-please-manifest.json`) and any numbered file in a release-notes directory (`docs/releases/1.2.4.md`);
- a new or changed value under a key with `version` in its name, in any manifest or data file: `package.json`, `pyproject.toml`, `Cargo.toml`, `pom.xml`, a `.csproj` or `.nuspec`, `Chart.yaml`, `Info.plist`, `CMakeLists.txt`, `build.gradle`, `setup.py`, `AssemblyInfo.cs`, `version.h`, and files the helper has never heard of. In a file without a known format, a line that only swaps one three-part number for another counts too;
- a line of source code that sets a quoted version: an assignment (`__version__ = "1.2.4"`, `public static readonly string Version = "1.2.4";`), a key of an object, a struct or a dictionary (`version: "1.2.4",`), a `#define APP_VERSION "1.2.4"`. `app.config.js` and `app.config.ts` are read as manifests;
- a new version heading in release notes (`CHANGELOG`, `CHANGES`, `HISTORY`, `NEWS`, `RELEASES`, `RELEASE_NOTES`, with any extension): `## 1.2.4`, `## [1.2.4] - 2026-11-10`, `1.2.4` over an underline, `**1.2.4**`, `## kit 1.2.4`, a link definition `[1.2.4]: ...`.

Ordinary are: lock files; files that pin tools (`.nvmrc`, `.python-version`, `Dockerfile`, `docker-compose.yml`, `requirements*.txt`, `.pre-commit-config.yaml`, `packages.config`, `deps.edn`); everything under `.github/`, `.circleci/` and `.devcontainer/`; files in test, fixture, example and vendor directories; documentation (`README`, `.md`, `.rst`, `.txt`, `.html`); dependency tables and elements (`dependencies`, `[dependencies.clap]`, `<parent>`, `<dependency>`, `engines`); keys that name a tool or a format (`python-version`, `apiVersion`, `schemaVersion`, `minSdkVersion`); a whole number under a plain `version` key (`version: 2` is a format version); a changelog entry under an existing heading.

No reading of a diff is complete, so three more things decide:

- `ship.py record --result pass` takes `--release yes` or `--release no`. Whoever ran the test knows what the change is and says so; `yes` holds the pull request, and a pass without the answer is not accepted.
- A project names its own release files and branches in its `CLAUDE.md`, each on a line of its own: `Release files: app/build.txt, deploy/` and `Release branches: team-*, customer-*`. A change to one of the files, and a pull request from or into one of the branches, is held. `deploy/` is everything below that directory; anything else is a glob on the path, for files also on the file name alone. As with the opt-out line, the `CLAUDE.md` on the base branch counts as well.
- A branch that other pull requests were merged into is a stage, whatever it is called, and merging it on is a promotion. The helper asks GitHub about every head branch that is not a topic branch (`feat/...`, `fix/...`); without an answer nothing merges.

The gate guards your own project against a slip. It is not a defence against a pull request written to get past it. It does not see: a version in a place the lists call ordinary (a label in a `Dockerfile`, a file under `tests/` or `examples/`, a `.md` file that is not release notes); a whole-number version under a plain `version` key; a version that source code spells another way (`VERSION = (1, 2, 4)`, the header comment of a plugin); a version in a `.nix` or `.tf` file; a version Maven takes from `<properties>` or `${revision}`; files over 1 MB and binary files; a release whose title uses no release word (`chore: go live`) and whose diff sets no version. It holds some pull requests that are not releases: a nested package getting its first version, a version-like setting in a config file, a branch whose short name starts with a stage word (`qa-fixes`), a title that is a name and a number (`chore: lodash 4.17.21`). When that happens, say that it may be merged, and merge it yourself.

Known working branches are: the default branch; the shared branches `develop`, `development`, `dev`, `integration`, `staging`, `stage`, `next`, `beta`, `alpha`, `canary`, `preview`, `nightly`, `edge`, `uat`, `qa`, `preprod`, `test`, `testing` and `trunk`; branches under `integration/`, `staging/`, `stage/`, `uat/`, `qa/` and `preprod/`; release lines, which is anything that starts with `release/`, `release-`, `releases/`, `rel/`, `rc/`, `hotfix/`, `support/` or `maint/`, and bare version names such as `1.x` or `v2`; topic branches such as `feat/12-base` (a stacked pull request). A pull request into any other branch (`customer-a`, `release`) is held, because the helper cannot know what that branch stands for. Name such a branch on a `Release branches:` line when it is a release branch. As the branch a pull request comes from, `hotfix/login-crash` is a fix like any other; only a hotfix branch with a version in its name (`hotfix/1.2.1`), or one that other pull requests were merged into, is held.

These stay yours: release pull requests, tags, publishing and production deploys; pull requests someone else opened; anything behind a required review or branch protection. Claude also stops and asks when the same finding is still open after two fix attempts, after five failed rounds in a row, and when a test needs a decision the criteria do not settle. A stuck loop shows in `ship.py status` and blocks `ship.py merge` until you decide.

To turn self-merging off for a project, put this line in its `CLAUDE.md`:

```text
Merges: ask first
```

The same line in `~/.claude/CLAUDE.md` turns it off everywhere, and so does `PIPELINEKIT_MERGE` in the environment with any non-empty value but `auto`. Claude then asks before it merges. The line counts on its own line, also as a list or task item, a heading, a table cell or two cells of a row (`| Merges | ask first |`), in bold, quoted, in backticks or inside an HTML comment. `Merging: ask first`, `Merges - ask first`, `Merges: always ask first`, `Merges: never`, `Merges: off` and `Merges: manual` count as the same line. A sentence that only mentions it does not. The `CLAUDE.md` on the base branch counts as well, so a branch cannot drop the line for its own pull request.

Test reports and screenshots go to `docs/uat/` in the project. That directory is local: the helper adds it to `.git/info/exclude`, and it is on the never-stage list. The kit does not install Playwright; `/kit` reports whether `gh` and Playwright are available.

```bash
python3 ~/.claude/skills/ship/ship.py status           # every gate, with the reason
python3 ~/.claude/skills/ship/ship.py merge --dry-run  # what would be merged, and how
```

Exit code 0 means done, 1 means a gate or a check failed, 2 means the helper could not run, 3 means stop and ask.

## CLAUDE.md template

`claude/CLAUDE.md.template` is about 60 lines of English with no imported rule files. The installer fills in `${USER_NAME}`, `${USER_EMAIL}` and `${CLAUDE_HOME}` and writes the result to `~/.claude/CLAUDE.md`. It covers:

- your identity;
- git rules: commit only when asked, conventional commits, no AI attribution, no workflow jargon in commit text, the never-stage list, `.git/info/exclude` for Claude-specific ignores, and no direct pushes to `main`;
- the `docs/` (local, never committed) and `documentation/` (committed) split;
- a base-branch detection snippet;
- serena for symbol navigation, Grep/Glob for text;
- decisions that are yours to make, asked as interactive questions: two to four options, each with its upside and downside, the recommended one first;
- GitHub habits with `gh`: issues with acceptance criteria before work, `<type>/<issue#>-<slug>` branches, draft PRs, finishing its own PRs with the `ship` skill, reading CI logs, releases when you ask;
- the deploy CLIs.

## MCP servers

| Server | Installed by default | Notes |
|--------|----------------------|-------|
| serena | Yes, unless you pass `--no-serena` | Symbol-level code navigation. Installed with `uv` from a pinned commit and registered at user scope in `~/.claude.json`. A project `.mcp.json` entry takes precedence |
| context7 | No | Library and framework docs. Copy its entry from `.mcp.json.template` into a project's `.mcp.json` |

## What is not included

Plan mode, the Workflow tool, `/code-review`, `/security-review`, `/simplify`, the Explore and Plan agents, auto-memory, worktree isolation, `/loop` and `/schedule` are all built into Claude Code. pipelinekit no longer provides its own versions. See [Upgrading from 0.0.1](upgrading.html#what-was-removed) for how the old components map to these built-ins.
