<!--
diataxis: how-to
-->
# DigitalOcean App Platform Deployment Provider

> [INFO] Not sure which provider fits? Try the [provider chooser](deployment-chooser.html).

DigitalOcean App Platform setup, doctl CLI, .do/app.yaml App Spec, pipelinekit integration via Charter Topic 10, env config, runtime verification, and provider comparison.

<div data-snippet="comparison-tabs"></div>

DigitalOcean App Platform setup, doctl CLI, .do/app.yaml App Spec, pipelinekit integration via Charter Topic 10, env config, runtime verification, and provider comparison.

pipelinekit integrates DigitalOcean App Platform as a first-class deployment provider on the same footing as Vercel, Azure, Railway, and Render. When your project charter selects `digitalocean` as the deployment target (Charter Topic 10), pipelinekit routes deployment work to the `@digitalocean-deployment-engineer` agent and the `digitalocean-ops` skill automatically.

## 1. What is the DigitalOcean provider integration

DigitalOcean App Platform is a Platform-as-a-Service (PaaS) that provisions infrastructure from source code with zero Dockerfile required for most runtimes (Node.js, Python, Go, Ruby, PHP, static sites). App Platform supports managed PostgreSQL, MySQL, and Redis databases, workers, cron jobs, and multi-component apps defined via a `.do/app.yaml` App Spec at the repository root.

The pipelinekit DigitalOcean integration consists of three components:

- **`claude/skills/digitalocean-ops/SKILL.md`** — the operational skill that wraps the DigitalOcean CLI (`doctl`) for day-to-day ops: app listing, deploy, log tail, health-endpoint polling, and redeploy. Enforces the auth-posture contract (never auto-authenticates, always starts with `doctl account get`).
- **`claude/agents/digitalocean-deployment-engineer.md`** — the deployment-engineer agent that covers DigitalOcean App Platform topology (App / Component / Service / Region), `.do/app.yaml` App Spec configuration authoring, observability wiring, cost guardrails, and the full provider-native verification chain.
- **Charter Topic 10 integration** — selecting `digitalocean` as the deployment provider in the project charter automatically routes `/pipeline` deployment phases to the agent and skill above.

## 2. Account & app setup

