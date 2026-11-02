# Changelog

## 0.1.0 — 2026-11-02

Trimmed to a small config kit. Current Claude Code covers most of what the
kit used to ship, so those parts are gone.

### Kept

- Guard hooks: `block-stage-sensitive` (+ `_never_stage_match`, `_pathguard`,
  `denial_tracker`, `config/never-stage.txt`), `block-dangerous-commands`,
  `block-push-main`, `env-scrub`, `scan-tool-output` (+ `_promptguard`),
  `block-bare-repo-markers`, `validate-commit-msg`, `pre-edit-protect`,
  `post-edit-format`, and the repo git hooks `commit-msg-wrapper` and
  `scan-secrets-staged`, with their tests.
- Skills: `commit-conventions`, `security-conventions`, `dotnet-conventions`,
  `docs-writer` (with its render lib), `expo`, `ios`.
- Agent: `docs-writer`.
- serena MCP registration (pinned commit); context7 stays optional.

### Changed

- New `deploy` skill replaces `vercel-ops`, `railway-ops`, `render-ops`,
  `digitalocean-ops`, `azure-ops` and the per-provider deployment-engineer
  agents.
- `CLAUDE.md.template` rewritten: ~40 lines, English, no imported rule files.
- `install.sh` rewritten (2,560 to ~250 lines). It now overlays files in place
  instead of moving `~/.claude` aside, prunes `settings.json` hook entries whose
  script is gone, and sets `attribution` to empty strings (no co-author
  trailer or PR footer).
- `verify.sh` checks the kept hooks and skills, that every `settings.json`
  hook command resolves, and that attribution is off.
- `scan-tool-output.sh` now imports its scanner from the installed hooks dir.

### Removed

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
