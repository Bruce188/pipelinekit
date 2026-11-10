# Changelog

## 0.1.0 — 2026-11-03

Trimmed to a small config kit. Current Claude Code covers most of what the
kit used to ship, so those parts are gone.

### Kept

- Claude Code hooks: `bash-guard.py`, `block-bare-repo-markers.py`,
  `post-edit-format.sh` and `config/never-stage.txt`, with their tests.
- Global git hooks: `commit-msg`, `pre-commit`, `pre-push`.
- Skills: `dotnet-conventions`, `deploy`, `exchange-api-keys`, `docs-writer`
  (with its render lib), `mobile`.
- serena MCP registration (pinned commit); context7 stays optional.

### Platforms

- Claude Code Desktop: documented which session environments run the kit
  (WSL and SSH yes, Local on Windows and Cloud no).
- `install.sh` refuses to run in a native Windows shell (Git Bash, MSYS,
  Cygwin), where the hooks cannot start.
- `.gitattributes` forces LF, so a checkout made with Git for Windows no
  longer breaks the hook shebangs.
- `verify.sh` runs each hook once instead of only checking that it exists.

### Self-check

- `/kit` reports what is not working in an install: missing or changed files,
  hooks that no longer block or allow what they should, kit entries that went
  missing from `settings.json`, a global `core.hooksPath` that changed. The
  checks are in `claude/skills/kit/check.py` (`--quick`, `--verbose`, `--json`).
