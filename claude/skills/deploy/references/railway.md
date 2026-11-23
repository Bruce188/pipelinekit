# Railway

Non-interactive: add `-y` where a command asks for confirmation, and `--json` for output you will parse. Scope commands with `-s <service> -e <environment>`. Only switch environments (`railway environment`) when the user says so.

**Config format change:** Railway's docs say `railway.json`/`railway.toml` (Config as Code) stop being read on 2026-12-01, replaced by `.railway/railway.ts` (`railway config init|pull|plan|apply|migrate`). If the repo still uses the old files, tell the user, and confirm the key names with `railway config --help` before you migrate.

## Auth check
```bash
railway whoami
railway status                        # linked project, environment and service
```

## Deploy
```bash
railway up -s <svc> -e staging --detach   # preview/staging; --ci streams the build and exits
railway up -s <svc> -e production --detach   # only on explicit intent
railway redeploy -s <svc> -y          # rebuild the latest deployment
railway restart -s <svc> -y           # restart without rebuilding
railway deployment list --json        # deployment IDs
```
Each Railway environment (staging, production) is the equivalent of preview vs prod.

## Env vars
```bash
railway variable list -s <svc> -e <env> --kv
printf %s "$VALUE" | railway variable set NAME --stdin -s <svc> -e <env>   # one key; the value stays out of argv
railway variable set A=1 B=2 --skip-deploys   # non-secret values only
railway variable delete NAME
```
`variable` also answers to `variables`, `vars` and `var`. The old `railway variables --set` still works but is deprecated.

## Health check and pre-deploy
Set these in the config: `deploy.healthcheckPath` (for example `/health`), `deploy.healthcheckTimeout`, and `deploy.preDeployCommand` (an array, for example `["python manage.py migrate"]`).

**Trading bots.** By default the new deployment comes up before the old one stops. `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS` (default 0) keeps the old deployment running even longer after the new one goes live, so leave it at 0 for bots. Give the bot time to stop cleanly with `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` (the gap between SIGTERM and SIGKILL, default 0). Even at overlap 0 there is a brief window, so the bot still needs a leader lock.

## Logs
`railway logs` streams by default. `-n`, `--since` or `--until` switch it to a one-off historical query.
```bash
railway logs -s <svc>                       # stream runtime logs
railway logs --build                        # logs for a failed build
railway logs -n 200 --filter '@level:error' # historical
railway logs <DEPLOYMENT_ID> --since 30m
```
`--deployment` (`-d`) selects the deploy-logs type. It does not filter by deployment ID.

## Rollback
The CLI has no rollback command. In the dashboard, go to the service, open Deployments, then open the good deployment's menu and choose Rollback. Get the ID first with `railway deployment list`, then ask the user to do it.
