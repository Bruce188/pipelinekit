---
name: azure-ops
description: Azure CLI (`az`) wrapper for common ops — resource listing, deploy (App Service / Container Apps / Function Apps), log tail, app-service restart. STOPS and prompts the user if `az account show` fails — never auto-authenticates. Use when running day-to-day Azure operations against an already-authenticated context.
---

# Azure Operations Skill

This skill wraps the Azure CLI (`az`) for common day-to-day operations: listing resources, deploying applications, tailing logs, and restarting services. It focuses on the *operational* layer — for canonical `az` command reference, use https://learn.microsoft.com/cli/azure or the `context7` MCP.

The skill is deliberately narrow: it does NOT handle first-time Azure setup, service-principal authentication, token caching, or non-interactive CI workflows. It assumes the user has already run `az login` themselves in an interactive shell and that the current Azure CLI context is healthy.

## Keywords

Azure CLI, az, Azure resources, App Service, Container Apps, Function Apps, Log Analytics, KQL, Azure Resource Manager, ARM, resource group, az login, az account, az webapp, az containerapp, az functionapp, az monitor, Azure deployment, Azure auth posture

## Capabilities

### Authentication posture (FIRST — runs before every operation)

The skill begins every workflow with the following preflight probe:

```bash
az account show --query "user.name" -o tsv
```

On non-zero exit (or empty output), STOP immediately and print a prompt instructing the user to run `az login` themselves. Do not retry. Do not attempt alternative auth flows.

**Non-negotiable constraints:**
- The skill MUST NOT attempt any non-interactive service-principal `az login` variants.
- The skill MUST NOT read or echo credential env vars. Do not echo client secrets, tenant secrets, or any credential material.
- The skill MUST NOT cache access tokens locally or in the environment.
- Authentication is the user's responsibility. The skill operates against an already-authenticated context only.

**Why this matters:** Non-interactive credential flows in agentic contexts have repeatedly leaked credentials through shell history, log files, and inadvertent transcript captures. The auth posture above eliminates that class of risk entirely — the skill simply refuses to operate without a healthy interactive `az login` context.

### Resource listing

List Azure resources scoped to a resource group or subscription, with JMESPath query projections to limit output.

Common patterns:

- `az resource list --resource-group <rg>` — list every resource in a resource group
- `az resource list --query "[?type=='Microsoft.Web/sites']"` — filter to App Service sites only
- `az group list` — list all resource groups in the current subscription
- `az resource list --query "[?location=='eastus'].{name:name, type:type}" --output table` — projection with filter

**Output formatting:**
- `--output table` is the human-readable default — use for ad-hoc inspection.
- `--output json` is for piping to other tools (`jq` not installed in pipelinekit; use `python3 -c` for downstream parsing).
- `--output tsv` is the safest for shell pipelines (one value per line, no quoting issues).

**Always use `--query` projections.** Never dump full resource JSON to the terminal — Azure resource objects can contain credentials, connection strings, and PII in custom tags. Project the specific fields you need.

### Deploy

The skill supports four primary deployment surfaces.

**App Service (`az webapp`):**
- `az webapp up --name <app> --resource-group <rg> --runtime "PYTHON:3.11"` — zero-config deploy from current directory (Oryx build provider)
- `az webapp deploy --name <app> --resource-group <rg> --src-path <path>` — modern deploy command with explicit src-path
- Slot deployments: `az webapp deployment slot create --name <app> --slot staging`, then `az webapp deployment slot swap --slot staging --target-slot production`

**Container Apps (`az containerapp`):**
- `az containerapp up --name <app> --resource-group <rg> --source .` — Buildpacks-based build + deploy
- `az containerapp update --name <app> --image <registry>/<image>:<tag>` — update existing app to a new image
- Revision-based rollouts: `az containerapp revision list --name <app> --resource-group <rg>`

**Function Apps (`az functionapp`):**
- `az functionapp deployment source config-zip --name <app> --resource-group <rg> --src <zip>` — zip deploy
- `az functionapp config appsettings set --name <app> --resource-group <rg> --settings KEY=value` — env config

