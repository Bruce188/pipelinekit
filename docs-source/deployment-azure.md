<!--
diataxis: how-to
-->
# Azure Deployment Provider

> [INFO] Not sure which provider fits? Try the [provider chooser](deployment-chooser.html).

Azure deployment via App Service, Container Apps, Function Apps. Auth (Managed Identity), Key Vault, Bicep/ARM, environment config, runtime verification, and provider comparison.

<div data-snippet="comparison-tabs"></div>

Azure deployment via App Service, Container Apps, Function Apps. Auth (Managed Identity), Key Vault, Bicep/ARM, environment config, runtime verification, and provider comparison.

pipelinekit integrates Azure as a first-class deployment provider on the same footing as Vercel, Railway, Render, and DigitalOcean. When your project charter selects `azure` as the deployment target (Charter Topic 10), pipelinekit routes deployment work to the `@azure-deployment-engineer` agent and the `azure-ops` skill automatically.

## 1. What is the Azure provider integration

Azure is Microsoft's cloud platform offering infrastructure-as-a-service (IaaS), platform-as-a-service (PaaS), and serverless compute. pipelinekit supports three Azure hosting models:

- **App Service** — Managed web hosting for Node.js, Python, .NET, Java, PHP, and Ruby. Zero container knowledge required; Azure handles runtime patching, scaling, and SSL.
- **Container Apps** — Managed container runtime with automatic scaling, networking, and secrets management. Bridges the gap between App Service (simplicity) and Kubernetes (flexibility).
- **Function Apps** — Serverless compute for event-driven workloads (HTTP triggers, timers, queues, blob storage). Pay only for execution time; no servers to manage.

The pipelinekit Azure integration consists of three components:

- **`claude/skills/azure-ops/SKILL.md`** — the operational skill that wraps the Azure CLI (`az`) for day-to-day ops: resource listing, app service restart, deployment history, log streaming, and health checks. Enforces the auth-posture contract (never auto-authenticates, always starts with `az account show`).
- **`claude/agents/azure-deployment-engineer.md`** — the deployment-engineer agent that covers Azure subscription topology, resource group strategy, app service / container apps / function app configuration, managed identity setup, Key Vault integration, observability wiring, and the full provider-native verification chain.
- **Charter Topic 10 integration** — selecting `azure` as the deployment provider in the project charter automatically routes `/pipeline` deployment phases to the agent and skill above.

## 2. Account & subscription setup

