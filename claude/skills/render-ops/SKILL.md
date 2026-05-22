---
name: render-ops
description: Deploy and verify Render services when the charter targets render
allowed-tools:
  - Bash(render *)
  - Bash(curl --fail *)
paths:
  - documentation/deployment-render.html
  - claude/skills/render-ops/**
---

# Render Operations Skill

This skill wraps the Render CLI (`render`) for common day-to-day operations: listing services, deploying applications, checking deployment state, tailing logs, health-check polling, and triggering redeploys. It focuses on the *operational* layer — for canonical `render` command reference, use https://render.com/docs/cli or the `context7` MCP.

The skill is deliberately narrow: it does NOT handle first-time Render account creation, headless `RENDER_API_KEY` automation, custom CI workflows, or dashboard-clicked configuration. It assumes the user has already run `render login` themselves in an interactive shell outside Claude and that the current Render CLI context is healthy.

## Keywords

Render CLI, render, render.yaml, render deploy, render services list, render logs, render whoami, Render service, Render environment, Render blueprint, Render plan tier, health check, exponential backoff, deployment verification

## Capabilities

### Authentication posture (FIRST — runs before every operation)

The skill begins every workflow with the following preflight probe:

```bash
render whoami
```

On non-zero exit (or empty output), STOP immediately and print this prompt: `Render auth missing. Run \`render login\` outside Claude, then re-invoke this skill.` Do not retry. Do not attempt alternative auth flows.

**Non-negotiable constraints:**
- The skill MUST NEVER auto-authenticate. It MUST NOT run `render login` itself under any circumstance — the user authenticates manually outside Claude.
- The skill MUST NOT read or echo `RENDER_API_KEY`, any value with the substring `render_`, or any other credential material. Treat any `render_*` value as a secret.
- The skill MUST NOT cache tokens locally or in the environment.
- Authentication is the user's responsibility. The skill operates against an already-authenticated context only.

**Why this matters:** Non-interactive credential flows in agentic contexts have repeatedly leaked credentials through shell history, log files, and inadvertent transcript captures. The auth posture above eliminates that class of risk entirely — the skill simply refuses to operate without a healthy interactive `render login` context.

### Project/service listing

List Render services associated with the authenticated user and confirm the active service before any deploy.

Common patterns:

- `render whoami` — show the authenticated user
- `render services list` — list all services for the authenticated account; use to confirm the target service exists and is in the expected state
- `render services list --json` — machine-readable service list (id, name, type, status, deployURL)

**Service hygiene:**
- Always confirm `render whoami` returns the correct user before every deploy. The preflight catches stale or missing auth.
- The skill MUST NOT auto-link a service. If no service context is set, STOP and prompt the user to confirm the target service name or ID.

### Deploy

The skill supports deploying via the Render CLI.

**Trigger a deploy:**
- `render deploy create <service-id>` — trigger a deploy for the specified service. The service ID is obtained from `render services list`.
- `render deploy create <service-id> --wait` — trigger the deploy and wait for it to reach LIVE or FAILED state before returning.

**Configuration via `render.yaml` (Blueprint):**
- Place a `render.yaml` at the project root to declare services, databases, environment groups, and per-service configuration in code.
- Prefer `render.yaml` over dashboard-only configuration so the deployment spec is version-controlled.

### Provider-native verification

Every deploy MUST pass through this verification chain before being considered done.

```bash
# 1. Check service state (poll until LIVE or FAILED)
render services list

# 2. Tail logs for the first 60s post-deploy — STOP on observed runtime errors
render logs --tail

# 3. Health endpoint probe with exponential backoff (60s timeout)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RENDER_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Decision rules:**
- If `render services list` shows a FAILED or DEPLOY_FAILED state, STOP. Do not continue. Read `render logs` for the failure reason and report it.
- If `render logs --tail` shows runtime errors (uncaught exceptions, crash loops, 5xx patterns), STOP. Do not proceed until logs are clean.
- If `curl --fail $RENDER_URL/health` does not return 200 within the 60s exponential backoff window, STOP. Report the failure with the last curl output.

Only after all three steps pass should the deployment be considered production-ready.

### Log tail

Streaming and historical log access patterns.

**Streaming (tail):**
- `render logs --tail` — stream live logs from the active service. Includes deploy and runtime logs.
- `render logs` — one-shot log dump (recent lines).

**When to use:**
- Tail logs immediately after a deploy to catch cold-start failures and config errors.
- For incident investigation, run `render logs` to retrieve recent entries. For durable retention beyond Render's native window, configure an external log sink (Datadog, Papertrail, etc.) via the Render dashboard.

### Redeploy

Re-trigger a deploy without changing source code.

- `render deploy create <service-id>` (from a clean working tree) — re-upload and redeploy. Use to pick up changed environment variables or to recover from a transient build failure.

**When to redeploy:**
- A new environment variable was added in the dashboard and the running service is still on the prior set.
- A transient upstream dependency caused a build failure that subsequently resolved (no code change needed).

**When NOT to redeploy:**
- During an active deploy from the same source — wait for it to finish.

## How to Use

Every workflow MUST include the `render whoami` preflight as a visible step in the code block — not just narrative. The pattern below MUST be copied into each operational example.

**Service status check:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If render whoami fails: run `render login` outside Claude, then re-invoke.
render whoami || { echo "Render auth missing — see Installation Requirements"; exit 1; }
# 2. List services to confirm target service state
render services list
```

**Deploy + verify:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If render whoami fails: run `render login` outside Claude, then re-invoke.
render whoami || { echo "Render auth missing — see Installation Requirements"; exit 1; }
# 2. Trigger deploy for the target service (replace <service-id> with your service ID)
render deploy create <service-id> --wait
# 3. Confirm service state via services list
render services list
# 4. Tail logs for 60s post-deploy
render logs --tail
# 5. Health endpoint probe with exponential backoff (60s timeout)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RENDER_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Log tail (runtime logs):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If render whoami fails: run `render login` outside Claude, then re-invoke.
render whoami || { echo "Render auth missing — see Installation Requirements"; exit 1; }
# 2. Stream logs from the active service (Ctrl-C to stop)
render logs --tail
```

**Health probe only (post-deploy verification):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If render whoami fails: run `render login` outside Claude, then re-invoke.
render whoami || { echo "Render auth missing — see Installation Requirements"; exit 1; }
# 2. Probe /health with exponential backoff (60s total window)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$RENDER_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

## When to Use

Use this skill when you need to:

- Check the state of a Render service deployment (service list, deploy state).
- Deploy an application to Render via `render deploy create` and verify it reaches LIVE state.
- Tail runtime logs from a Render service for live debugging.
- Run a health-check probe with exponential backoff against `$RENDER_URL/health`.
- Redeploy a Render service after an environment-variable change.
- Confirm the active Render identity before running an operation.

## When NOT to Use

Do not use this skill for first-time Render account setup — that requires interactive `render login`, which the skill does not perform. Do not use this skill in non-interactive CI environments without a pre-authenticated `RENDER_API_KEY` managed by the CI platform (the skill does not read `RENDER_API_KEY` itself).

Do not use this skill for:

- Bootstrapping a new Render account — that requires interactive signup and `render login`.
- Long-running unattended automation — the skill is built for interactive ops, not for `cron`-style schedulers (use GitHub Actions + the Render deploy webhook, or a deploy bot wired with `RENDER_API_KEY` managed outside Claude).
- Dashboard-only configuration (custom domains, disks, env-group creation, log-sink wiring) — those tasks belong with the `@render-deployment-engineer` agent and the Render dashboard.
- Multi-cloud deploys — this skill is Render-only.

## Limitations

- No `RENDER_API_KEY` automation. The skill operates against an already-authenticated interactive `render login` context only.
- No auto-service-link. The user specifies the target service ID from `render services list` manually.
- No auto-`render login`. Authentication is the user's responsibility, every time.
- No dashboard-driven environment switching. The user changes environment variables manually in the Render dashboard.
- No build-environment introspection beyond `render services list` and `render logs`. For deep build debugging, use the Render dashboard.

## Best Practices

- Always confirm `render whoami` before every deploy. The preflight catches stale or missing auth before operations begin.
- Never echo `RENDER_API_KEY` or any value with the substring `render_`. Treat them as secrets. The skill never reads them; the user manages API keys outside Claude.
- Always run `render services list` after a deploy to confirm the service reached LIVE state.
- Tail logs (`render logs --tail`) for the first 60s after every deploy. Cold-start failures and config-only runtime errors surface within that window.
- Always probe `$RENDER_URL/health` with exponential backoff — not a single one-shot `curl`. Render cold-starts can take several seconds; a single-shot probe produces false negatives.
- Pin the start command and healthcheck path in `render.yaml` so the deployment spec is version-controlled and reproducible.
- Configure environment-specific env vars in the Render dashboard per service. Never reuse production secrets in staging.
- Run `render whoami` to verify identity scope before every deploy — especially if working across multiple Render accounts.

## Installation Requirements

- The Render CLI is **not** auto-installed by `scripts/install.sh`. Installation is user-driven — this mirrors Vercel's "user-driven install" stance. pipelinekit does not auto-install Render CLI in this feature iteration.
- Install the Render CLI by following the instructions at https://render.com/docs/cli — the canonical install path is documented at that URL for macOS, Linux, and Windows.
- **`render login` is the user's responsibility.** After install, run `render login` in an interactive shell outside Claude. Do NOT run `render login` inside Claude — the skill refuses to do so.
- The skill verifies authentication state by running `render whoami` at the start of every workflow. STOP and prompt the user if it returns non-zero — `Render auth missing. Run \`render login\` outside Claude, then re-invoke this skill.`
- macOS, Linux, and WSL2 are all supported — see the Render CLI documentation for the canonical install path for your OS.