**Build provider gotchas:**
- App Service Linux uses Oryx — auto-detects Python, Node, .NET, Java, PHP, Ruby. Honor `Oryx-AppService` build flags via app settings.
- Container Apps uses Buildpacks (Paketo) by default. Override with a Dockerfile in the repo root.
- Function Apps on Premium/Dedicated plans use the same App Service runtime; Consumption-plan Function Apps have stricter cold-start constraints.

### Log tail

Streaming and historical log access patterns.

**Streaming (tail / follow):**
- `az webapp log tail --name <app> --resource-group <rg>` — App Service streaming logs (stdout + stderr from the application)
- `az containerapp logs show --name <app> --resource-group <rg> --follow` — Container Apps streaming logs (per-revision)
- `az functionapp logstream <app> --resource-group <rg>` — Function App streaming logs

**Historical (KQL queries against Log Analytics):**
- `az monitor log-analytics query --workspace <workspace-id> --analytics-query "AppServiceHTTPLogs | where TimeGenerated > ago(1h) | take 100"`
- KQL supports rich aggregation, joins, and time-window analysis — use for SLO investigations, error-rate trending, and incident retros.

**Distinguish streaming from historical:**
- Streaming is for live debugging — what is the app doing right now?
- Historical is for investigation — what happened during the incident two hours ago?
- Streaming logs are not persisted by Azure for App Service (only the last few hundred lines). Configure diagnostic settings to ship logs to a Log Analytics workspace if you need durable retention.

### App-service restart

Restart workflows for the three primary compute services.

- `az webapp restart --name <app> --resource-group <rg>` — App Service restart (single-instance; for slot-aware restart, add `--slot <slot>`)
- `az containerapp revision restart --revision <revision-name> --resource-group <rg>` — Container Apps revision restart (or update the active revision)
- `az functionapp restart --name <app> --resource-group <rg>` — Function App restart

**When to restart:**
- A new app setting was applied that requires a process restart (Function Apps auto-restart on setting change; App Service usually does, but custom containers may not).
- Memory pressure or a stuck worker thread — restart is the first-line remediation.
- After a deployment slot swap, the target slot is "warm" but a restart of the slot guarantees a clean state.

**When NOT to restart:**
- High-traffic production without a load-balanced fallback — restart is a brief outage on App Service single-instance plans. Use deployment slots + swap instead.
- During an active deploy — let the deploy finish before restarting.

## How to Use

Every workflow MUST include the `az account show` preflight as a visible step in the code block — not just narrative. The pattern below MUST be copied into each operational example.

**Resource listing:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
az account show --query "user.name" -o tsv || { echo "Not logged in. Run: az login"; exit 1; }
# 2. List resources in a group with a JMESPath projection
az resource list --resource-group myrg --query "[].{name:name, type:type, location:location}" --output table
```

**Deploy to App Service:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
az account show --query "user.name" -o tsv || { echo "Not logged in. Run: az login"; exit 1; }
# 2. Deploy current directory to App Service
az webapp up --name myapp --resource-group myrg --runtime "PYTHON:3.11"
```

**Log tail (App Service streaming):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
az account show --query "user.name" -o tsv || { echo "Not logged in. Run: az login"; exit 1; }
# 2. Stream logs from the app (Ctrl-C to stop)
az webapp log tail --name myapp --resource-group myrg
```

**App-service restart:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
az account show --query "user.name" -o tsv || { echo "Not logged in. Run: az login"; exit 1; }
# 2. Restart the app
az webapp restart --name myapp --resource-group myrg
```

**Subscription / account confirmation:**

```bash
# Show the current Azure CLI account context (identity only — never dump full JSON)
az account show --query "user.name" -o tsv
# Show the current subscription
az account show --query "{id:id, name:name}" --output table
```

## When to Use

Use this skill when you need to:

- List Azure resources in the current subscription or a specific resource group.
- Deploy an application to App Service, Container Apps, or Function Apps from a local repo.
- Tail logs from an App Service, Container App, or Function App for live debugging.
- Restart an App Service, Container App revision, or Function App.
- Check the current `az` account context (identity / subscription) before running an operation elsewhere.

## When NOT to Use

Do not use this skill for first-time Azure setup — that requires interactive `az login`, which the skill does not perform. Do not use this skill in non-interactive CI environments without a pre-authenticated `AZURE_*` token bundle managed by the CI platform (the skill does not read service-principal credentials).

