---
name: deploy
description: Deploy and operate apps on Vercel, Railway, Render, DigitalOcean App Platform, or Azure via each provider's CLI — auth preflight, deploy (preview/production), verify, logs, redeploy/rollback. Stops and asks the user when the CLI is missing or not authenticated; never logs in on the user's behalf. Use for day-to-day deploy work against an already-authenticated context.
allowed-tools:
  - Read
  - Bash
---

# deploy

One skill for all supported providers. Pick the provider from the repo
(`vercel.json`, `railway.json`/`railway.toml`, `render.yaml`, `.do/app.yaml`,
`azure.yaml`/`host.json`) or ask the user.

## Rules (all providers)

1. **Preflight auth first.** Run the provider's whoami command. If it fails,
   STOP and tell the user to authenticate in their own terminal. Never run
   `login`, never switch team/project/environment/subscription automatically.
2. **Never print secrets.** Do not echo tokens (`VERCEL_TOKEN`, `RAILWAY_TOKEN`,
   `RENDER_API_KEY`, `DIGITALOCEAN_ACCESS_TOKEN`, `AZURE_*`) or env values.
   Do not commit `.vercel/`, `.railway/`, or local credential files.
3. **Production needs explicit user intent.** Default to preview/staging.
4. **Verify every deploy:** HTTP status (`curl -sI "$URL" | head -1`), provider
   status, then logs. Report the URL and the status line.
5. **Rollback = redeploy a known-good build**, not a force push.

## Install

| Provider | CLI | Install |
|----------|-----|---------|
| Vercel | `vercel` | `npm i -g vercel` |
| Railway | `railway` | `npm i -g @railway/cli` |
| Render | `render` | user installs (`brew install render` or GitHub release) |
| DigitalOcean | `doctl` | user installs (package manager or GitHub release) |
| Azure | `az` | user installs (Microsoft docs) |

If the CLI is not on `PATH`, stop and print the install line.

## Vercel

```bash
vercel whoami                       # preflight
vercel project ls; vercel ls        # projects, recent deployments
vercel                              # preview deploy (prints URL)
vercel build && vercel deploy --prebuilt   # build locally, upload output
vercel --prod                       # production (explicit intent only)
vercel promote <deployment-url>     # promote a preview to production
vercel inspect <url> --wait         # wait for READY / ERROR
vercel logs <url>                   # runtime logs
vercel redeploy <url>               # redeploy / roll back to a known-good build
```

## Railway

```bash
railway whoami                      # preflight
railway status                      # linked project / environment / service
railway up                          # build + deploy local source
railway up --detach                 # non-blocking; tail logs separately
railway logs                        # recent build + runtime logs
railway logs --tail                 # stream
railway open                        # dashboard
```

Switching environments (`railway environment <name>`) is the user's call.

## Render

```bash
render whoami                       # preflight
render services list [--json]       # find service id / URL / status
render deploy create <service-id> --wait   # deploy, wait for LIVE / FAILED
render logs [--tail]                # logs
```

Config lives in `render.yaml` (Blueprint); rollback via redeploying a previous
commit or the dashboard's rollback.

## DigitalOcean App Platform

```bash
doctl account get                   # preflight
doctl apps list --format ID,Spec.Name,ActiveDeployment.Phase
doctl apps create --spec .do/app.yaml          # first deploy
doctl apps update <app-id> --spec .do/app.yaml # apply spec changes
doctl apps create-deployment <app-id>          # redeploy current spec
doctl apps get <app-id>             # status + live URL
doctl apps logs <app-id> [--tail]   # logs
```

`.do/app.yaml` is the source of truth; keep it committed.

## Azure

```bash
az account show --query "{id:id, name:name}" -o table   # preflight
az webapp up --name <app> --resource-group <rg> --runtime "PYTHON:3.11"
az webapp deploy --name <app> --resource-group <rg> --src-path <path>
az webapp log tail --name <app> --resource-group <rg>
az webapp restart --name <app> --resource-group <rg>
az containerapp up --name <app> --resource-group <rg> --source .
az containerapp update --name <app> --image <registry>/<image>:<tag>
az containerapp logs show --name <app> --resource-group <rg> --follow
az functionapp deployment source config-zip --name <app> --resource-group <rg> --src <zip>
az functionapp logstream <app> --resource-group <rg>
```

Prefer `-o tsv` in shell pipelines, `-o table` for humans. Never change the
active subscription without asking.
