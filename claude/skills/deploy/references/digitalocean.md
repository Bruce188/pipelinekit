# DigitalOcean App Platform

`.do/app.yaml` is the source of truth, so keep it committed. Use `-o json` for output you will parse.

## Auth check
```bash
doctl account get
doctl apps list -o json               # app IDs
```

## Deploy
```bash
doctl apps create --spec .do/app.yaml --wait                 # first deploy
doctl apps update <app-id> --spec .do/app.yaml --update-sources --wait   # spec change and new source
doctl apps create-deployment <app-id> --wait [--force-rebuild]           # redeploy the current spec
doctl apps get <app-id>               # live URL and active deployment
doctl apps list-deployments <app-id>
```
Without `--update-sources`, `apps update` does not pull new source or a new image. To get a preview, run a second app (for example `<name>-staging`) from its own spec. There is no preview flag.

## Env vars
Declare them in the spec, then apply with `apps update --spec`:
```yaml
envs:
  - key: LIGHTER_API_KEY_PRIVATE
    type: SECRET       # encrypted after the first apply; the spec then holds the EV[...] ciphertext
    scope: RUN_TIME
```
Don't commit a spec with a plaintext secret value. Have the user enter it in the control panel, or apply it once from an uncommitted copy.

## Health check and pre-deploy
- Services use `health_check.http_path: /health`. Workers use `liveness_health_check.http_path` instead.
- For migrations, add a job with `kind: PRE_DEPLOY`.

**Trading bots.** The docs don't describe how a deploy cuts over from old to new instances, so assume they overlap. Keep `instance_count: 1` and use a leader lock.

## Logs
```bash
doctl apps logs <app-id> <component> --type run --follow
doctl apps logs <app-id> <component> --type build      # build failures
doctl apps logs <app-id> <component> --type deploy --tail 200
```
`--tail N` sets a line count, and `--follow` streams.

## Rollback
`doctl` has no rollback command. Use the control panel (Activity, then the deployment, then Rollback) or the API (`POST /v2/apps/{id}/rollback` with `{"deployment_id": "..."}`). Only the last 10 successful deployments qualify, and a rollback pins the app until you commit or revert it. Ask the user to do this.
