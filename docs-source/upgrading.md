---
diataxis: how-to
---

# Upgrading from 0.0.1

How to move from the 0.0.1 pipeline kit to the 0.1.0 config kit: what was removed, what replaces it, and how to clean up an existing `~/.claude`.

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

The [CHANGELOG](https://github.com/Bruce188/pipelinekit/blob/main/CHANGELOG.md) lists every removed file.

## Upgrade steps

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

<details markdown="1">
<summary>Commands that delete the 0.0.1 directories, agents, skills and hooks</summary>

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

</details>

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

## Rolling back

Your 0.0.1 setup is still in the backups from step 1. To go back, move the current directory aside rather than deleting it, so sessions and memory created since the upgrade are not lost:

```bash
mv ~/.claude ~/.claude.0.1.0
cp -a ~/.claude.bak-0.0.1 ~/.claude
cp -p ~/.claude.json.bak-0.0.1 ~/.claude.json
```
