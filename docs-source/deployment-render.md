# Render Deployment Provider

Render account setup, service config, render.yaml IaC, environment groups, pipelinekit integration via Charter Topic 10, runtime verification, and provider comparison.

<div data-snippet="comparison-tabs"></div>

Render account setup, service config, render.yaml IaC, environment groups, pipelinekit integration via Charter Topic 10, runtime verification, and provider comparison.

pipelinekit integrates Render as a first-class deployment provider on the same footing as Vercel, Azure, and Railway. When your project charter selects `render` as the deployment target (Charter Topic 10), pipelinekit routes deployment work to the `@render-deployment-engineer` agent and the `render-ops` skill automatically.

## 1. What is the Render provider integration

Render is a cloud platform that provisions infrastructure from source code with zero Dockerfile required for most runtimes (Node.js, Python, Go, Ruby). Render supports persistent disks, cron jobs, private networking, and multi-service projects defined via a `render.yaml` Blueprint at the repository root.

The pipelinekit Render integration consists of three components:

- **`claude/skills/render-ops/SKILL.md`** — the operational skill that wraps the Render CLI (`render`) for day-to-day ops: service listing, deploy, log tail, health-endpoint polling, and redeploy. Enforces the auth-posture contract (never auto-authenticates, always starts with `render whoami`).
- **`claude/agents/render-deployment-engineer.md`** — the deployment-engineer agent that covers Render project/service topology, `render.yaml` Blueprint configuration authoring, observability wiring, cost guardrails, and the full provider-native verification chain.
- **Charter Topic 10 integration** — selecting `render` as the deployment provider in the project charter automatically routes `/pipeline` deployment phases to the agent and skill above.

## 2. Account & project setup

