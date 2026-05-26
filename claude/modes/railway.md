## Railway Mode

Railway 部署專案工作流疊加層。部署相關工作透過 `@railway-deployment-engineer` 與 `railway-ops` 路由；非部署階段沿用預設代理。

| Phase | Agents / Skills | Notes |
|-------|-----------------|-------|
| analyze | default `/analyze` | No Railway-specific gating at analyze-time. |
| plan | default `/create-plan` | If plan touches Railway deploy config, include explicit `@railway-deployment-engineer` task per service. |
| implement | `@railway-deployment-engineer` for `railway.toml` / `railway` CLI / pipeline YAML tasks; default agents otherwise | Use the `railway-ops` skill for day-to-day ops against an already-authenticated context. |
| review | default `/review` + `@railway-deployment-engineer` consulted on Railway-touching diffs | Security-auditor remains primary on auth / secret / env changes. |
| merge | default `/ppr` | No Railway-specific merge gate. |

**Gotchas:**
- `railway-ops` STOPS and prompts if `railway whoami` fails — never auto-authenticates. Run `railway login` before invoking deploy commands.
- Railway CLI is user-driven (`npm i -g @railway/cli`). The skill prints an install prompt and stops if the CLI is absent.
- Secrets (env vars, service tokens) NEVER go in committed files. Use Railway's environment variable management in the dashboard, or store under names matched by `~/.claude/config/never-stage.txt`.