Do not use this skill for:

- Bootstrapping a new tenant or subscription — that requires interactive `az login` and is the user's responsibility.
- Long-running unattended automation — the skill is built for interactive ops, not for `cron`-style schedulers (use Azure-native automation: Functions, Logic Apps, Azure Pipelines).
- Bulk resource lifecycle (create dozens of resources from scratch) — use Bicep or ARM IaC via the `@azure-deployment-engineer` agent instead.
- AKS day-2 operations beyond `az aks get-credentials` — full AKS workflows belong with `kubectl` and the `@azure-deployment-engineer` agent.
- Azure Government / Azure China cloud endpoints — v1 supports the public commercial cloud only.

## Limitations

- No service-principal auth flow. The skill operates against an already-authenticated interactive context only.
- No token refresh handling. If your `az login` session expires mid-workflow, the next command will fail; STOP and prompt the user to re-authenticate.
- No automatic `az` upgrade. The skill checks `az version` and warns when the installed CLI is older than 30 days, but does not auto-upgrade — the user owns the install lifecycle.
- No support for Azure Government, Azure China, or Azure Stack endpoints in v1 (public commercial cloud only).
- No bulk-create / bulk-delete operations. For multi-resource lifecycle, defer to IaC (Bicep / ARM) via the `@azure-deployment-engineer` agent.

## Best Practices

- Always use `--query` projections to limit output fields. Never dump full resource JSON — Azure resource objects can contain credentials, connection strings, and PII in custom tags.
- Prefer `--output table` for human review; `--output tsv` for shell pipelines; `--output json` only when piping to a parser.
- Set defaults for the current session via `az configure --defaults group=<rg> location=<region>` to avoid repeating `--resource-group` on every command.
- Never log full `az account show` JSON — it includes tenant IDs, subscription IDs, and the signed-in user's UPN. Project the specific field you need (`--query "user.name"`).
- Prefer Bicep over raw ARM JSON for any IaC the skill emits. Bicep templates are shorter, lint-checked by `az bicep build`, and round-trip cleanly to ARM.
- Use deployment slots (`az webapp deployment slot`) for zero-downtime App Service swaps. Restart targets a single slot — never restart production without a warm staging slot ready.
- Tag every resource at creation time with `Environment`, `Owner`, and `CostCenter`. Tags survive resource moves and are queryable via JMESPath.
- Prefer Container Apps over AKS for stateless HTTP workloads — Container Apps has less ops surface (no node pool management, no kubectl).
- Stream logs for live debugging; query Log Analytics for historical investigation. Don't try to use streaming logs as an audit trail — they aren't persisted.
- When restarting an App Service, prefer slot swap if available. Direct restart is a brief outage on single-instance plans.
- Run `az version` periodically. The skill warns when the installed CLI is older than 30 days; user upgrades on their own schedule.
- Never echo client secrets. The skill never reads `AZURE_*` credential env vars; the user manages secrets via Azure Key Vault, not via shell exports.

## Installation Requirements

- Set `CLAUDE_INSTALL_OPTIONALS=azure` (or any superset that includes `azure`) when running `scripts/install.sh` to opt into the Azure CLI install gate. The Azure CLI is NOT installed by default.
- The install gate runs the Microsoft-published one-liner `curl -sL https://aka.ms/InstallAzureCLIDeb | bash` on Debian/Ubuntu hosts. **Trust note:** Microsoft does not publish a sha256 for the install script; the install gate logs the URL before running so the user can verify the supply-chain dependency. The user can also install manually from https://learn.microsoft.com/cli/azure/install-azure-cli-linux.
- macOS: install via `brew install azure-cli`. The `install.sh` gate is Debian/Ubuntu-only in v1 — macOS users install the CLI themselves and re-run `install.sh` to verify.
- WSL2-Ubuntu and the pipelinekit devcontainer base image both work out of the box (the devcontainer pre-provisions `az` when the `azure` optional is enabled).
- **`az login` is the user's responsibility.** The install gate does not authenticate. After install, run `az login` in an interactive shell before invoking this skill.
- The skill verifies authentication state by running `az account show --query "user.name" -o tsv` at the start of every workflow. STOP and prompt the user if it returns non-zero.
