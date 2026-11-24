# Changelog

## Unreleased

- judge-loop: a full-panel loop runs the six roles in round 1 and in the final
  round, and three combined judges at high effort in the rounds between
  (`correctness+tests`, `security+operations`, `user-experience+scope`). The
  state, `status` and `scorecard.md` name the panel of each round.

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
- The release gate reads the branches, the title and the diff. A version is
  held wherever it is set, except in the places known to hold the versions of
  other things (lock files, dependency tables, files that pin tools, CI,
  tests, docs). `record --result pass` takes `--release yes` or `no`, a
  project names its own with `Release files:` and `Release branches:` lines
  in its `CLAUDE.md`, and a branch that pull requests were merged into counts
  as a stage.
- After marking a draft ready the helper watches the pull request for a
  settle time before it merges (30 seconds, 90 where a check is still to
  come; `--settle`), so a check or review that only starts then is not
  skipped. A pull request without any check is not green where workflows run
  on pull requests, and a check that was skipped on the draft does not count
  as a run (`--allow-no-checks` says otherwise).
- A pull request of a judged stack merges bottom-up: a `stack` gate holds it
  until the stack's last round is counted, nothing is open on it or below
  it while the loop runs, no unjudged commit came on its branch, and the
  pull request below it, also the top of a stack it is based on, merged. After a merge, your own
  pull requests based on the merged branch move to its base and get that
  base merged in; others are named, not moved.
- `gh pr merge --admin` is on the `permissions.ask` list, `docs/uat/` (local
  test reports) is on the never-stage list, and `/kit` reports whether `gh`
  and Playwright are available.

### Design

- `frontend-design` skill, vendored unchanged from `anthropics/skills`
  (`skills/frontend-design` at commit
  `41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f`) under the Apache License 2.0.
  `SOURCE.md` in its folder records the commit, the checksums and how to move
  to a newer commit.
- The `CLAUDE.md` template has a Design section: load `frontend-design` before
  building or reshaping anything a person looks at; a project's own design
  system and the host's rules for the output come first; `dataviz` decides
  chart form when the session has it; skip it for small fixes inside an
  existing design.
- `docs-writer` has a Design section: `frontend-design` guides new snippets,
  template changes and raw HTML in a page, within the template's CSS
  variables and without remote assets.
- `/kit` adds an `[info]` line when a `frontend-design` plugin is enabled in
  the user settings next to the kit's copy, and says how to keep one.
- The installer moves a `frontend-design` skill of your own to
  `~/.claude/pipelinekit/backup/` once and prints where; a link of that name
  is removed without touching its target.

### Agents

- Three agents in `claude/agents/`, installed to `~/.claude/agents/`:
  `kit-planner` (model `opus`) writes a plan, `kit-builder` (model `opus`)
  builds it failing test first and commits on the work branch, `kit-judge`
  (model `fable`, tools `Read, Grep, Glob`) scores a plan or a build with one
  JSON object.
- The installer moves an agent file of your own with one of those names to
  `~/.claude/pipelinekit/backup/` once and prints where; a link of that name is
  removed without touching its target. Other agents are left alone. Its last
  line says to start a new session to load the agents, also when the
  verification fails. An old copy of the kit's own agent, left by an install
  that stopped before its manifest, is replaced without a backup. Your own
  files are moved before any kit file is copied: when one cannot be backed up,
  the installer stops with one line, leaves the file as it was and has copied
  nothing of the kit.
- `/kit` fails when an agent file is missing, when `kit-judge.md` has a
  frontmatter key other than `name`, `description`, `model` and `tools`, or
  when it does not have the kit's tools line `Read, Grep, Glob`; it lists an
  edited agent file under "Changes since install".

### Judge loop

- `judge-loop` skill (`/judge-loop`): a change that is more than a small fix
  is planned by `kit-planner`, built by `kit-builder` and scored from 0 to 10
  by fresh `kit-judge` agents, one `general` judge or, for a large or
  sensitive change, six (correctness, tests, security, scope, operations,
  user experience), until each gives 10 within a round budget.
  `claude/skills/judge-loop/loop.py` keeps the state under `docs/loops/` and
  says what comes next; `docs/loops/` is on the never-stage list.
