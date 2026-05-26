| Skill | Description |
|---|---|
| `analyze` | Analyze an existing codebase or defined task. Asks 2 focused questions, then produces docs/analysis.md. Use at the start of an existing project workflow, before /create-plan. |
| `ascii-diagram` | Generate an ASCII architecture diagram for the current project or a described system |
| `azure-ops` | Azure CLI (`az`) wrapper for common ops — resource listing, deploy (App Service / Container Apps / Function Apps), log tail, app-service restart. STOPS and prompts the user if `az account show` fails — never auto-authenticates. Use when running day-to-day Azure operations against an already-authenticated context. |
| `build-hook` | Generate a Claude Code hook from a description. Creates the shell script and settings.json entry. Use when user wants to add workflow automation, enforce a rule, or react to Claude Code events. |
| `caveman-mode` | Toggle response verbosity (caveman-style terse fragments vs normal English). Default wenyan-ultra. |
| `claude-md-enhancer` | Analyzes, generates, and enhances CLAUDE.md files for any project type using best practices, modular architecture support, and tech stack customization. Use when setting up new projects, improving existing CLAUDE.md files, or establishing AI-assisted development standards. |
| `code-health` | Comprehensive codebase health assessment with quality metrics, test coverage, documentation, and maintainability analysis. Use for quality gates, pre-release checks, or periodic health monitoring. |
| `codegraph-init` | Initialize codegraph index in the current project. Walks the 50k-file pre-flight gate. Use when starting symbolic-graph work in a new repo. |
| `commit-conventions` | Conventional commit format, message rules, and attribution policy. Loaded when writing commit messages, creating PRs, or merging branches. |
| `context-dump` | Save current session context to docs/context-dump.md for handoff or resumption |
| `create-plan` | Generate docs/plan.md AND docs/prompts.md together — always both, never one without the other. Initializes or amends docs/progress.md. Use after /analyze (existing project) or after /clear following /pipeline Step 0 Charter Discovery (new project — preferred). |
| `dependency-auditor` | Check dependencies for known vulnerabilities using npm audit, pip-audit, etc. Use when package.json or requirements.txt changes, or before deployments. Alerts on vulnerable dependencies. Triggers on dependency file changes, deployment prep, security mentions. |
| `digest-memories` | Synthesize per-project memory proposals from the session journal written by memory-journal.sh. User-invoked via /digest-memories slash command. Reads recent sessions, proposes additions to ~/.claude/projects/<slug>/memory/, requires user confirmation before writing. |
| `digitalocean-ops` | Deploy and verify DigitalOcean App Platform apps when the charter targets digitalocean |
| `docs-writer` | Documentation skill — renders markdown to rich, interactive, self-contained HTML for documentation/. Uses the shipped template + render.py. Refuses to write markdown to documentation/. |
| `document-release` | Update application documentation in `documentation/` after a release. Reads the most recent merge commit (or `--since <sha>`) and `docs/progress.md`, then writes/updates `documentation/` and lands a separate `docs:` commit on the current branch. Runnable ad-hoc outside the `/pipeline` workflow. |
| `dotnet-conventions` | .NET architecture, DI, data access, and testing conventions. Loaded when working with C#, .NET, controllers, services, entities, repositories, or solution files. |
| `expo` | Expo developer workflow — managed vs. bare workflow, EAS Build, EAS Update (OTA), dev-client, Expo Router, expo-modules-core, push notifications via Expo's APNs/FCM gateway |
| `financial-data-analyst` | Automatically analyzes financial and trading data using Python to calculate performance metrics, technical indicators, risk analysis, and portfolio statistics with visualizations |
| `fix-issue` | Fix a GitHub issue by number. Reads the issue, implements a fix with TDD, and commits. |
| `graphify-init` | Initialize graphify build in the current project. Walks the 50k-file pre-flight gate. Use when starting graph-knowledge work in a new repo. |
| `handoff-create` | Analyze the current conversation and create a handoff document for continuing this work in a fresh context |
| `implement-plan` | Execute all remaining tasks from docs/progress.md with verification after each. Parallelizes phases with independent tasks by default. Stops on verification failure. Run again to resume after fixing a failure. |
| `incident` | Triage a failing post-merge verification gate using @incident-responder. Gathers failure context from logs and dispatches the incident-responder agent with a structured prompt. Use when /post-merge reports a verification failure or any post-merge anomaly. |
| `ios` | Xcode 26.3 + Anthropic Claude Agent SDK integration — project setup, in-editor usage, Agent SDK API surface, simulator integration, code signing & TestFlight workflows |
| `landing-report` | Pre-push version-slot collision detector. Reads VERSION or package.json:version, compares against existing git tags, prints a one-line status. Silent skip when neither marker is present. Invoked from /ppr Step 1.6. |
| `learn` | Read interface for pipelinekit's per-project learnings journal. Reads ~/.pipelinekit/projects/<slug>/learnings.jsonl. The write path is the inline shell helper at claude/lib/learn-append.sh — invoked best-effort from pipeline Path A at post-review and post-merge. |
| `new-branch` | Create a conventional feature branch from main/master. Use when starting new work, before first commit, or when on main/master. |
| `pipeline` | Autonomous pipeline orchestrator. Processes a feature list through the full workflow (analyze → plan → implement → review → merge) with zero human intervention. Supports --dry-run and --restart-from. |
| `playwright` | Native Python browser automation using Playwright for navigation, interaction, screenshots, and form filling |
| `post-merge` | Clean up after PR merge. Switches to main, pulls latest, deletes merged feature branch locally and remotely. Use after a PR has been merged on GitHub. |
| `ppr` | Push + PR. Push committed changes to origin and open a pull request. Run after /review passes. Human approves the PR separately. |
| `railway-ops` | Deploy and verify Railway projects when the charter targets railway |
| `render-ops` | Deploy and verify Render services when the charter targets render |
| `research` | Karpathy autoresearch loop — hypothesize, mutate one file, run benchmark, keep-or-reset, append TSV row. Repeat until budget or iteration cap. |
| `review` | Multi-agent parallel review with auto-scaling agent selection. Scales from 2 agents (small diffs) to 6-agent teams (large diffs). Teams mode is default-on; pass --no-teams to opt out. Supports --scope, --force, --no-teams. |
| `secret-scanner` | Detect exposed secrets, API keys, credentials, and tokens in code. Use before commits, on file saves, or when security is mentioned. Prevents accidental secret exposure. Triggers on file changes, git commits, security checks, .env file modifications. |
| `security-conventions` | ASP.NET Core security conventions — anti-forgery, authorization, secret storage, parameterized queries, HTTPS. Loaded when working with controllers, API endpoints, authentication, authorization, or user input handling. |
| `simplify` | Post-green reductive refactor: remove unused helpers, dead branches, over-generalized abstractions, and redundant null checks; revert on test failure. |
| `tdd` | Test-driven development with red-green-refactor loop. Use when user wants to build features or fix bugs using TDD, mentions "red-green-refactor", wants integration tests, or asks for test-first development. |
| `test-hooks` | Run hook tests and summarize results. Auto-loads when working on files under .claude/hooks/. Use to verify hook correctness after changes to hook scripts or tests. |
| `vercel-ops` | Vercel CLI (`vercel`) wrapper for common ops — project listing, deploy (preview / production), `vercel inspect` verification, log tail, redeploy. STOPS and prompts the user if `vercel whoami` fails — never auto-authenticates. Use when running day-to-day Vercel operations against an already-authenticated context. |
| `write-a-skill` | Create new agent skills with proper structure, progressive disclosure, and bundled resources. Use when user wants to create, write, or build a new skill. |
| `zoom-out` | Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you're unfamiliar with a section of code or need to understand how it fits into the bigger picture. |

## Generation

This file is auto-generated by `python3 scripts/build_skills_index.py`. Do not edit by hand — re-run the script.
