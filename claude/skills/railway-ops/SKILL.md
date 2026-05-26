---
name: railway-ops
description: Deploy and verify Railway projects when the charter targets railway
allowed-tools:
  - Bash(railway *)
  - Bash(curl --fail *)
paths:
  - documentation/deployment-railway.html
  - claude/skills/railway-ops/**
---

# Railway Operations Skill

This skill wraps the Railway CLI (`railway`) for common day-to-day operations: listing projects, deploying applications, checking deployment state, tailing logs, health-check polling, and triggering redeploys. It focuses on the *operational* layer — for canonical `railway` command reference, use https://docs.railway.com/reference/cli-api or the `context7` MCP.

The skill is deliberately narrow: it does NOT handle first-time Railway account creation, headless `RAILWAY_TOKEN` automation, custom CI workflows, or dashboard-clicked configuration. It assumes the user has already run `railway login` themselves in an interactive shell outside Claude and that the current Railway CLI context is healthy.

## Keywords

Railway CLI, railway, railway.toml, railway up, railway status, railway logs, railway whoami, railway deploy, railway open, Railway project, Railway environment, Railway service, Railway plan tier, health check, exponential backoff, deployment verification

## Capabilities

### Authentication posture (FIRST — runs before every operation)

The skill begins every workflow with the following preflight probe:

```bash
railway whoami
```

On non-zero exit (or empty output), STOP immediately and print this prompt: `Railway auth missing. Run \`railway login\` outside Claude, then re-invoke this skill.` Do not retry. Do not attempt alternative auth flows.

**Non-negotiable constraints:**
- The skill MUST NEVER auto-authenticate. It MUST NOT run `railway login` itself under any circumstance — the user authenticates manually outside Claude.
- The skill MUST NOT read or echo `RAILWAY_TOKEN`, any value with the substring `railway_`, or any other credential material. Treat any `railway_*` value as a secret.
- The skill MUST NOT cache tokens locally or in the environment.
- Authentication is the user's responsibility. The skill operates against an already-authenticated context only.

**Why this matters:** Non-interactive credential flows in agentic contexts have repeatedly leaked credentials through shell history, log files, and inadvertent transcript captures. The auth posture above eliminates that class of risk entirely — the skill simply refuses to operate without a healthy interactive `railway login` context.

### Project listing

List Railway projects associated with the authenticated user and confirm the active project before any deploy.

Common patterns:

- `railway whoami` — show the authenticated user
- `railway status` — show the current project, environment, and service link state
- `railway open` — open the Railway dashboard for the linked project in the browser

**Project hygiene:**
- Always confirm `railway whoami` returns the correct user before every deploy. The preflight catches stale or missing auth.
- The skill MUST NOT auto-link a project. If no project is linked, STOP and prompt the user to run `railway link` themselves outside Claude.

### Deploy

The skill supports deploying via the Railway CLI.

**Trigger a deploy:**
- `railway up` — upload local source and trigger a build + deploy on Railway
- `railway up --detach` — trigger the deploy and detach immediately (non-blocking); use when you want to tail logs separately

**Environment targeting:**
- `railway environment <name>` — switch the active environment (run OUTSIDE Claude; the skill does not run this)
- Confirm the active environment via `railway status` before deploying

**Configuration via `railway.toml`:**
- Place a `railway.toml` at the project root to declare build commands, start commands, healthcheck paths, and environment-specific overrides.
- Prefer `railway.toml` over dashboard-only configuration so the deployment spec is version-controlled.

### Provider-native verification

Every deploy MUST pass through this verification chain before being considered done.

```bash
# 1. Check deployment state (poll until ACTIVE or FAILED)
railway status

# 2. Tail logs for the first 60s post-deploy — STOP on observed runtime errors
railway logs --tail

# 3. Health endpoint probe with exponential backoff (60s timeout)
RAILWAY_URL="${RAILWAY_URL:-$(railway status --json 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("url",""))' 2>/dev/null)}"
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RAILWAY_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Decision rules:**
- If `railway status` shows FAILED or CRASHED, STOP. Do not continue. Read `railway logs` for the failure reason and report it.
- If `railway logs --tail` shows runtime errors (uncaught exceptions, crash loops, 5xx patterns), STOP. Do not proceed until logs are clean.
- If `curl --fail $RAILWAY_URL/health` does not return 200 within the 60s exponential backoff window, STOP. Report the failure with the last curl output.

Only after all three steps pass should the deployment be considered production-ready.

### Log tail

Streaming and historical log access patterns.

**Streaming (tail):**
- `railway logs --tail` — stream live logs from the active deployment. Includes build and runtime logs.
- `railway logs` — one-shot log dump (recent lines).

**When to use:**
- Tail logs immediately after a deploy to catch cold-start failures and config errors.
- For incident investigation, run `railway logs` to retrieve recent entries. For durable retention beyond Railway's native window, configure an external log sink (Datadog, Papertrail, etc.) via the Railway dashboard.

### Redeploy

Re-trigger a deploy without changing source code.

- `railway up` (from a clean working tree) — re-upload and redeploy. Use to pick up changed environment variables or to recover from a transient build failure.

**When to redeploy:**
- A new environment variable was added in the dashboard and the running service is still on the prior set.
- A transient upstream dependency caused a build failure that subsequently resolved (no code change needed).

**When NOT to redeploy:**
- During an active deploy from the same source — wait for it to finish.

## How to Use

Every workflow MUST include the `railway whoami` preflight as a visible step in the code block — not just narrative. The pattern below MUST be copied into each operational example.

**Project status check:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If railway whoami fails: run `railway login` outside Claude, then re-invoke.
railway whoami || { echo "Railway auth missing — see Installation Requirements"; exit 1; }
# 2. Show current project, environment, and service link
railway status
```

**Deploy + verify:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If railway whoami fails: run `railway login` outside Claude, then re-invoke.
railway whoami || { echo "Railway auth missing — see Installation Requirements"; exit 1; }
# 2. Upload and deploy
railway up
# 3. Check deployment state
railway status
# 4. Tail logs for 60s post-deploy
railway logs --tail
# 5. Health endpoint probe with exponential backoff (60s timeout)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RAILWAY_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Log tail (runtime logs):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If railway whoami fails: run `railway login` outside Claude, then re-invoke.
railway whoami || { echo "Railway auth missing — see Installation Requirements"; exit 1; }
# 2. Stream logs from the active deployment (Ctrl-C to stop)
railway logs --tail
```

**Health probe only (post-deploy verification):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If railway whoami fails: run `railway login` outside Claude, then re-invoke.
railway whoami || { echo "Railway auth missing — see Installation Requirements"; exit 1; }
# 2. Probe /health with exponential backoff (60s total window)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RAILWAY_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

## When to Use

Use this skill when you need to:

- Check the status of a Railway deployment (project, environment, service state).
- Deploy an application to Railway via `railway up` and verify it reaches ACTIVE state.
- Tail runtime logs from a Railway deployment for live debugging.
- Run a health-check probe with exponential backoff against `$RAILWAY_URL/health`.
- Redeploy a Railway service after an environment-variable change.
- Confirm the active Railway identity before running an operation.

## When NOT to Use

Do not use this skill for first-time Railway account setup — that requires interactive `railway login`, which the skill does not perform. Do not use this skill in non-interactive CI environments without a pre-authenticated `RAILWAY_TOKEN` managed by the CI platform (the skill does not read `RAILWAY_TOKEN` itself).

Do not use this skill for:

- Bootstrapping a new Railway account — that requires interactive signup + `railway login`.
- Long-running unattended automation — the skill is built for interactive ops, not for `cron`-style schedulers (use GitHub Actions + the Railway deploy webhook, or a deploy bot wired with `RAILWAY_TOKEN` managed outside Claude).
- Dashboard-only configuration (custom domains, volume mounts, env-var creation, log-sink wiring) — those tasks belong with the `@deployment-engineer` agent (dispatched with `provider: railway`) and the Railway dashboard.
- Multi-cloud deploys — this skill is Railway-only.

## Limitations

- No `RAILWAY_TOKEN` automation. The skill operates against an already-authenticated interactive `railway login` context only.
- No auto-`railway link`. The user links a project manually outside Claude.
- No auto-`railway login`. Authentication is the user's responsibility, every time.
- No dashboard-driven environment switching. The user changes the active environment manually outside Claude.
- No build-environment introspection beyond `railway status` and `railway logs`. For deep build debugging, use the Railway dashboard.

## Best Practices

- Always confirm `railway whoami` before every deploy. The preflight catches stale or missing auth before operations begin.
- Never echo `RAILWAY_TOKEN` or any value with the substring `railway_`. Treat them as secrets. The skill never reads them; the user manages tokens outside Claude.
- Always run `railway status` after a deploy to confirm the deployment reached ACTIVE state.
- Tail logs (`railway logs --tail`) for the first 60s after every deploy. Cold-start failures and config-only runtime errors surface within that window.
- Always probe `$RAILWAY_URL/health` with exponential backoff — not a single one-shot `curl`. Railway cold-starts can take several seconds; a single-shot probe produces false negatives.
- Pin the start command and healthcheck path in `railway.toml` so the deployment spec is version-controlled and reproducible.
- Configure environment-specific env vars in the Railway dashboard per environment (production vs. staging). Never reuse production secrets in staging.
- Run `railway whoami` to verify identity scope before every deploy — especially if working across multiple Railway accounts.

## Installation Requirements

- The Railway CLI is **not** auto-installed by `scripts/install.sh`. Installation is user-driven — this mirrors Vercel's "user-driven install" stance. pipelinekit does not auto-install Railway CLI in this feature iteration.
- Install the Railway CLI by following the instructions at https://docs.railway.com/guides/cli — typically `npm i -g @railway/cli` or the platform-native method for your OS.
- **`railway login` is the user's responsibility.** After install, run `railway login` in an interactive shell outside Claude. Do NOT run `railway login` inside Claude — the skill refuses to do so.
- The skill verifies authentication state by running `railway whoami` at the start of every workflow. STOP and prompt the user if it returns non-zero — `Railway auth missing. Run \`railway login\` outside Claude, then re-invoke this skill.`
- macOS, Linux, and WSL2 are all supported via the npm install path (or the platform-native install method described in the Railway docs).