- A build judge reads `hunks.patch` first: the changed hunks with five lines
  of context, without the lines that only moved. Then `map.md`, its last
  result and `criteria.md`; it opens a source file only for a fact the hunks
  do not show, and stops at about 30 tool calls with `"read": "part"`. A 10
  still needs every file the change touches read whole, and that read is not
  capped.
- The `CLAUDE.md` template gains a "Plan, build, judge" section with the rules
  for every agent it starts: read a file whole once or search first, read
  nothing twice, keep output short, return a JSON form or at most 15 lines.
  The agent files and the ship skill's tester brief carry the same rules.
- A project sets its own terms in its `CLAUDE.md`: `Judge loop: off`,
  `Judge rounds: N`, `Judges: correctness, tests`. The installer warns when
  the user-level `CLAUDE.md` it replaces held one of these lines.
- Work of several issues is built and judged as stacks of pull requests:
  `loop.py stacks` groups issues that touch the same files into ordered
  chains of at most five pull requests and about 2,500 changed lines, and
  `start build --stack` judges a chain in one loop, each item naming its pull
  request. `loop.py wait` marks a loop whose judges cannot run yet.
  `Stacks: off` keeps one loop per pull request.
- A judge lists a hand-written file over 1,500 lines or 50,000 bytes that the
  work creates or makes longer as an item.
- Installed into another `CLAUDE_HOME` that is an absolute path of letters,
  digits and `._/@+-`, the skill names `loop.py` by that path, right after the
  copy; for any other home the installer warns and leaves the skill as it is.
- `round` heads the fix list `Items to fix:`; the order to fix in (blocking
  items first, then the printed order) is in the fix prompts and the agent
  files.
- A build loop is always named after its branch (`docs/loops/<branch>/build/`),
  also after `start build --plan-loop <name>`; its state records the plan loop
  it came from as `plan_loop`, with the sha256 of the judged plan. With no loop
  open, `status` and `leftovers` show the checked-out branch's own build loop.
- A project agent file or folder that cannot be read stops `start` and `brief`
  with exit 3 and the path, as a link or an oversized file does; with
  `--agents fallback` it is passed over with a note.
- `status` and `brief` print a note for each area of a loop's `map.md` that
  has no notes file `areas/<name>.md` yet, or a note to rename an area whose
  name cannot be a file name, and `status --json` lists the same notes under
  `warnings`.
- `brief` refuses a round on unchanged work with one note per item that holds
  it, giving the `changes.md` row to write and the agent that writes it; a row
  marked with a round not counted yet does not count. `save` gives a 10 with
  a blocking item its own reason and hint.
- `save` refuses an item whose evidence names no place, neither a `file:line`
  nor a section of the plan or a criterion, and says which form it expects.
- `start` does not ask `gh pr view` for the base in a repository without a
  remote, and a remote that `gh` does not know as GitHub reads as no pull
  request, without a note.
- The installer leaves the `judge-loop` tests in the repo, and `/kit` no
  longer expects them in `~/.claude/skills/judge-loop/`.
- A command whose new `state.json` would be too big to save puts back what it
  changed in the loop folder: the files it wrote or moved (such as a brief's
  judge files) and, for `start`, the earlier loop it moved aside. The refusal
  says how many files were put back, or which could not be; once the cause
  is fixed, the same command runs as if the first try had not happened.
- `start build` on the base branch also names the way to a plan loop
  (`loop.py start plan --name <issue>-<slug>`), which still starts there; with
  `--stack` it names the stack's top branch to switch to.
- Without a remote, `start build` and `skip` on the base branch also say to
  move the base branch back to the commit the work began on. `skip` above the
  exempt size has its own question for the user; a question needs no skip
  record. `leftovers --dir` writes the repository and home folders as `<repo>`
  and `~`, and its checklist names each item in code. A refused role or id of
  `settle` and `save` is shown cut, odd characters as `?`. Size limits are
  decimal, as their messages say (200 kB is 200,000 bytes).

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

- The installer names the backup of your own agent or `frontend-design` folder
  by an absolute path without a doubled slash, also for a relative
  `CLAUDE_HOME` or one that ends in `/`.
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