1.  Create an Azure account at [azure.microsoft.com](https://azure.microsoft.com). New accounts receive \$200 in free credits for 30 days; always-free tier includes App Service (B1 tier, 1 GB RAM), Azure SQL Database (20 GB), Azure Cosmos DB, and Function Apps (1M invocations/month).

2.  Create a subscription (or use the default subscription created with your account). All Azure resources belong to exactly one subscription; resource groups organize resources within a subscription.

3.  Create a resource group in your subscription using the Azure Portal or CLI:

        az group create --name myapp-rg --location eastus

    Resource group names must be unique within your subscription. Choose a location close to your users.

## 3. Install the Azure CLI

The Azure CLI (`az`) is the primary interface for pipelinekit's Azure ops. `pipelinekit/scripts/install.sh` auto-installs `az` on Debian / Ubuntu hosts. On other platforms (macOS, Fedora, etc.), follow Microsoft's installation guide: [Install the Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).

After install, verify the CLI is on your PATH:

    az version

## 4. Authenticate to Azure

Before running any deployment via pipelinekit, authenticate to Azure outside of Claude:

    az login

This opens a browser for interactive login. After authentication, the CLI stores your credentials in `~/.azure/` (never in shell history, env vars, or transcript).

Verify authentication with:

    az account show

If multiple subscriptions are available, set the default:

    az account set --subscription "My Subscription Name"

The `@azure-deployment-engineer` agent runs `az account show` as a preflight check before any deployment operation. If authentication is not set up, the agent STOPS and instructs you to authenticate outside Claude.

## 5. Create an App Service / Container App / Function App

### App Service (Web App)

For a Node.js web application:

    az appservice plan create --name myapp-plan --resource-group myapp-rg --sku B1 --is-linux
    az webapp create --resource-group myapp-rg --plan myapp-plan --name myapp-web --runtime "Node|20-lts"

Replace `myapp-web` with a globally unique name. The app will be accessible at `https://myapp-web.azurewebsites.net`.

### Container Apps

For a containerized application:

    az containerapp create --name myapp-container --resource-group myapp-rg \
      --image myregistry.azurecr.io/myapp:latest --target-port 3000 --ingress external

### Function App

For a serverless function:

    az functionapp create --resource-group myapp-rg --consumption-plan-location eastus \
      --runtime node --runtime-version 20 --functions-version 4 --name myapp-func

## 6. Integrate with pipelinekit Charter

When creating a new project via `/pipeline`, Step 0 (Charter Discovery) asks about deployment target (Topic 10). Select `azure` to route deployment tasks to the `@azure-deployment-engineer` agent.

For existing projects, ensure your charter includes:

    **Deployment Target:** azure

## 7. Runtime verification

After deployment, pipelinekit verifies the application with a three-step chain:

1.  **Deployment state probe:** Check app service status via Azure CLI

        az webapp show --resource-group myapp-rg --name myapp-web --query "state"

2.  **Log tail (60 seconds):** Stream application logs to catch cold-start failures

        az webapp log tail --resource-group myapp-rg --name myapp-web

3.  **Health-endpoint polling:** Hit your application's health endpoint with exponential backoff

        for i in 1 2 4 8 16 32; do
          curl --fail --silent "https://myapp-web.azurewebsites.net/health" && break
          echo "Health check failed — retrying in ${i}s"
          sleep "$i"
        done

## 8. Secret management

Never commit secrets (API keys, database passwords, tokens) to source code. Azure offers two solutions:

- **Application Settings (easier):** Store secrets as encrypted environment variables in App Service. Access via `process.env.MY_SECRET` (Node.js) or `os.environ['MY_SECRET']` (Python).

      az webapp config appsettings set --resource-group myapp-rg --name myapp-web \
        --settings API_KEY="secret-value" DATABASE_URL="postgres://..."

- **Azure Key Vault (recommended for enterprise):** Centralized secret storage with audit logging. Create a vault:

      az keyvault create --resource-group myapp-rg --name myapp-kv

  Store a secret:

      az keyvault secret set --vault-name myapp-kv --name database-password --value "secret-value"

  Grant your app access via managed identity (Agent will guide).

## 9. Common deployment tasks

### Redeploy from Git

If your app is connected to a GitHub repository, trigger a redeploy:

    az webapp deployment source sync --resource-group myapp-rg --name myapp-web

### View deployment history

    az webapp deployment list --resource-group myapp-rg --name myapp-web

### Roll back to a previous deployment

    az webapp deployment slot swap --resource-group myapp-rg --name myapp-web --slot staging

### Monitor application performance

Enable Application Insights (Azure's built-in observability service):

    az monitor app-insights component create --app myapp-insights --location eastus --resource-group myapp-rg

## 10. Auth posture & secret hygiene

The `@azure-deployment-engineer` agent enforces:

- **Authentication is your responsibility.** You run `az login` outside Claude. The agent verifies authentication with `az account show` and STOPS if not authenticated.
- **No credential env vars.** The agent never reads `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, or any `AZURE_*` credential. All credentials live in `~/.azure/` (on-disk encrypted).
- **No token logging.** Secrets never appear in logs, comments, or debug output. If a token leaks, rotate it immediately via the Azure Portal or CLI.
- **Application secrets in Key Vault.** Production API keys, database passwords, and third-party tokens belong in Azure Key Vault or Application Settings, never in source code or env vars.

## 11. Comparison with other providers

| Dimension                 | Azure                                           | Vercel                                           | Railway                               | Render                                       | DigitalOcean                                |
|---------------------------|-------------------------------------------------|--------------------------------------------------|---------------------------------------|----------------------------------------------|---------------------------------------------|
| **Primary Use Case**      | Enterprise; multi-service; managed containers   | Frontend; edge functions; serverless             | Any runtime; persistent volumes; cron | Any runtime; simple PaaS; persistent storage | Any runtime; simple PaaS; managed databases |
| **Hosting Models**        | App Service, Container Apps, Function Apps, VMs | Static hosting, Serverless Functions             | PaaS (auto-scaling)                   | PaaS (auto-scaling)                          | App Platform (managed containers)           |
| **Dockerfile Required**   | No (App Service) / Yes (Container Apps)         | No                                               | No                                    | No                                           | No                                          |
| **Free Tier**             | \$200 credit × 30 days + always-free tier       | Pro: 100 GB bandwidth; Functions: 1M invocations | \$5/month credit (trial)              | Free tier exists (limited)                   | \$5/month credit                            |
| **Min Cost (Production)** | ~\$15/month (B1 App Service)                    | ~\$20/month (Pro)                                | ~\$7/month                            | ~\$7/month                                   | ~\$12/month (basic droplet)                 |
| **CLI Tool**              | az (Microsoft)                                  | vercel (Vercel)                                  | railway (Railway)                     | render (Render)                              | doctl (DigitalOcean)                        |
| **IaC Support**           | Bicep, ARM, Terraform                           | vercel.json                                      | railway.toml                          | render.yaml                                  | .do/app.yaml                                |
| **Scaling**               | Auto (Premium SKUs)                             | Auto (edge network)                              | Auto (PaaS)                           | Auto (PaaS)                                  | Manual or via App Platform                  |

## 12. Troubleshooting

### Deployment fails with "Resource group not found"

Verify the resource group exists:

    az group list --output table

Create it if missing:

    az group create --name myapp-rg --location eastus

### Application crashes after deployment

Check application logs:

    az webapp log tail --resource-group myapp-rg --name myapp-web

Common causes:

- Missing environment variables (set via Application Settings)
- Database connection string incorrect
- Port mismatch (Azure expects app to listen on port from `WEBSITES_PORT` env var, default 8080)

### Health check times out

If your app is starting slowly, increase the health-check timeout:

    for i in 1 2 4 8 16 32 60; do
      curl --fail --silent --max-time 10 "https://myapp-web.azurewebsites.net/health" && break
      echo "Retrying in ${i}s..."
      sleep "$i"
    done

### "Not authenticated to Azure"

Run `az login` outside Claude, then verify with `az account show`.

## 13. Additional resources

- [Microsoft Learn — Azure Docs](https://learn.microsoft.com/en-us/azure/)
- [Azure CLI Documentation](https://learn.microsoft.com/en-us/cli/azure/)
- [App Service Documentation](https://learn.microsoft.com/en-us/azure/app-service/)
- [Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Azure Functions Documentation](https://learn.microsoft.com/en-us/azure/azure-functions/)
- [Azure Key Vault Documentation](https://learn.microsoft.com/en-us/azure/key-vault/)

## 14. Pipelinekit command cheatsheet

Filter the table below by `azure`, `ppr`, or `review` to surface the deploy-relevant slash commands.

<div data-snippet="command-cheatsheet"></div>