1.  Create a Render account at [render.com](https://render.com). You can sign up with GitHub for zero-friction Git integration.

2.  Create a new service via the Render dashboard. A Web Service, Background Worker, or other service type is the primary deployable unit on Render. One service per deployable application is recommended for clean environment and secret isolation.

3.  Optionally define your full service topology in a `render.yaml` Blueprint at the repository root:

        render.yaml

    The `render.yaml` Blueprint declares services, databases, and environment groups in code. Render picks it up automatically when the repository is connected to a Render project. Prefer `render.yaml` over dashboard-only configuration so the deployment spec is version-controlled.

4.  Authenticate the CLI before deploying:

        render login

    Run `render login` outside Claude in an interactive shell. pipelinekit's `render-ops` skill never runs `render login` for you — authentication is your responsibility.

5.  Verify authentication and list your services to confirm the target service exists:

        render whoami
        render services list

## 3. CLI install

The Render CLI is not auto-installed by pipelinekit. Installation is user-driven — this mirrors Vercel's and Railway's install posture. To install the Render CLI, follow the instructions in the [Render CLI documentation](https://render.com/docs/cli).

pipelinekit does not automate this step. Refer to the Render CLI docs linked above for the canonical install path for your operating system (macOS, Linux, or Windows).

After installing, run `render login` in an interactive shell outside Claude to authenticate the CLI. Then verify the install and auth with:

    render whoami

A successful `render whoami` is the prerequisite for every `render-ops` skill invocation.

## 4. Pipelinekit integration

To activate the Render provider integration in pipelinekit, select `render` as the deployment provider when answering Charter Topic 10 during `/pipeline` Step 0 (Charter Discovery).

**Charter Topic 10** asks: *"What is your deployment target?"* Answer `render` (Option D). The charter records this answer and downstream pipeline phases use it to route deployment work automatically:

- The `/implement-plan` phase routes Render-specific deployment tasks to the `@render-deployment-engineer` agent.
- The agent invokes `claude/skills/render-ops/SKILL.md` for all CLI operations, enforcing the auth-posture contract (preflight `render whoami`, never auto-authenticates).

If you have an existing charter and want to switch to Render, update Charter Topic 10 to `render` and re-run the relevant pipeline phase.

## 5. Runtime verification commands

pipelinekit's Render integration uses the following verification chain after every deploy. All three steps must pass before a deployment is declared production-ready.

### Step 1: Service state check

    render services list

Confirms the service reached **LIVE** state. If the state is FAILED or DEPLOY_FAILED, do not proceed — read `render logs` for the failure reason.

### Step 2: Log tail (60 seconds post-deploy)

    render logs --tail

Streams live logs from the active service for the first 60 seconds after deploy. Cold-start failures and config-only runtime errors surface within this window.

### Step 3: Health endpoint probe with exponential backoff (60s timeout)

    for i in 1 2 4 8 16 32; do
      curl --fail --silent "$RENDER_URL/health" && break
      echo "Health check failed — retrying in ${i}s (exponential backoff)..."
      sleep "$i"
    done

Probes `$RENDER_URL/health` with a 60s total timeout using exponential backoff (1 → 2 → 4 → 8 → 16 → 32 seconds between retries). Render services can have cold-start delays; a single one-shot `curl` probe produces false negatives. The exponential backoff pattern handles cold-start gracefully.

Set `healthCheckPath: /health` in your `render.yaml` so Render itself also polls the health endpoint before routing traffic to the new deployment.

## 6. Auth posture

pipelinekit's Render integration enforces a strict auth posture: Claude never runs `render login`, never reads `RENDER_API_KEY` from the environment, and never caches or echoes Render credentials.

- **You are responsible for `render login`.** Run it outside Claude in an interactive shell before invoking any Render skill or agent. Claude refuses to run `render login` for you.

- **pipelinekit does not read `RENDER_API_KEY`.** If you are wiring a CI pipeline (GitHub Actions, etc.), manage `RENDER_API_KEY` as a CI secret outside Claude. The `render-ops` skill and `@render-deployment-engineer` agent never read it.

- **Preflight on every operation.** Every `render-ops` workflow begins with `render whoami`. On non-zero exit, the skill stops and prompts:

      Render auth missing. Run `render login` outside Claude, then re-invoke this skill.

This posture eliminates a class of credential-leak risk that has historically occurred when agentic contexts run non-interactive auth flows (shell history leaks, log captures, transcript exports).

## 7. When to use Render vs. other providers

Render, Railway, Vercel, and Azure serve overlapping but distinct workload profiles. Use this comparison to guide Charter Topic 10 selection.

| Dimension        | Render                                                                             | Railway                                                          | Vercel                                                          | Azure                                                                       |
|------------------|------------------------------------------------------------------------------------|------------------------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------|
| Best for         | Full-stack apps, APIs, workers, databases; Blueprint-driven multi-service projects | Full-stack apps, APIs, workers, databases in one project         | Frontend-heavy apps (Next.js, SvelteKit, Astro, Remix)          | Enterprise .NET / Java workloads, regulated industries                      |
| Runtime model    | Always-on services (paid plans); spin-down on inactivity (Free)                    | Always-on services (Pro); sleep on inactivity (Hobby)            | Serverless / Edge Functions; no persistent processes            | App Service (persistent), Container Apps (serverless containers), Functions |
| Database support | First-class: managed PostgreSQL as a Render service, linked via render.yaml        | First-class: Postgres, MySQL, Redis, MongoDB as Railway services | No native database — use external (PlanetScale, Supabase, Neon) | Azure SQL, Cosmos DB, Cache for Redis — managed PaaS                        |
| Config format    | `render.yaml` (Blueprint)                                                          | `railway.toml`                                                   | `vercel.json`                                                   | Bicep / ARM templates, App Service config                                   |
| CLI auth posture | User-driven `render login`                                                         | User-driven `railway login`                                      | User-driven `vercel login`                                      | User-driven `az login`                                                      |
| Cold start       | Yes (Free plan spin-down); No (paid plans with always-on)                          | Yes (Hobby plan sleep); No (Pro plan)                            | Yes (Serverless Functions); Near-zero (Edge Functions)          | Varies by service tier and scaling config                                   |
| Compliance       | SOC 2 / HIPAA on Enterprise plan                                                   | SOC 2 / HIPAA on Enterprise plan                                 | SOC 2 / HIPAA on Enterprise plan                                | Broad: ISO 27001, SOC 1/2/3, HIPAA, FedRAMP, GDPR                           |

**Choose Render when** your workload needs persistent processes (long-running workers, WebSocket servers), managed PostgreSQL co-located with the app, a declarative Blueprint spec for multi-service projects, or an alternative to Railway with a slightly different platform ergonomics and pricing model.

**Choose Railway when** your workload is a full-stack application or API that benefits from Railway's project/environment/service topology, `railway.toml` configuration, or Railway's GitHub integration.

**Choose Vercel when** your workload is a frontend framework (Next.js / SvelteKit / Astro / Remix) and you want zero-config per-commit preview deployments with tight Git integration.

**Choose Azure when** your workload is enterprise .NET or Java, requires Azure-native services (Azure SQL, Cosmos DB, Service Bus), or has compliance requirements (FedRAMP, regulated healthcare) that need Azure's compliance portfolio.