1.  Create a DigitalOcean account at [digitalocean.com](https://www.digitalocean.com). You can sign up with GitHub for zero-friction Git integration.

2.  Create a new app via the DigitalOcean App Platform dashboard. An App contains one or more Components (Service, Worker, Job, Static Site). One Component per deployable application is recommended for clean environment and secret isolation.

3.  Optionally define your full app topology in a `.do/app.yaml` App Spec at the repository root:

        .do/app.yaml

    The App Spec declares components, databases, environment variables, instance sizes, regions, and health check paths in code. DigitalOcean picks it up automatically when the repository is connected to an App Platform app. Prefer `.do/app.yaml` over dashboard-only configuration so the deployment spec is version-controlled.

4.  Authenticate the CLI before deploying:

        doctl auth init

    Run `doctl auth init` outside Claude in an interactive shell. You will be prompted for your DigitalOcean personal access token. pipelinekit's `digitalocean-ops` skill never runs `doctl auth init` for you — authentication is your responsibility.

5.  Verify authentication and list your apps to confirm the target app exists:

        doctl account get
        doctl apps list

## 3. CLI install

The `doctl` CLI is not auto-installed by pipelinekit. Installation is user-driven — this mirrors Vercel's, Railway's, and Render's install posture. To install `doctl`, follow the instructions in the [DigitalOcean doctl install documentation](https://docs.digitalocean.com/reference/doctl/how-to/install/).

pipelinekit does not automate this step. Refer to the DigitalOcean CLI docs linked above for the canonical install path for your operating system (macOS, Linux, or Windows).

After installing, run `doctl auth init` in an interactive shell outside Claude to authenticate the CLI. Then verify the install and auth with:

    doctl account get

A successful `doctl account get` is the prerequisite for every `digitalocean-ops` skill invocation.

## 4. Pipelinekit integration

To activate the DigitalOcean provider integration in pipelinekit, select `digitalocean` as the deployment provider when answering Charter Topic 10 during `/pipeline` Step 0 (Charter Discovery).

**Charter Topic 10** asks: *"What is your deployment target?"* Answer `digitalocean` (Option E). The charter records this answer and downstream pipeline phases use it to route deployment work automatically:

- The `/implement-plan` phase routes DigitalOcean-specific deployment tasks to the `@digitalocean-deployment-engineer` agent.
- The agent invokes `claude/skills/digitalocean-ops/SKILL.md` for all CLI operations, enforcing the auth-posture contract (preflight `doctl account get`, never auto-authenticates).

If you have an existing charter and want to switch to DigitalOcean, update Charter Topic 10 to `digitalocean` and re-run the relevant pipeline phase.

## 5. Runtime verification commands

pipelinekit's DigitalOcean integration uses the following verification chain after every deploy. All three steps must pass before a deployment is declared production-ready.

### Step 1: App state check

    doctl apps get <app-id>

Confirms the app reached **ACTIVE** state. If the state is ERROR or stuck in DEPLOYING, do not proceed — read `doctl apps logs <app-id>` for the failure reason.

### Step 2: Log tail (60 seconds post-deploy)

    doctl apps logs <app-id> --tail

Streams live logs from the active app for the first 60 seconds after deploy. Cold-start failures and config-only runtime errors surface within this window.

### Step 3: Health endpoint probe with exponential backoff (60s timeout)

    for i in 1 2 4 8 16 32; do
      curl --fail --silent "$DO_URL/health" && break
      echo "Health check failed — retrying in ${i}s (exponential backoff)..."
      sleep "$i"
    done

Probes `$DO_URL/health` with a 60s total timeout using exponential backoff (1 → 2 → 4 → 8 → 16 → 32 seconds between retries). DigitalOcean App Platform services can have cold-start delays; a single one-shot `curl` probe produces false negatives. The exponential backoff pattern handles cold-start gracefully.

Set `health_check.http_path: /health` in your `.do/app.yaml` so DigitalOcean itself also polls the health endpoint before routing traffic to the new deployment.

## 6. Auth posture

pipelinekit's DigitalOcean integration enforces a strict auth posture: Claude never runs `doctl auth init`, never reads `DIGITALOCEAN_ACCESS_TOKEN` from the environment, and never caches or echoes DigitalOcean credentials.

- **You are responsible for `doctl auth init`.** Run it outside Claude in an interactive shell before invoking any DigitalOcean skill or agent. You will be prompted for your DigitalOcean personal access token. Claude refuses to run `doctl auth init` for you.

- **pipelinekit does not read `DIGITALOCEAN_ACCESS_TOKEN`.** If you are wiring a CI pipeline (GitHub Actions, etc.), manage `DIGITALOCEAN_ACCESS_TOKEN` as a CI secret outside Claude. The `digitalocean-ops` skill and `@digitalocean-deployment-engineer` agent never read it.

- **Preflight on every operation.** Every `digitalocean-ops` workflow begins with `doctl account get`. On non-zero exit, the skill stops and prompts:

      DigitalOcean auth missing. Run `doctl auth init` outside Claude, then re-invoke this skill.

This posture eliminates a class of credential-leak risk that has historically occurred when agentic contexts run non-interactive auth flows (shell history leaks, log captures, transcript exports).

## 7. When to use DigitalOcean vs. other providers

DigitalOcean App Platform, Render, Railway, Vercel, and Azure serve overlapping but distinct workload profiles. Use this comparison to guide Charter Topic 10 selection.

| Dimension        | DigitalOcean                                                                                                       | Render                                                                             | Railway                                                          | Vercel                                                          | Azure                                                                       |
|------------------|--------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|------------------------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------|
| Best for         | Full-stack apps, APIs, workers, databases; App Spec-driven multi-component projects on DigitalOcean infrastructure | Full-stack apps, APIs, workers, databases; Blueprint-driven multi-service projects | Full-stack apps, APIs, workers, databases in one project         | Frontend-heavy apps (Next.js, SvelteKit, Astro, Remix)          | Enterprise .NET / Java workloads, regulated industries                      |
| Runtime model    | Always-on services (Pro / Dedicated plans); potential cold start on smaller Basic tiers                            | Always-on services (paid plans); spin-down on inactivity (Free)                    | Always-on services (Pro); sleep on inactivity (Hobby)            | Serverless / Edge Functions; no persistent processes            | App Service (persistent), Container Apps (serverless containers), Functions |
| Database support | First-class: managed PostgreSQL, MySQL, Redis as App Platform databases, linked via .do/app.yaml                   | First-class: managed PostgreSQL as a Render service, linked via render.yaml        | First-class: Postgres, MySQL, Redis, MongoDB as Railway services | No native database — use external (PlanetScale, Supabase, Neon) | Azure SQL, Cosmos DB, Cache for Redis — managed PaaS                        |
| Config format    | `.do/app.yaml` (App Spec)                                                                                          | `render.yaml` (Blueprint)                                                          | `railway.toml`                                                   | `vercel.json`                                                   | Bicep / ARM templates, App Service config                                   |
| CLI auth posture | User-driven `doctl auth init`                                                                                      | User-driven `render login`                                                         | User-driven `railway login`                                      | User-driven `vercel login`                                      | User-driven `az login`                                                      |
| Cold start       | Minimal on Pro / Dedicated; possible on Basic tiers depending on instance size                                     | Yes (Free plan spin-down); No (paid plans with always-on)                          | Yes (Hobby plan sleep); No (Pro plan)                            | Yes (Serverless Functions); Near-zero (Edge Functions)          | Varies by service tier and scaling config                                   |
| Compliance       | SOC 2 Type II certified; HIPAA-eligible workloads on a Business Associate Agreement basis                          | SOC 2 / HIPAA on Enterprise plan                                                   | SOC 2 / HIPAA on Enterprise plan                                 | SOC 2 / HIPAA on Enterprise plan                                | Broad: ISO 27001, SOC 1/2/3, HIPAA, FedRAMP, GDPR                           |

**Choose DigitalOcean when** your workload needs persistent processes (long-running workers, WebSocket servers), managed PostgreSQL / MySQL / Redis co-located with the app, a declarative App Spec for multi-component projects, or you prefer DigitalOcean's platform ergonomics, pricing model, and regional infrastructure footprint (NYC, SFO, AMS, SGP, and more).

**Choose Render when** your workload is a full-stack application or API that benefits from Render's project/service topology, `render.yaml` Blueprint configuration, or Render's GitHub integration with a slightly different pricing model than DigitalOcean.

**Choose Railway when** your workload is a full-stack application or API that benefits from Railway's project/environment/service topology, `railway.toml` configuration, or Railway's GitHub integration.

**Choose Vercel when** your workload is a frontend framework (Next.js / SvelteKit / Astro / Remix) and you want zero-config per-commit preview deployments with tight Git integration.

**Choose Azure when** your workload is enterprise .NET or Java, requires Azure-native services (Azure SQL, Cosmos DB, Service Bus), or has compliance requirements (FedRAMP, regulated healthcare) that need Azure's compliance portfolio.

## 8. Pipelinekit command cheatsheet

Filter the table by `do`, `ppr`, or `review` to surface the deploy-relevant slash commands.

<div data-snippet="command-cheatsheet"></div>

