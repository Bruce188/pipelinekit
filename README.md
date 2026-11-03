# pipelinekit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce188/pipelinekit/actions/workflows/ci.yml)

A small Claude Code config kit. It contains guard hooks, a few skills, one docs
agent, a short `CLAUDE.md` template, and an installer that copies them into
`~/.claude` while leaving everything else in that directory alone.

Up to 0.0.1, pipelinekit was a full multi-agent pipeline kit with its own
orchestrator, review panel, persona agents and memory stack. Current Claude
Code covers most of that natively, so v0.1.0 drops those parts and keeps only
what Claude Code does not ship. See [What was removed](#what-was-removed) and
the [CHANGELOG](CHANGELOG.md).

> **Status:** the hooks and skills are still being reviewed, so details may
> change in later releases. The hooks are guardrails that catch common
> mistakes. They are not a security boundary.

## What you get

### Guard hooks

The installer adds these to `~/.claude/settings.json`.

| Hook | Event | What it does |
|------|-------|--------------|
| `block-dangerous-commands.sh` | PreToolUse `Bash` | Blocks risky git, docker and destructive SQL commands, or asks before running them |
| `block-push-main.sh` | PreToolUse `Bash` | Blocks direct pushes to `main`/`master` |
| `block-stage-sensitive.sh` | PreToolUse `Bash` | Refuses to stage paths listed in `config/never-stage.txt` (env files, credentials, keys, local `docs/` workflow notes) |
| `env-scrub.py` | PreToolUse `Bash` | In CI, or with `CLAUDE_CODE_SCRUB_SUBPROCESS=1`, blocks commands that reference secret env vars |
| `validate-commit-msg.sh` | PreToolUse `Bash` | Checks commit messages against the conventional-commit format |
| `pre-edit-protect.sh` | PreToolUse `Edit`/`Write` | Blocks edits to `.env`, credential and key files, and Claude settings files |
| `block-bare-repo-markers.py` | PreToolUse `Write` | Blocks writing bare-repo markers (`HEAD`, `config`, ...) at a repo root |
| `post-edit-format.sh` | PostToolUse `Edit`/`Write` | Runs the project's formatter on the edited file |
| `scan-tool-output.sh` | PostToolUse `WebFetch`/`Read` | Warns when fetched or read content looks like a prompt injection |

`_pathguard.py`, `_promptguard.py`, `_never_stage_match.py` and
`denial_tracker.py` are helper modules that the hooks import. They are not
hooks themselves.

`commit-msg-wrapper.sh` and `scan-secrets-staged.sh` are installed as git
`commit-msg` and `pre-commit` hooks in this repository only.

### Skills

| Skill | Use it for |
|-------|------------|
| `commit-conventions` | Conventional commit format, message rules and the no-attribution policy |
| `security-conventions` | ASP.NET Core security conventions (anti-forgery, authorization, secret storage, parameterized queries, HTTPS) |
| `dotnet-conventions` | .NET architecture, DI, data access and testing conventions |
| `deploy` | Deploy and operate apps on Vercel, Railway, Render, DigitalOcean App Platform or Azure through each provider's CLI (auth check, deploy, verify, logs, rollback) |
| `docs-writer` | Render markdown into self-contained HTML pages under `documentation/` |
| `expo` | Expo workflow: EAS Build and Update, dev client, Expo Router, push notifications |
| `ios` | Xcode with the Claude Agent SDK: project setup, simulator, code signing, TestFlight |

### Agent

`docs-writer` is a documentation subagent that pairs with the `docs-writer`
skill.

### CLAUDE.md template

`claude/CLAUDE.md.template` is about 40 lines long. It covers your identity,
git rules (conventional commits, no AI attribution, never-stage list, no
direct pushes to `main`), the `docs/` and `documentation/` split, base-branch
detection and the deploy CLIs. The installer renders it to
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
bash scripts/install.sh            # add --no-serena to skip serena
```

You can safely run the installer again to update. It:

1. copies the hooks, skills, agent and `config/never-stage.txt` into
   `~/.claude`, overwriting them in place without moving the directory;
2. renders `~/.claude/CLAUDE.md` from the template, first backing up an existing
   one to `CLAUDE.md.bak-<timestamp>`;
3. backs up `settings.json`, merges in the hook wiring, removes hook entries
   whose script no longer exists, and turns commit/PR attribution off. Other
   settings stay as they are;
4. installs serena and registers it in `~/.claude.json`, backing that file up
   first;
5. runs `scripts/verify.sh`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLAUDE_HOME` | `~/.claude` | Install target |
| `USER_NAME` / `USER_EMAIL` | git config | Identity written into `CLAUDE.md` |
| `SERENA_REF` | pinned SHA | serena commit to install |
| `CLAUDE_INSTALL_SKIP_SERENA=1` | unset | Same as `--no-serena` |

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
you just deleted.

```bash
cd pipelinekit && git pull && bash scripts/install.sh
```

**4. Clean up `settings.json`.** The installer only prunes hook entries that
point to scripts that are missing from `~/.claude/hooks/`. Open
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
python3 claude/skills/docs-writer/render.py   # renders every docs-source/*.md
```

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
