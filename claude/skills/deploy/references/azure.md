# Azure

Non-interactive: `--only-show-errors -o json` for parsing, `-o table` for people. Never change the active subscription (`az account set`) without being asked. The Container Apps commands need the `containerapp` extension (`az extension add -n containerapp`).

## Contents
- Container Apps (FundingRateArb)
- App Service

## Container Apps (FundingRateArb)

FundingRateArb's `.github/workflows/deploy.yml` deploys `ca-fundingratearb` in `rg-fundingratearb` on every push to `main`:
1. Builds the image and pushes it to ACR, tagged with the commit SHA.
2. Runs `dotnet ef database update` behind a temporary SQL firewall rule.
3. Runs `az containerapp update --image`.
4. Polls `/healthz`.

The normal way to deploy is to merge to `main` or run the workflow with `workflow_dispatch` (`gh workflow run deploy.yml`). Only update the image by hand to roll back.

### Auth check
```bash
az account show --query "{name:name, id:id}" -o table
az containerapp show -n <app> -g <rg> --query "{fqdn:properties.configuration.ingress.fqdn, mode:properties.configuration.activeRevisionsMode, image:properties.template.containers[0].image}" -o json
```

### Deploy
```bash
az containerapp update -n <app> -g <rg> --image <acr>.azurecr.io/<repo>:<sha>   # creates a new revision
az containerapp revision list -n <app> -g <rg> -o table
```
To get a preview, use multiple-revision mode with a label (`--target-label`), or a separate staging app. Production is the revision that receives traffic.

### Secrets and env vars
```bash
az containerapp secret set -n <app> -g <rg> \
  --secrets aster-key=keyvaultref:https://<kv>.vault.azure.net/secrets/Exchanges--Aster--ApiKey,identityref:system
az containerapp update -n <app> -g <rg> --set-env-vars Exchanges__Aster__ApiKey=secretref:aster-key
```
Prefer `keyvaultref:` so that no value ever passes through argv. FundingRateArb reads Key Vault directly through `KeyVaultName`, so new exchange keys belong in Key Vault (`az keyvault secret set --vault-name <kv> --name Exchanges--X--ApiKey --file <path>`). Let the user run that command.

### Health
Configure liveness and readiness probes on `/healthz` (FundingRateArb maps both `/healthz` and `/health`). The deploy workflow polls `/healthz` with backoff.

### Logs
```bash
az containerapp logs show -n <app> -g <rg> --follow
az containerapp logs show -n <app> -g <rg> --tail 100 --type system   # startup and probe failures
az containerapp logs show -n <app> -g <rg> --revision <rev> --tail 100
```

### Rollback
Single-revision mode (the default):
```bash
az containerapp update -n <app> -g <rg> --image <acr>.azurecr.io/<repo>:<previous-good-sha>
```
Multiple-revision mode:
```bash
az containerapp revision activate -n <app> -g <rg> --revision <good-rev>
az containerapp ingress traffic set -n <app> -g <rg> --revision-weight <good-rev>=100
az containerapp revision deactivate -n <app> -g <rg> --revision <bad-rev>
```
A rollback does not undo a migration. If the bad release changed the schema, ask before you go any further.

### Trading bot: overlap
Single-revision mode keeps the old revision serving until the new one passes its probes, so **two bot processes run at once** during every deploy and every rollback. To prevent that:
- Pin the replica count: `az containerapp update -n <app> -g <rg> --min-replicas 1 --max-replicas 1`. This stops scale-out but does not prevent the overlap between revisions.
- Add a leader lock that every hosted service which places orders must hold (for example SQL `sp_getapplock` with a session-owned lock held for the life of the process). The new revision waits until the old one releases the lock at shutdown.
- Give shutdown room with `--termination-grace-period` so `StopAsync` can finish.

## App Service

### Auth check and deploy
```bash
az account show -o table
az webapp list-runtimes --os linux          # choose a runtime; don't hardcode an old one
az webapp deploy -n <app> -g <rg> --src-path app.zip --type zip --track-status
az webapp deploy -n <app> -g <rg> --slot staging --src-path app.zip --type zip   # preview slot
az webapp deployment slot swap -n <app> -g <rg> --slot staging --target-slot production   # explicit intent only
```

### Env vars
`az webapp config appsettings set -n <app> -g <rg> --settings @settings.json`. The `@file` form (a JSON file) keeps values out of argv. Delete the file afterwards and never commit it. Use `--slot-settings` for values that must stay with their slot. For secrets, prefer a Key Vault reference: `@Microsoft.KeyVault(SecretUri=...)`.

### Health
`az webapp config set -n <app> -g <rg> --generic-configurations '{"healthCheckPath": "/health"}'`

### Logs
`az webapp log tail -n <app> -g <rg>`. For Functions, use `func azure functionapp logstream <app>` from Azure Functions Core Tools. `az functionapp logstream` does not exist.

### Rollback
Swap again: `az webapp deployment slot swap ... --slot staging --target-slot production`. Without slots, redeploy the last good package.

### Trading bot: overlap
A slot swap warms up the new instance before the old one stops, so the two overlap. Run bots with one instance and without slot swaps, or use a leader lock.
