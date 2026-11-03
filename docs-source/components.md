---
diataxis: reference
---

# Components

This page lists what pipelinekit v0.1.0 installs and what each part does.

> The hooks and skills are still being reviewed, so details may change in later releases. The hooks are guardrails that catch common mistakes. They are not a security boundary, and they do not replace review.

## Guard hooks

The installer adds these to the `hooks` section of `~/.claude/settings.json`. The scripts live in `~/.claude/hooks/`.

| Hook | Event / matcher | What it does |
|------|-----------------|--------------|
| `block-dangerous-commands.sh` | PreToolUse `Bash` | Blocks risky git, docker and destructive SQL commands, or asks before running them |
| `block-push-main.sh` | PreToolUse `Bash` | Blocks direct pushes to `main`/`master` |
| `block-stage-sensitive.sh` | PreToolUse `Bash` | Refuses to stage paths that match `config/never-stage.txt` |
| `env-scrub.py` | PreToolUse `Bash` | In CI, or with `CLAUDE_CODE_SCRUB_SUBPROCESS=1`, blocks commands that reference secret env vars |
| `validate-commit-msg.sh` | PreToolUse `Bash` | Checks commit messages against the conventional-commit format |
| `pre-edit-protect.sh` | PreToolUse `Edit\|Write` | Blocks edits to `.env`, credential and key files, and Claude settings files |
| `block-bare-repo-markers.py` | PreToolUse `Write` | Blocks writing bare-repo markers (`HEAD`, `config`, ...) at a repo root |
| `post-edit-format.sh` | PostToolUse `Edit\|Write` | Runs the project's formatter on the edited file |
| `scan-tool-output.sh` | PostToolUse `WebFetch\|Read` | Warns when fetched or read content looks like a prompt injection |

### Helper modules

The hooks import these modules. They are not wired into `settings.json`:

- `_never_stage_match.py` matches paths against `config/never-stage.txt`.
- `_pathguard.py` holds the shared path checks.
- `_promptguard.py` is the prompt-injection scanner used by `scan-tool-output.sh`.
- `denial_tracker.py` records hook denials and prints an advisory when the same denial keeps repeating.

### The never-stage list

`config/never-stage.txt` is the single list of paths that must not be committed. It covers env files, credentials, keys, and the local `docs/` workflow notes. Edit the copy in `~/.claude/config/` to change it for your machine. The installer overwrites that copy on the next run, so put changes you want to keep in the repo's `claude/config/never-stage.txt`.

### Repo git hooks

In the pipelinekit repo only, the installer adds:

- `commit-msg`, which runs `commit-msg-wrapper.sh` and the same conventional-commit check;
- `pre-commit`, which runs `scan-secrets-staged.sh`. That script runs `gitleaks` over staged changes. If `gitleaks` is not installed, it prints a notice and lets the commit through.

## Skills

<div data-snippet="skill-catalog-grid"></div>

| Skill | Use it for |
|-------|------------|
| `commit-conventions` | Conventional commit format, message rules and the no-attribution policy |
| `security-conventions` | ASP.NET Core security conventions (anti-forgery, authorization, secret storage, parameterized queries, HTTPS) |
| `dotnet-conventions` | .NET architecture, DI, data access and testing conventions |
| `deploy` | Deploy and operate apps on Vercel, Railway, Render, DigitalOcean App Platform or Azure through each provider's CLI. If a CLI is missing or not logged in, it stops and asks you |
| `docs-writer` | Render markdown into self-contained HTML pages under `documentation/` with `render.py` and `template.html` |
| `expo` | Expo workflow: EAS Build and Update, dev client, Expo Router, push notifications |
| `ios` | Xcode with the Claude Agent SDK: project setup, simulator, code signing, TestFlight |

In 0.1.0, `deploy` replaces the five separate `*-ops` skills and the per-provider deployment agents.

## Agent

`docs-writer` is a documentation subagent. It writes application docs to `documentation/`, never to `docs/`, and uses the `docs-writer` skill to render them.

## CLAUDE.md template

`claude/CLAUDE.md.template` is about 40 lines of English with no imported rule files. The installer fills in `${USER_NAME}`, `${USER_EMAIL}` and `${CLAUDE_HOME}` and writes the result to `~/.claude/CLAUDE.md`. It covers:

- your identity;
- git rules: commit only when asked, conventional commits, no AI attribution, the never-stage list, `.git/info/exclude` for Claude-specific ignores, and no direct pushes to `main`;
- the `docs/` (local, never committed) and `documentation/` (committed) split;
- a base-branch detection snippet;
- the deploy CLIs.

## MCP servers

| Server | Installed by default | Notes |
|--------|----------------------|-------|
| serena | Yes, unless you pass `--no-serena` | Symbol-level code navigation. Installed with `uv` from a pinned commit and registered at user scope in `~/.claude.json`. A project `.mcp.json` entry takes precedence |
| context7 | No | Library and framework docs. Copy its entry from `.mcp.json.template` into a project's `.mcp.json` |

## What is not included

Plan mode, the Workflow tool, `/code-review`, `/security-review`, `/simplify`, the Explore and Plan agents, auto-memory, worktree isolation, `/loop` and `/schedule` are all built into Claude Code. pipelinekit no longer provides its own versions. See [Upgrading from 0.0.1](upgrading.html#what-was-removed) for how the old components map to these built-ins.
