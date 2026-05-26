## Vercel Mode

Per-project workflow overlay for Vercel deployments. Use when a project ships to Vercel. Routes deployment-shaped work through `@vercel-deployment-engineer` and the `vercel-ops` skill; non-deployment phases continue to use the default pipeline agents.

| Phase | Agents / Skills | Notes |
|-------|-----------------|-------|
| analyze | default `/analyze` | No Vercel-specific gating at analyze-time. |
| plan | default `/create-plan` | If plan touches Vercel deploy config, include explicit `@vercel-deployment-engineer` task per project. |
| implement | `@vercel-deployment-engineer` for `vercel.json` / `vercel` CLI / build-config tasks; default agents otherwise | Use the `vercel-ops` skill for day-to-day ops against an already-authenticated context. |
| review | default `/review` + `@vercel-deployment-engineer` consulted on Vercel-touching diffs | Security-auditor remains primary on auth / secret / env changes. |
| merge | default `/ppr` | No Vercel-specific merge gate. |

**Gotchas:**
- `vercel-ops` STOPS and prompts if `vercel whoami` fails — never auto-authenticates. Run `vercel login` before invoking deploy commands.
- Vercel CLI is user-driven (`npm i -g vercel`). The skill prints an install prompt and stops if the CLI is absent.
- Secrets (env vars, project tokens) NEVER go in committed files. Use Vercel's environment variable management in the dashboard, or store under names matched by `~/.claude/config/never-stage.txt`.
- Preview vs production deploys are not interchangeable — confirm the target environment with `--prod` or omission before re-running a deploy command.
