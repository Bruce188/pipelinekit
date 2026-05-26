## Render Mode

Render 部署專案工作流疊加層。適用 Web Services, Workers, Cron Jobs, Static Sites。部署工作透過 `@render-deployment-engineer` 與 `render-ops` 路由；非部署階段沿用預設代理。

| Phase | Agents / Skills | Notes |
|-------|-----------------|-------|
| analyze | default `/analyze` | No Render-specific gating at analyze-time. |
| plan | default `/create-plan` | If plan touches Render deploy config, include explicit `@render-deployment-engineer` task per service. |
| implement | `@render-deployment-engineer` for `render.yaml` Blueprint / `render` CLI tasks; default agents otherwise | Use the `render-ops` skill for day-to-day ops against an already-authenticated context. |
| review | default `/review` + `@render-deployment-engineer` consulted on Render-touching diffs | Security-auditor remains primary on auth / secret / env changes. |
| merge | default `/ppr` | No Render-specific merge gate. |

**Gotchas:**
- `render-ops` STOPS and prompts if authentication fails — never auto-authenticates. Set `RENDER_API_KEY` or run `render login` before invoking deploy commands.
- Secrets (API keys, env vars) NEVER go in committed files. Use Render's environment group management in the dashboard.
- `render.yaml` Blueprint deploys are not idempotent across services with the same name — confirm the target service before re-running a deploy command.
