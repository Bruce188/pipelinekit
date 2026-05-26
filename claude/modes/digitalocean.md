## DigitalOcean Mode

DigitalOcean App Platform 部署專案工作流疊加層。部署工作透過 `@digitalocean-deployment-engineer` 與 `digitalocean-ops` 路由；非部署階段沿用預設代理。

| Phase | Agents / Skills | Notes |
|-------|-----------------|-------|
| analyze | default `/analyze` | No DigitalOcean-specific gating at analyze-time. |
| plan | default `/create-plan` | If plan touches App Platform config, include explicit `@digitalocean-deployment-engineer` task per component. |
| implement | `@digitalocean-deployment-engineer` for `.do/app.yaml` App Spec / `doctl` CLI tasks; default agents otherwise | Use the `digitalocean-ops` skill for day-to-day ops against an already-authenticated context. |
| review | default `/review` + `@digitalocean-deployment-engineer` consulted on DO-touching diffs | Security-auditor remains primary on auth / secret / env changes. |
| merge | default `/ppr` | No DigitalOcean-specific merge gate. |

**Gotchas:**
- `digitalocean-ops` STOPS and prompts if `doctl auth status` fails — never auto-authenticates. Run `doctl auth init` before invoking deploy commands.
- DigitalOcean CLI (`doctl`) is user-driven. The skill prints an install prompt and stops if the CLI is absent.
- Secrets (API tokens, env vars) NEVER go in committed files. Use App Platform's environment variable management in the dashboard or `.do/app.yaml` with `value_from` references.
- App Spec deploys (`doctl apps update`) are idempotent for env/config changes but create new deployments — confirm the target app ID before re-running.
