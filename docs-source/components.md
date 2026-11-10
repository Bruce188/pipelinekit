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
  {"name": "Claude Code hooks", "color": "#f59e0b", "count": "3 scripts",
   "chips": [{"label": "bash-guard.py", "tip": "PreToolUse Bash: git, docker, fetch and SQL rules"},
             {"label": "block-bare-repo-markers.py", "tip": "PreToolUse Edit/Write"},
             {"label": "post-edit-format.sh", "tip": "PostToolUse Edit/Write: prettier"}]},
  {"name": "Git hooks", "color": "#3b82f6", "count": "global core.hooksPath",
   "chips": [{"label": "commit-msg", "tip": "Conventional commits, no attribution or emoji"},
             {"label": "pre-commit", "tip": "gitleaks on staged changes"},
             {"label": "pre-push", "tip": "No pushes to main or master"}]},
  {"name": "Skills", "color": "#10b981", "count": "5 skills",
   "chips": [{"label": "dotnet-conventions"}, {"label": "deploy"}, {"label": "exchange-api-keys"},
             {"label": "docs-writer"}, {"label": "mobile"}]},
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

## Skills

| Skill | Use it for |
|-------|------------|
| `dotnet-conventions` | .NET layering, DI, EF Core migrations, testing (FluentAssertions 7.x pin), BackgroundService rules, target-framework support dates, plus ASP.NET Core security in `references/security.md` |
| `deploy` | Router for Vercel, Railway, Render, DigitalOcean App Platform and Azure (Container Apps, App Service): auth check, deploy, secrets without argv, verify, logs, rollback, and trading-bot overlap. Per-provider detail in `references/`. If a CLI is missing or not logged in, it stops and asks you |
| `exchange-api-keys` | Exchange API keys for CryptoBargain and FundingRateArb: where they load from, never logging them, testnet vs mainnet, withdrawal-disabled and IP-restricted scopes, storage, rotation, leak runbook |
| `docs-writer` | Render `docs-source/*.md` into self-contained HTML pages under `documentation/` with `render.py` and `template.html`, with optional data-driven interactive snippets |
| `mobile` | Android (Kotlin/Compose) builds and device access from WSL2, iPhone home-screen web apps, Expo/EAS cloud builds for iOS, release and security checklist |
| `kit` | Self-check, run as `/kit`: reports missing or changed kit files, hooks that no longer block or allow what they should, kit entries missing from `settings.json`, and environment conflicts |
| `ship` | Run as `/ship`: Claude finishes the pull requests it opens. A fresh agent acceptance-tests the change against the issue's criteria, findings are fixed and tested again, then `ship.py` merges once every gate holds (own pull request, not a release, no required review, a passed test for exactly this commit, green CI). A project opts out with `Merges: ask first` in its `CLAUDE.md` |

In 0.1.0, `deploy` replaces the five separate `*-ops` skills and the per-provider deployment agents, `mobile` replaces `expo` and `ios`, and the ASP.NET Core security rules moved into `dotnet-conventions`.

## Self-check

`/kit` answers one question: is anything in this install not working? Run it after installing or updating the kit, and when a hook blocks something you did not expect or fails to start. Claude can also run it on its own when a kit hook misbehaves.

| Section | What is checked |
|---------|-----------------|
| Install | Every hook, git hook and skill is present; hooks are executable and have LF line endings; `settings.json` is valid, its hook commands point to files that exist, attribution is off and the secret deny rules are there; the global `core.hooksPath` |
| Changes since install | Each installed file against the hash recorded at install time; the kit's hook entries and deny/ask rules in `settings.json` |
| Live probe | Each hook gets input it must block and input it must allow: `git commit --no-verify`, a `docker` mount of `/etc`, `curl` piped into `sh`, `DROP TABLE` through `psql`, a `HEAD` file next to `refs/`, a non-conventional commit message, a push to `main` |
| Environment | python3, Claude Code and gitleaks versions; whether `gh` and Playwright are available; WSL; a repository that sets its own `core.hooksPath` |

A line is `[fail]` when a guard is missing or does the wrong thing, `[warn]` when something changed but still works (for example a skill file you edited), and `[info]` for context. The report ends with `Result: healthy`, or with the number of problems and the command that repairs the install. The check itself changes nothing in `~/.claude`.

The checker is `claude/skills/kit/check.py`, stdlib only. It also runs outside a session:

```bash
python3 ~/.claude/skills/kit/check.py            # full report, about a second
python3 ~/.claude/skills/kit/check.py --quick    # no live probes
python3 ~/.claude/skills/kit/check.py --verbose  # also list the checks that passed
python3 ~/.claude/skills/kit/check.py --json     # for scripts
```

