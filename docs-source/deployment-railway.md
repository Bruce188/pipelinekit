# Railway Deployment Provider

> [INFO] Not sure which provider fits? Try the [provider chooser](deployment-chooser.html).

Railway account setup, project linking, CLI install posture, pipelinekit integration via Charter Topic 10, Nixpacks build, environment configuration, and provider comparison.

<div data-snippet="comparison-tabs"></div>

Railway account setup, project linking, CLI install posture, pipelinekit integration via Charter Topic 10, Nixpacks build, environment configuration, and provider comparison.

pipelinekit integrates Railway as a first-class deployment provider on the same footing as Vercel and Azure. When your project charter selects `railway` as the deployment target (Charter Topic 10), pipelinekit routes deployment work to the `@railway-deployment-engineer` agent and the `railway-ops` skill automatically.

## 1. What is the Railway provider integration

Railway is a cloud platform that provisions infrastructure from source code with zero Dockerfile required for most runtimes (Node.js, Python, Go, Ruby). Railway supports persistent volumes, cron jobs, private networking, and multi-service projects within a single project boundary.

The pipelinekit Railway integration consists of three components:

- **`claude/skills/railway-ops/SKILL.md`** — the operational skill that wraps the Railway CLI (`railway`) for day-to-day ops: deploy, status check, log tail, health-endpoint polling, and redeploy. Enforces the auth-posture contract (never auto-authenticates, always starts with `railway whoami`).
- **`claude/agents/railway-deployment-engineer.md`** — the deployment-engineer agent that covers Railway project/environment/service topology, `railway.toml` configuration authoring, observability wiring, cost guardrails, and the full provider-native verification chain.
- **Charter Topic 10 integration** — selecting `railway` as the deployment provider in the project charter automatically routes `/pipeline` deployment phases to the agent and skill above.

## 2. Account & project setup

