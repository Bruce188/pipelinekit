# Render

Non-interactive: `--confirm` skips prompts and `-o json` gives parseable output (both are global flags). In a script, `RENDER_API_KEY` takes precedence over `render login`.

## Auth check
```bash
render whoami -o json
render services -o json               # service IDs (srv-...), URLs and status
```

## Deploy
```bash
render deploys create <srv-id> --wait --confirm -o json
render deploys create <srv-id> --commit <sha> --wait --confirm   # deploy one specific commit
render deploys create <srv-id> --image <url> --wait --confirm    # image-backed service
render deploys list <srv-id> -o json
```
Render has no preview/prod flag. Production is a service, and preview environments come from the Blueprint (`previews:`), so pick the right `srv-id`.

## Env vars
The CLI only sets env vars when it creates a service. After that, use the dashboard (Environment), the REST API, or the Blueprint. In `render.yaml`, declare secrets with:
```yaml
envVars:
  - key: LIGHTER_API_KEY_PRIVATE
    sync: false        # the value is entered in the dashboard and never committed
```
Render only asks for `sync: false` values when the Blueprint is first created. They are left out of preview environments and can't live in env groups.

## Health check and pre-deploy
- `healthCheckPath: /health` applies to web services only.
- `preDeployCommand:` applies to paid web services, private services and workers. It runs on a separate instance with no disk and a 30-minute timeout, and if it fails the deploy fails.

**Trading bots.** Zero-downtime deploys overlap the old and new instances, and Render's docs list background workers as affected too. The old instance gets SIGTERM after the new one is up. Attaching a persistent disk turns zero-downtime off, so the old instance stops first. Otherwise, use a leader lock.

## Logs
`-r` is required when the CLI runs non-interactively.
```bash
render logs -r <srv-id> --limit 200 --level error -o text
render logs -r <srv-id> --tail        # stream
```

## Rollback
There is no CLI command for rollback. You can:
- Roll back from the dashboard (Events, then Rollback). This disables autodeploy.
- Call the API's "Roll back deploy" endpoint.
- Redeploy a known-good commit: `render deploys create <srv-id> --commit <good-sha> --wait --confirm`.