Exit code 0 means healthy, 1 means problems were found, 2 means the checker itself failed. `scripts/verify.sh` runs the same file.

The comparison data is `~/.claude/pipelinekit/manifest.json`, which the installer writes: kit version and commit, the checkout path, a SHA-256 of every installed file, and the `settings.json` entries the kit owns. An install made before this file existed reports `install manifest not found`; run the installer once.

Two things are outside its reach. A `permissions.deny` match, or a prompt you declined, leaves no trace to report. And the report describes the environment it runs in: another WSL distro, an SSH host or a sandboxed session can differ, so run the check there.

## Shipping a pull request

With the kit installed, Claude finishes the pull requests it opens instead of handing each one to you to merge. The `ship` skill (`/ship`) describes the loop, and `claude/skills/ship/ship.py` holds the conditions for the merge.

1. The issue lists acceptance criteria as a checklist.
2. Claude builds the change, runs the project's tests and opens a draft pull request.
3. A fresh agent tests the change. It gets the criteria and the running build, not the code or the builder's notes. A web page is driven with Playwright, a command-line tool or installer runs in a throwaway directory, an API is started and called. A change with nothing user-visible gets a smoke run instead.
4. Findings are fixed, each bug with a regression test, and the test runs again until it passes.
5. `ship.py record` notes the result for the tested commit. `ship.py merge` waits for CI and merges.

`ship.py merge` refuses unless every gate holds:

| Gate | Holds when |
|------|------------|
| `pr` | The branch has an open pull request |
| `own` | Your GitHub account opened it, and it is not from a fork |
| `policy` | The project has not opted out |
| `release` | It is not a release. A release is: a release, stage or version branch (`release/1.0`, `develop`, `staging`, `v2`, `chore/release-0.2.0`) into the default branch; the default branch into another branch; anything into a deploy branch such as `production` or `gh-pages`; anything into `main` where another branch is the default; a title that names a release or a version |
| `review` | No review is required, requested or asking for changes |
| `current` | The local commit is the pull request's head and nothing tracked is uncommitted |
| `up-to-date` | The branch contains its base branch and does not conflict with it |
| `tested` | The last test record is a pass for exactly this commit, and the loop is not stuck |
| `ci` | Every check has finished and passed. A pull request with no check at all passes only where no workflow runs on pull requests, or with `--allow-no-checks` |

The merge command names the tested commit (`--match-head-commit`), so a commit pushed in between is not merged. The helper has no `--admin` option, and `gh pr merge --admin` is on the `permissions.ask` list. The merge method follows the base branch: a merge commit where the branch already has them, squash otherwise.

A draft has to be marked ready before GitHub merges it, and that can start checks, add reviewers or turn on branch protection. The helper therefore watches the pull request after marking it ready and merges only when it stayed mergeable for the whole settle time: 30 seconds, or 90 (the `--grace` time) where a check is still to come, because none has run yet or a workflow starts on `ready_for_review`. `--settle S` sets the time. Where a workflow runs on pull requests, a check must really have run by then: one that was skipped on the draft does not count, and only `--allow-no-checks` lifts that. If something showed up, the pull request stays ready and unmerged. The last line of output is always the outcome: `Merged #12 into main ...`, `Not merged: ...` or `STOP: ...`.

The release gate leans towards asking. A feature branch into a release branch such as `release/v1.0` is an ordinary change and merges; the release branch into `main` does not. A title counts when it is made of release words (`chore: prepare 0.3.0`, `Bump version: 1.2.3 to 1.2.4`, `chore: release kit 1.2.0`), not when it is about a release (`fix: release 1.2.0 broke the installer`, `chore(deps): bump lodash to 4.17.21`); `docs`, `test`, `style`, `refactor` and `perf` titles never count.

These stay yours: release pull requests, tags, publishing and production deploys; pull requests someone else opened; anything behind a required review or branch protection. Claude also stops and asks when the same finding is still open after two fix attempts, after five failed rounds in a row, and when a test needs a decision the criteria do not settle. A stuck loop shows in `ship.py status` and blocks `ship.py merge` until you decide.

To turn self-merging off for a project, put this line in its `CLAUDE.md`:

```text
Merges: ask first
```

The same line in `~/.claude/CLAUDE.md` turns it off everywhere, and so does `PIPELINEKIT_MERGE` in the environment with any value but `auto`. Claude then asks before it merges. The line counts on its own line, also as a list or task item, a heading, a table cell, in bold, quoted, in backticks or inside an HTML comment. A sentence that only mentions it does not. The `CLAUDE.md` on the base branch counts as well, so a branch cannot drop the line for its own pull request.

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