- The installer writes `~/.claude/pipelinekit/manifest.json` (version, commit,
  file hashes, the kit's settings entries); the check compares against it.
- `verify.sh` runs the same checker, so the installer, CI and `/kit` agree.
- Every refusal names its rule id in square brackets (`[git.no-verify]`), and
  the hooks record each block, ask, override and error in
  `~/.local/state/pipelinekit/events.jsonl`: rule id, reason, session and
  working directory, never the command text. Only its owner can read the
  file, it rotates at 1 MB, and `PIPELINEKIT_LOG=0` switches it off.
- `/kit` has an Activity section: what the hooks blocked, asked about or
  failed on in the last 7 days, grouped by rule (`--days N`, `--session ID`).
  The live probe also checks that refusals reach the log.
- A SessionStart hook (`session-check.py`) runs the quick check when a session
  starts: no output when the install is healthy, one line naming `/kit` when
  something is broken. It never blocks a session, and
  `PIPELINEKIT_SESSION_CHECK=0` switches it off.
- CI runs the checker on a fresh install and on one with a hook removed. The
  workflow also runs every Monday and on demand; a failed scheduled run opens
  the issue `Weekly self-check failed` or adds a comment to it
  (`scripts/ci-report.sh`).
- `/kit` has an Updates section: it asks the remote of the checkout once a day
  whether there are commits this install lacks and says `up to date`,
  `update available` or `not checked`. It never counts as a problem;
  `PIPELINEKIT_UPDATE_CHECK=0` switches it off.
- `/kit update` lists the new commits, asks, then fast-forwards the checkout
  to exactly the commit it listed, runs the installer with the options chosen
  at install time and runs the self-check (`claude/skills/kit/update.py`). It
  refuses on uncommitted changes, another branch, own commits or a remote that
  moved in the meantime.
- The Environment section says when the Bash sandbox keeps `gh` from reading
  its own login file, and which setting fixes that.

### Shipping

- `ship` skill (`/ship`): Claude finishes the pull requests it opens. A fresh
  agent acceptance-tests the change against the issue's criteria, findings are
  fixed and tested again, and `claude/skills/ship/ship.py` merges once every
  gate holds: own pull request, not a release, no required review, branch up
  to date, a passed test for exactly this commit, green CI.
- Release pull requests, tags, publishing, other people's pull requests and
  anything behind branch protection stay with the user. A project opts out
  with the line `Merges: ask first` in its `CLAUDE.md`.
- After marking a draft ready the helper reads the pull request again
  before it merges, so a check or review that only starts then is not
  skipped. A pull request without any check is not green where workflows run
  on pull requests (`--allow-no-checks` says otherwise).
- `gh pr merge --admin` is on the `permissions.ask` list, `docs/uat/` (local
  test reports) is on the never-stage list, and `/kit` reports whether `gh`
  and Playwright are available.

### Security

- Native permission rules: `deny` Read/Edit of `.env*` (except
  `.env.example/.sample/.template`), private keys, `~/.ssh`, `~/.aws`,
  `~/.kube/config`, `~/.config/gh/hosts.yml`, credentials files; `ask` before
  editing Claude settings/hooks/`~/.gitconfig` and before `reset --hard`,
  `clean -f`, force push, `branch -D`, `checkout/restore .`. Deny and ask hold
  in bypassPermissions mode.
- `env-scrub.py` removed without replacement. `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`
  was tried, but it forces the default permission mode, which breaks
  bypassPermissions workflows. Secrets stay out of reach through deny rules.
- Fixed: `block-stage-sensitive` turned a block into an allow after three
  denials (`denial_tracker.py`, removed) and sent its reason to stdout.
- Global git hooks in `~/.claude/git-hooks` (`core.hooksPath`): `commit-msg`
  (conventional commits incl. `revert`, `!`, scopes; rejects wip outside agent
  worktrees, AI attribution, emoji; passes Merge/Revert/fixup!), `pre-commit`
  (gitleaks on staged changes with the right syntax for 8.19+ and older; warns
  if gitleaks is missing), `pre-push` (refuses main/master from git's ref
  list). Each chains to the repo's own `.git/hooks/<name>` or
  `.githooks/<name>`.

### Added

- `exchange-api-keys` skill.
- `mobile` skill, replacing `expo` and `ios`. It covers native Android builds
  from WSL2 (Gradle, adb through the Windows server or wireless debugging),
  iPhone home-screen web apps (service worker updates, LAN HTTPS with a
  private CA, debugging Safari without a Mac), Expo/EAS as a reference, and a
  release and security checklist.
- skill-creator `evals/` for `dotnet-conventions`, `deploy`,
  `exchange-api-keys`, `mobile` and `docs-writer`.
- `claude/config/settings.template.json`, merged into `settings.json` by the
  installer.
- docs-writer browser test (`tests/test_interactive.py`) that drives every
  widget in headless Chromium; prints SKIP without playwright.

### Changed

- One `bash-guard.py` replaces `block-dangerous-commands`, `block-push-main`,
  `block-stage-sensitive` and the Bash-side `validate-commit-msg`. Parses once
  (shlex, git global options, wrappers, `sh -c`, `$()`), runs only for
  git/docker/podman/curl/wget/DB-client commands via `if`, `onFailure: block`.
  Closes the reviewed bypasses (`git stage`, `git -C`, `commit -a`,
  `add -- .`, `add :/`, `remote set-url`, `+main`, `HEAD:main`, `--no-verify`,
  `-c core.hooksPath`, `curl | sh`, `bash <(curl)`) and false positives
  (`docker -v .:/app`, read-only global git config reads, `grep "drop table"`,
  `src/credentials.ts`, `.env.example`, `src/bin/`, `docs/planning-notes.md`,
  heredoc commit messages).
- `never-stage.txt` is the single list, gitignore-style with `!` negation;
  pipeline-only entries removed.
- `block-bare-repo-markers` covers Edit and only blocks a HEAD plus
  config/objects/refs set at depth 0-1 (no more `src/config` false positive).
- `post-edit-format` runs prettier only (py and `dotnet format` branches
  removed: 250 ms to 5 s per edit).
- New `deploy` skill replaces `vercel-ops`, `railway-ops`, `render-ops`,
  `digitalocean-ops`, `azure-ops` and the per-provider deployment-engineer
  agents. It is a router plus
  `references/{vercel,railway,render,digitalocean,azure}.md`, with corrected
  CLI commands, a way to set secrets that keeps them out of argv, and
  guidance on trading-bot deploy overlap.
- Rewrote `dotnet-conventions`: path-scoped, EF Core migration workflow,
  FluentAssertions 7.x pin (8+ needs a commercial licence), SQLite in-memory
  for tests, BackgroundService rules, .NET support dates.
- Merged `security-conventions` into
  `dotnet-conventions/references/security.md`. Corrected the antiforgery
  guidance: it is a global `AutoValidateAntiforgeryTokenAttribute`, and
  token-authenticated APIs are exempt. Dropped the reference to the removed
  `security-auditor` agent.
- `CLAUDE.md.template` rewritten: ~55 lines, English, no imported rule files.
  It gained the "no workflow jargon in commit or PR text" rule (from
  `commit-conventions`), an Azure (`az`) row in the deploy platforms table, a
  GitHub section (issues, branches, PRs, CI logs and releases with `gh`) and
  clearer serena vs Grep guidance.
- docs-writer scripts work from an installed skill dir. The target is the cwd
  or `--root`, and SKILL.md uses `${CLAUDE_SKILL_DIR}`. Batch mode
  (`render.py` with no arguments) renders `docs-source/*.md` and inlines the
  search index, so search works from `file://`.
- docs-writer snippets are generic and take their content from a JSON child.
- `install.sh` rewritten (2,560 to ~300 lines). It overlays files in place
  instead of moving `~/.claude` aside, merges the settings template after a
  backup (the user's own hooks and rules stay), removes kit files from
  earlier builds only if they are unmodified, offers to set the global
  `core.hooksPath` (`--git-hooks`/`--no-git-hooks`, `PIPELINEKIT_GIT_HOOKS`),
  and sets `attribution` to empty strings (no co-author trailer or PR footer).
- `verify.sh` checks the kept hooks, git hooks and skills, that every
  `settings.json` hook command resolves, that attribution is off, and that the
  deny rules are present.
- CI runs the git-hook, installer, pytest hook and docs-writer tests.

### Fixed

- docs-writer: the richness check counted inline script/style as prose words.
- docs-writer: before-after-slider dropped its placeholder children.
- docs-writer: widgets and template features (search from `file://`, the
  mobile ToC button, comparison tabs, terminal simulator) now work.
- `mobile` skill: an example path contained a personal home directory.

### Removed

- `commit-conventions` skill: `CLAUDE.md.template` and the `commit-msg` git
  hook cover it.
- `security-conventions` skill (merged into `dotnet-conventions`).
- `ios` skill: it described an Xcode integration that needs a Mac, linked a
  missing reference, and contained an unverified Swift SDK API.
- `expo` skill: folded into `mobile`. Removed stale commands (`eas secret:*`,
  global `expo-cli`, `eas update --republish`).
- `docs-writer` agent (the skill covers it).
- Pipelinekit-specific docs-writer snippets (`skill-catalog-grid` and 8
  others), `build_catalog_data.py` and the topic-affinity check.
- Hooks `env-scrub.py`, `pre-edit-protect.sh`, `scan-tool-output.sh`,
  `_promptguard.py`, `_pathguard.py`, `_never_stage_match.py`,
  `denial_tracker.py`, `validate-commit-msg.sh`, `commit-msg-wrapper.sh`,
  `scan-secrets-staged.sh`, `block-push-main.sh`,
  `block-dangerous-commands.sh`, `block-stage-sensitive.sh`, and the per-repo
  git hook install.
- `/pipeline` and its skills, agents, `lib/pipeline`, `lib/ingest`, TDD/UAT
  gates and review panel. Superseded by built-in plan mode, subagents,
  `/code-review`, `/security-review` and `/loop`.
- Persona agents and `persona`; `host-adapters`; `model-overlays`; `modes/`;
  `rules/`; `tresor-resources`; `snippets`; `commands`.
- `caveman-mode`, `caveman-compress`, `claude-md-enhancer` (superseded by
  built-in `/init`), `write-a-skill` (superseded by built-in `skill-creator`),
  `secret-scanner` and `dependency-auditor` (superseded by built-in
  `/security-review`), `research` (superseded by built-in `/loop`),
  `build-hook`/`test-hooks` (superseded by built-in `update-config`),
  `playwright`, `financial-data-analyst`, `synced`, `zoom-out`,
  `ascii-diagram`, `code-health`, `context-dump`, `document-release`,
  `incident`, `landing-report`, `learn`, `uat`, `codegraph-init`,
  `graphify-init`.
- Hooks: `subagent-first-nudge`, `context-budget-advisor`, `context-warning`,
  `post-compact-context`, `session-start-*` (superseded by built-in
  auto-compact and context handling), `skill_budget`, `completion-gate`,
  `stop-completion-gate`, `tdd-red-phase-gate`, `tdd-order-check`,
  `test-logger`, `validate-task-spec`, `verify-worktree-commit`,
  `memory-journal` (superseded by built-in auto-memory),
  `strip-ai-attribution` (superseded by the built-in `attribution` setting),
  `claude-md-guard`, `notify-emit`, `cost_log`, `kill-rogue-mcp-daemon`,
  `mcp-rss-cap`, `agent-caveman-gate`.
- MCP setup for agentmemory, codegraph, graphify, local-rag and
  sequential-thinking (agentmemory superseded by built-in auto-memory).
- `scripts/migrate_flatfile_memory_to_agentmemory.py`, sandbox and index
  scripts, `docs-source/`, the old kit's `documentation/` HTML, `examples/`.

## 0.0.1

Initial pre-release with the `/pipeline` orchestrator. See git history.