1.  Create a Railway account at [railway.com](https://railway.com). You can sign up with GitHub for zero-friction Git integration.

2.  Create a new project via the Railway dashboard. A project is a top-level grouping of services. One project per deployable application is recommended for clean environment and secret isolation.

3.  Link your local repository to the Railway project using the CLI:

        railway link

    `railway link` is an interactive command — run it outside Claude in your terminal. It writes local project-link state to `.railway/`. Add `.railway/` to your `.gitignore` — it is per-developer state, not source-controlled configuration.

4.  Authenticate the CLI before linking or deploying:

        railway login

    Run `railway login` outside Claude in an interactive shell. pipelinekit's `railway-ops` skill never runs `railway login` for you — authentication is your responsibility.

5.  Verify the link succeeded and confirm the active project, environment, and service:

        railway status

## 3. CLI install

The Railway CLI is not auto-installed by pipelinekit. Installation is user-driven — this mirrors Vercel's install posture. To install the Railway CLI, follow the instructions in the [Railway CLI documentation](https://docs.railway.com/guides/cli).

The most common install method across macOS, Linux, and WSL2 is via npm:

    npm i -g @railway/cli

Railway also publishes a platform-native install script and Homebrew tap — see the Railway CLI docs for the canonical install path for your OS. pipelinekit does not automate this step.

After installing, run `railway login` in an interactive shell outside Claude to authenticate the CLI. Then verify the install and auth with:

    railway whoami

A successful `railway whoami` is the prerequisite for every `railway-ops` skill invocation.

## 4. Pipelinekit integration

To activate the Railway provider integration in pipelinekit, select `railway` as the deployment provider when answering Charter Topic 10 during `/pipeline` Step 0 (Charter Discovery).

**Charter Topic 10** asks: *"What is your deployment target?"* Answer `railway` (Option C). The charter records this answer and downstream pipeline phases use it to route deployment work automatically:

- The `/implement-plan` phase routes Railway-specific deployment tasks to the `@railway-deployment-engineer` agent.
- The agent invokes `claude/skills/railway-ops/SKILL.md` for all CLI operations, enforcing the auth-posture contract (preflight `railway whoami`, never auto-authenticates).

If you have an existing charter and want to switch to Railway, update Charter Topic 10 to `railway` and re-run the relevant pipeline phase.

## 5. Runtime verification commands

pipelinekit's Railway integration uses the following verification chain after every deploy. All three steps must pass before a deployment is declared production-ready.

### Step 1: Deployment state check

    railway status

Confirms the deployment reached **ACTIVE** state. If the state is FAILED or CRASHED, do not proceed — read `railway logs` for the failure reason.

### Step 2: Log tail (60 seconds post-deploy)

    railway logs --tail

Streams live logs from the active service for the first 60 seconds after deploy. Cold-start failures and config-only runtime errors surface within this window.

### Step 3: Health endpoint probe with exponential backoff (60s timeout)

    for i in 1 2 4 8 16 32; do
      curl --fail --silent "$RAILWAY_URL/health" && break
      echo "Health check failed — retrying in ${i}s (exponential backoff)..."
      sleep "$i"
    done

Probes `$RAILWAY_URL/health` with a 60s total timeout using exponential backoff (1 → 2 → 4 → 8 → 16 → 32 seconds between retries). Railway services can have cold-start delays; a single one-shot `curl` probe produces false negatives. The exponential backoff pattern handles cold-start gracefully.

Set `healthcheckPath = "/health"` in your `railway.toml` so Railway itself also polls the health endpoint before routing traffic to the new deployment.

## 6. Auth posture

pipelinekit's Railway integration enforces a strict auth posture: Claude never runs `railway login`, never reads `RAILWAY_TOKEN` from the environment, and never caches or echoes Railway credentials.

- **You are responsible for `railway login`.** Run it outside Claude in an interactive shell before invoking any Railway skill or agent. Claude refuses to run `railway login` for you.

- **pipelinekit does not read `RAILWAY_TOKEN`.** If you are wiring a CI pipeline (GitHub Actions, etc.), manage `RAILWAY_TOKEN` as a CI secret outside Claude. The `railway-ops` skill and `@railway-deployment-engineer` agent never read it.

- **Preflight on every operation.** Every `railway-ops` workflow begins with `railway whoami`. On non-zero exit, the skill stops and prompts:

      Railway auth missing. Run `railway login` outside Claude, then re-invoke this skill.

This posture eliminates a class of credential-leak risk that has historically occurred when agentic contexts run non-interactive auth flows (shell history leaks, log captures, transcript exports).

## 7. When to use Railway vs. other providers

Railway, Vercel, and Azure serve overlapping but distinct workload profiles. Use this comparison to guide Charter Topic 10 selection.

| Dimension        | Railway                                                          | Vercel                                                          | Azure                                                                       |
|------------------|------------------------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------|
| Best for         | Full-stack apps, APIs, workers, databases in one project         | Frontend-heavy apps (Next.js, SvelteKit, Astro, Remix)          | Enterprise .NET / Java workloads, regulated industries                      |
| Runtime model    | Always-on services (Pro); sleep on inactivity (Hobby)            | Serverless / Edge Functions; no persistent processes            | App Service (persistent), Container Apps (serverless containers), Functions |
| Database support | First-class: Postgres, MySQL, Redis, MongoDB as Railway services | No native database — use external (PlanetScale, Supabase, Neon) | Azure SQL, Cosmos DB, Cache for Redis — managed PaaS                        |
| Config format    | `railway.toml`                                                   | `vercel.json`                                                   | Bicep / ARM templates, App Service config                                   |
| CLI auth posture | User-driven `railway login`                                      | User-driven `vercel login`                                      | User-driven `az login`                                                      |
| Cold start       | Yes (Hobby plan sleep); No (Pro plan)                            | Yes (Serverless Functions); Near-zero (Edge Functions)          | Varies by service tier and scaling config                                   |
| Compliance       | SOC 2 / HIPAA on Enterprise plan                                 | SOC 2 / HIPAA on Enterprise plan                                | Broad: ISO 27001, SOC 1/2/3, HIPAA, FedRAMP, GDPR                           |

**Choose Railway when** your workload needs persistent processes (long-running workers, WebSocket servers), first-class managed databases co-located with the app, or a simple all-in-one project boundary for a full-stack application.

**Choose Vercel when** your workload is a frontend framework (Next.js / SvelteKit / Astro / Remix) and you want zero-config per-commit preview deployments with tight Git integration.

**Choose Azure when** your workload is enterprise .NET or Java, requires Azure-native services (Azure SQL, Cosmos DB, Service Bus), or has compliance requirements (FedRAMP, regulated healthcare) that need Azure's compliance portfolio.

## Pipelinekit command cheatsheet

Filter the slash-command table below by `railway`, `ppr`, or `review` to surface the deploy-relevant subset.

<div data-snippet="command-cheatsheet"></div>

