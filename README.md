# pipelinekit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml)

A small Claude Code config kit. It contains guard hooks, permission rules,
global git hooks, a few skills, a short `CLAUDE.md` template, and an installer
that copies them into `~/.claude` while leaving everything else in that
directory alone.

Up to 0.0.1, pipelinekit was a full multi-agent pipeline kit with its own
orchestrator, review panel, persona agents and memory stack. Current Claude
Code covers most of that natively, so v0.1.0 drops those parts and keeps only
what Claude Code does not ship. See [What was removed](#what-was-removed) and
the [CHANGELOG](CHANGELOG.md).

> **Status:** the hooks and skills are still being reviewed, so details may
> change in later releases. The hooks are guardrails that catch common
> mistakes. They are not a security boundary.

## What you get

### Guard hooks and permissions

The installer merges `claude/config/settings.template.json` into `~/.claude/settings.json`.

| Piece | Where | What it does |
|------|-------|--------------|
| `permissions.deny` | settings | Claude can't read or edit `.env*` (not `.env.example`), keys, `~/.ssh`, `~/.aws`, `~/.kube/config`, `~/.config/gh/hosts.yml`, credentials files. Holds in bypass mode |
| `permissions.ask` | settings | Prompts before editing Claude settings/hooks or `~/.gitconfig`, and before `reset --hard`, `clean -f`, force push, `branch -D`, `checkout/restore .`. Prompts in bypass mode too |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` | settings `env` | Strips credentials from subprocess environments |
| `bash-guard.py` | PreToolUse `Bash` (`if`: git, docker, podman, curl, wget, psql, mysql, mariadb, sqlite3) | Blocks pushes to other remotes or main, remote changes, global git config writes, hook bypasses (`--no-verify`, `core.hooksPath`), staging `config/never-stage.txt` paths or bulk staging, sensitive docker mounts, and `curl \| sh`. Asks before `docker --privileged` and DROP/TRUNCATE |
| `block-bare-repo-markers.py` | PreToolUse `Edit`/`Write` | Blocks assembling a bare git repo (HEAD + config/objects/refs) in the working directory or one level down |
| `post-edit-format.sh` | PostToolUse `Edit`/`Write` | Runs the project's own prettier on ts/js/json/yaml |

### Git hooks

`claude/git-hooks/` is installed to `~/.claude/git-hooks` and, if you agree, set as the global `core.hooksPath`. Each hook runs the repository's own `.git/hooks/<name>` or `.githooks/<name>` afterwards.

| Hook | What it does |
|------|--------------|
| `commit-msg` | Conventional commits (`feat fix refactor docs test chore perf style build ci revert`, scopes, `!`). Rejects wip (outside `.claude/worktrees/`), AI attribution and emoji. Lets `Merge`, `Revert "`, `fixup!`/`squash!`/`amend!` through |
| `pre-commit` | `gitleaks` scan of staged changes. Warns and allows if gitleaks is missing. `PIPELINEKIT_ALLOW_SECRET=1` skips one commit |
| `pre-push` | Refuses pushes to `main`/`master`. `ALLOW_MAIN_PUSH=1` overrides (humans only; bash-guard refuses it for Claude) |

A repo with its own local `core.hooksPath` (husky, pre-commit framework, or a manual setting) bypasses these. Run `git config --show-origin core.hooksPath` inside it to check.

### Skills

| Skill | Use it for |
|-------|------------|
| `dotnet-conventions` | .NET layering, DI, EF Core migrations, testing (FluentAssertions 7.x pin), BackgroundService rules, target-framework support dates, plus ASP.NET Core security in `references/security.md` |
| `deploy` | Router for Vercel, Railway, Render, DigitalOcean App Platform and Azure (Container Apps, App Service): auth check, deploy, secrets without argv, verify, logs, rollback, and trading-bot overlap. Per-provider detail in `references/` |
| `exchange-api-keys` | Exchange API keys for CryptoBargain and FundingRateArb: where they load from, never logging them, testnet vs mainnet, withdrawal-disabled and IP-restricted scopes, storage, rotation, leak runbook |
| `docs-writer` | Render `docs-source/*.md` into self-contained HTML pages under `documentation/`, with optional data-driven interactive snippets |
| `mobile` | Android (Kotlin/Compose) builds and device access from WSL2, iPhone home-screen web apps, Expo/EAS cloud builds for iOS, release and security checklist |

### CLAUDE.md template

`claude/CLAUDE.md.template` is about 50 lines long. It covers your identity,
git rules (conventional commits, no AI attribution, never-stage list, no
direct pushes to `main`), the `docs/` and `documentation/` split, base-branch
detection, serena vs Grep, GitHub issue/PR habits with `gh`, and the deploy
CLIs. The installer renders it to
`~/.claude/CLAUDE.md`.

### MCP servers

- **serena** (symbol-level code navigation) is installed with `uv` at a pinned
  commit and registered at user scope in `~/.claude.json`. Skip it with
  `--no-serena`.
- **context7** (library docs) is optional. Copy its entry from
  `.mcp.json.template` into a project's `.mcp.json` if you want it.

## Install

Requirements: `bash`, `git` and `python3`. `uv` is needed only for serena.

```bash
git clone https://github.com/Bruce188/pipelinekit.git
cd pipelinekit
bash scripts/install.sh            # add --no-serena to skip serena, --git-hooks / --no-git-hooks to answer the git prompt
```

You can safely run the installer again to update. It:

1. copies the hooks, git hooks, skills and `config/never-stage.txt` into
   `~/.claude`, overwriting them in place without moving the directory;
2. removes skills, hooks and the agent that earlier 0.1.0 builds installed
   (`commit-conventions`, `security-conventions`, `expo`, `ios`, the old guard
   hooks, `agents/docs-writer.md`), but only if they are unmodified kit copies;
   edited ones are kept with a warning;
3. renders `~/.claude/CLAUDE.md` from the template, first backing up an existing
   one to `CLAUDE.md.bak-<timestamp>`;
4. backs up `settings.json` to `settings.json.bak-<timestamp>`, then merges in
   `claude/config/settings.template.json`: the kit's hook wiring replaces its
   old entries, hook entries whose script no longer exists are removed, the
   deny/ask rules are added after yours, `env` gets the scrub flag, and
   commit/PR attribution is turned off. Other settings stay as they are;
5. asks whether to set the global `core.hooksPath` to `~/.claude/git-hooks`
   (never changes an existing value);
6. installs serena and registers it in `~/.claude.json`, backing that file up
   first;
7. runs `scripts/verify.sh`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLAUDE_HOME` | `~/.claude` | Install target |
| `USER_NAME` / `USER_EMAIL` | git config | Identity written into `CLAUDE.md` |
| `SERENA_REF` | pinned SHA | serena commit to install |
| `CLAUDE_INSTALL_SKIP_SERENA=1` | unset | Same as `--no-serena` |
| `PIPELINEKIT_GIT_HOOKS=1` / `0` | ask (no if not a terminal) | Same as `--git-hooks` / `--no-git-hooks` |

The devcontainer runs the installer when the container is created. Bootstrap
scripts for Oracle and Hetzner VMs are in `scripts/cloud/`.

## What was removed

Each of these was dropped because a built-in Claude Code feature covers it.

| Removed in 0.1.0 | Use instead |
|------------------|-------------|
| `/pipeline` orchestrator, planner and goal-setter agents, TDD gates | Plan mode, the Workflow tool, built-in Plan agent |
| Review panel (code-reviewer, security-auditor and similar agents), `simplify` skill | `/code-review`, `/security-review`, `/simplify` |
| Persona agents and `persona` | Built-in Explore and Plan agents |
| agentmemory, `memory-journal` hook, memory migration script | Native auto-memory |
| codegraph, graphify, local-rag, sequential-thinking | Explore agent, plus serena for symbol navigation |
| Worktree agent rules and `verify-worktree-commit` hook | Built-in worktree isolation |
| `research` skill, overnight/loop machinery | `/loop`, `/schedule` |
| Context and compaction hooks (`context-warning`, `post-compact-context`, `session-start-*`, ...) | Built-in auto-compact |
| `strip-ai-attribution` hook | The `attribution` setting (the installer turns it off) |
| `claude-md-enhancer`, `write-a-skill`, `build-hook`/`test-hooks` | `/init`, `skill-creator`, `update-config` |
| `vercel-ops`, `railway-ops`, `render-ops`, `digitalocean-ops`, `azure-ops` and the per-provider deployment agents | The `deploy` skill |
| caveman, model overlays, `modes/`, `rules/`, host adapters | Dropped with no replacement |

The [CHANGELOG](CHANGELOG.md) lists every removed file.

## Upgrading from 0.0.1

The 0.0.1 installer copied the whole kit into `~/.claude`. The new installer
only adds and overwrites files. It does not delete the old ones, and it does
not touch MCP servers other than serena. To upgrade cleanly:

**1. Back up.**

```bash
cp -a ~/.claude ~/.claude.bak-0.0.1
cp -p ~/.claude.json ~/.claude.json.bak-0.0.1
```

**2. Remove the old kit files.** If you edited `rules/` or `modes/`, or stored
anything in `memory/`, check those directories first and keep what you need.

```bash
cd ~/.claude
rm -rf commands host-adapters lib memory model-overlays modes rules snippets tresor-resources
rm -rf agents/personas agents/tests
rm -f agents/{CLAUDE,INDEX,NOTICE,README}.md \
  agents/{azure,digitalocean,railway,render,vercel}-deployment-engineer.md \
  agents/{claude-md-guardian,code-reviewer,debugger,deployment-engineer,incident-responder}.md \
  agents/{mobile-dev,performance-tuner,production-probe,refactor-expert,security-auditor}.md \
  agents/{spec-tracer,symbol-verifier,tdd-implementer,tdd-test-writer,test-engineer,uat-runner}.md
rm -f skills/{CLAUDE,INDEX}.md
rm -rf skills/{analyze,ascii-diagram,azure-ops,build-hook,caveman-mode,claude-md-enhancer,code-health} \
  skills/{codegraph-init,context-dump,create-plan,dependency-auditor,digest-memories,digitalocean-ops} \
  skills/{document-release,financial-data-analyst,fix-issue,graphify-init,handoff-create,implement-plan} \
  skills/{incident,landing-report,learn,new-branch,pipeline,playwright,post-merge,ppr,railway-ops} \
  skills/{render-ops,research,review,secret-scanner,simplify,tdd,test-hooks,uat,vercel-ops} \
  skills/{write-a-skill,zoom-out}
rm -f hooks/{CLAUDE.md,agent-caveman-gate.sh,claude-md-guard.py,context-budget-advisor.py} \
  hooks/{context-warning.py,cost_log.py,kill-rogue-mcp-daemon.sh,mcp-rss-cap.sh,memory-journal.sh} \
  hooks/{notify-emit.sh,post-compact-context.sh,session-start-caveman.sh,session-start-context.sh} \
  hooks/{skill_budget.py,stop-completion-gate.sh,strip-ai-attribution.sh,subagent-first-nudge.sh} \
  hooks/{tdd-order-check.sh,tdd-red-phase-gate.sh,test-logger.sh,validate-task-spec.py} \
  hooks/verify-worktree-commit.sh
```

Old `skills/simplify` and `skills/review` folders can shadow the built-in
`/simplify` and `/review`, so make sure they are gone.

**3. Re-run the installer.** It rewrites `CLAUDE.md`, which no longer imports
`rules/` or `modes/`. It also prunes `settings.json` hook entries whose script
you just deleted, removes the old guard hooks and skills it replaced (only
unmodified copies), and asks whether to enable the global git hooks.

```bash
cd pipelinekit && git pull && bash scripts/install.sh
```

**4. Clean up `settings.json`.** The installer replaces its own hook entries
and prunes the ones that point to scripts missing from `~/.claude/hooks/`. Open
`~/.claude/settings.json` and remove anything else you no longer want from the
old kit. For example, 0.0.1 set `env.CLAUDE_CODE_DISABLE_1M_CONTEXT` to `"1"`
by default. A backup from step 3 is at `settings.json.bak-<timestamp>`.

**5. Remove the old MCP servers.** At user scope:

```bash
for s in agentmemory codegraph graphify local-rag sequential-thinking; do
  claude mcp remove "$s" -s user 2>/dev/null
done
```

Also delete those entries from any project `.mcp.json` the old installer
wrote. Then run `claude mcp list` to confirm that only the servers you want
are left.

**6. Verify.**

```bash
bash scripts/verify.sh
```

## Documentation

The HTML docs are in [`documentation/`](documentation/index.html) and are
rendered from the markdown in `docs-source/`:

```bash
python3 claude/skills/docs-writer/render.py   # renders every docs-source/*.md; or: --root /path/to/repo
```

## Tests

```bash
for t in claude/hooks/tests/test_*.sh; do bash "$t"; done   # git hooks
python3 -m pytest claude/hooks/tests
bash tests/test_install.sh
bash claude/skills/docs-writer/tests/test_render.sh
bash claude/skills/docs-writer/tests/test_richness_threshold.sh
```

## License

MIT, see [LICENSE](LICENSE).
