---
name: digitalocean-ops
description: Deploy and verify DigitalOcean App Platform apps when the charter targets digitalocean
allowed-tools:
  - Bash(doctl *)
  - Bash(curl --fail *)
paths:
  - documentation/deployment-digitalocean.html
  - claude/skills/digitalocean-ops/**
---

# DigitalOcean App Platform Operations Skill

This skill wraps the DigitalOcean CLI (`doctl`) for common day-to-day operations: listing apps, deploying applications, checking deployment state, tailing logs, health-check polling, and triggering redeploys. It focuses on the *operational* layer — for canonical `doctl` command reference, use https://docs.digitalocean.com/reference/doctl/ or the `context7` MCP.

The skill is deliberately narrow: it does NOT handle first-time DigitalOcean account creation, headless `DIGITALOCEAN_ACCESS_TOKEN` automation, custom CI workflows, or dashboard-clicked configuration. It assumes the user has already run `doctl auth init` themselves in an interactive shell outside Claude and that the current DigitalOcean CLI context is healthy.

## Keywords

DigitalOcean CLI, doctl, App Platform, doctl apps list, doctl apps get, doctl apps logs, doctl account get, App Spec, .do/app.yaml, health check, exponential backoff, deployment verification, App Platform tier, DO App Platform

## Capabilities

### Authentication posture (FIRST — runs before every operation)

The skill begins every workflow with the following preflight probe:

```bash
doctl account get
```

On non-zero exit (or empty output), STOP immediately and print this prompt: `DigitalOcean auth missing. Run \`doctl auth init\` outside Claude, then re-invoke this skill.` Do not retry. Do not attempt alternative auth flows.

**Non-negotiable constraints:**
- The skill MUST NEVER auto-authenticate. It MUST NOT run `doctl auth init` itself under any circumstance — the user authenticates manually outside Claude.
- The skill MUST NOT read or echo `DIGITALOCEAN_ACCESS_TOKEN`, `DO_ACCESS_TOKEN`, or any value with the substring `do_*` or `dop_*`. Treat any DigitalOcean credential material as a secret.
- The skill MUST NOT cache tokens locally or in the environment.
- Authentication is the user's responsibility. The skill operates against an already-authenticated context only.

**Why this matters:** Non-interactive credential flows in agentic contexts have repeatedly leaked credentials through shell history, log files, and inadvertent transcript captures. The auth posture above eliminates that class of risk entirely — the skill simply refuses to operate without a healthy interactive `doctl auth init` context.

### App listing

List DigitalOcean App Platform apps associated with the authenticated account and confirm the active app before any deploy.

Common patterns:

- `doctl account get` — show the authenticated user and account details
- `doctl apps list` — list all apps for the authenticated account; use to confirm the target app exists and is in the expected state
- `doctl apps list --format ID,Spec.Name,ActiveDeployment.Phase` — machine-readable app list (ID, name, deployment phase)

**App hygiene:**
- Always confirm `doctl account get` returns the correct user before every deploy. The preflight catches stale or missing auth.
- The skill MUST NOT auto-link an app. If no app context is set, STOP and prompt the user to confirm the target app name or ID.

### Deploy

The skill supports deploying via the DigitalOcean CLI.

**Trigger a deploy:**
- `doctl apps create --spec .do/app.yaml` — create a new app from an App Spec file. The App Spec is the declarative source of truth for the app configuration.
- `doctl apps update <app-id> --spec .do/app.yaml` — update an existing app from an App Spec file.

**Configuration via `.do/app.yaml` (App Spec):**
- Place a `.do/app.yaml` App Spec at the project root to declare services, databases, environment variables, instance sizes, and per-component configuration in code.
- Prefer `.do/app.yaml` over dashboard-only configuration so the deployment spec is version-controlled.

### Provider-native verification

Every deploy MUST pass through this verification chain before being considered done.

```bash
# 1. Check app state (poll until ACTIVE or ERROR)
doctl apps get <app-id>

# 2. Tail logs for the first 60s post-deploy — STOP on observed runtime errors
doctl apps logs <app-id> --tail

# 3. Health endpoint probe with exponential backoff (60s timeout)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$DO_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Decision rules:**
- If `doctl apps get <app-id>` shows an ERROR or DEPLOYING-stuck state, STOP. Do not continue. Read `doctl apps logs <app-id>` for the failure reason and report it.
- If `doctl apps logs <app-id> --tail` shows runtime errors (uncaught exceptions, crash loops, 5xx patterns), STOP. Do not proceed until logs are clean.
- If `curl --fail $DO_URL/health` does not return 200 within the 60s exponential backoff window, STOP. Report the failure with the last curl output.

Only after all three steps pass should the deployment be considered production-ready.

### Log tail

Streaming and historical log access patterns.

**Streaming (tail):**
- `doctl apps logs <app-id> --tail` — stream live logs from the active app. Includes deploy and runtime logs.
- `doctl apps logs <app-id>` — one-shot log dump (recent lines).

**When to use:**
- Tail logs immediately after a deploy to catch cold-start failures and config errors.
- For incident investigation, run `doctl apps logs <app-id>` to retrieve recent entries. For durable retention beyond DigitalOcean's native window, configure an external log destination (Datadog, Papertrail, etc.) via the App Spec or DigitalOcean dashboard.

### Redeploy

Re-trigger a deploy without changing source code.

- `doctl apps create-deployment <app-id>` — trigger a new deployment for the specified app. Use to pick up changed environment variables or to recover from a transient build failure.

**When to redeploy:**
- A new environment variable was added in the dashboard and the running app is still on the prior set.
- A transient upstream dependency caused a build failure that subsequently resolved (no code change needed).

**When NOT to redeploy:**
- During an active deployment from the same source — wait for it to finish.

## How to Use

Every workflow MUST include the `doctl account get` preflight as a visible step in the code block — not just narrative. The pattern below MUST be copied into each operational example.

**App status check:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If doctl account get fails: run `doctl auth init` outside Claude, then re-invoke.
doctl account get || { echo "DigitalOcean auth missing — see Installation Requirements"; exit 1; }
# 2. List apps to confirm target app state
doctl apps list
```

**Deploy + verify:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If doctl account get fails: run `doctl auth init` outside Claude, then re-invoke.
doctl account get || { echo "DigitalOcean auth missing — see Installation Requirements"; exit 1; }
# 2. Update app from App Spec (replace <app-id> with your app ID)
doctl apps update <app-id> --spec .do/app.yaml
# 3. Confirm app state via apps get
doctl apps get <app-id>
# 4. Tail logs for 60s post-deploy
doctl apps logs <app-id> --tail
# 5. Health endpoint probe with exponential backoff (60s timeout)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$DO_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

**Log tail (runtime logs):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If doctl account get fails: run `doctl auth init` outside Claude, then re-invoke.
doctl account get || { echo "DigitalOcean auth missing — see Installation Requirements"; exit 1; }
# 2. Stream logs from the active app (Ctrl-C to stop)
doctl apps logs <app-id> --tail
```

**Health probe only (post-deploy verification):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
# If doctl account get fails: run `doctl auth init` outside Claude, then re-invoke.
doctl account get || { echo "DigitalOcean auth missing — see Installation Requirements"; exit 1; }
# 2. Probe /health with exponential backoff (60s total window)
for i in 1 2 4 8 16 29; do
  curl --fail --silent "$DO_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

## When to Use

Use this skill when you need to:

- Check the state of a DigitalOcean App Platform deployment (app list, deployment state).
- Deploy an application to DigitalOcean App Platform via `doctl apps update` or `doctl apps create` and verify it reaches ACTIVE state.
- Tail runtime logs from a DigitalOcean app for live debugging.
- Run a health-check probe with exponential backoff against `$DO_URL/health`.
- Redeploy a DigitalOcean app after an environment-variable change.
- Confirm the active DigitalOcean identity before running an operation.

## When NOT to Use

Do not use this skill for first-time DigitalOcean account setup — that requires interactive `doctl auth init`, which the skill does not perform. Do not use this skill in non-interactive CI environments without a pre-authenticated `DIGITALOCEAN_ACCESS_TOKEN` managed by the CI platform (the skill does not read `DIGITALOCEAN_ACCESS_TOKEN` itself).

Do not use this skill for:

- Bootstrapping a new DigitalOcean account — that requires interactive signup and `doctl auth init`.
- Long-running unattended automation — the skill is built for interactive ops, not for `cron`-style schedulers (use GitHub Actions + the DigitalOcean deploy webhook, or a deploy bot wired with `DIGITALOCEAN_ACCESS_TOKEN` managed outside Claude).
- Dashboard-only configuration (custom domains, managed databases, managed Redis, log-destination wiring, notification rules) — those tasks belong with the `@digitalocean-deployment-engineer` agent and the DigitalOcean dashboard.
- Multi-cloud deploys — this skill is DigitalOcean-only.

## Limitations

- No `DIGITALOCEAN_ACCESS_TOKEN` automation. The skill operates against an already-authenticated interactive `doctl auth init` context only.
- No auto-app-link. The user specifies the target app ID from `doctl apps list` manually.
- No auto-`doctl auth init`. Authentication is the user's responsibility, every time.
- No dashboard-driven environment switching. The user changes environment variables manually in the DigitalOcean dashboard or via `.do/app.yaml`.
- No build-environment introspection beyond `doctl apps get` and `doctl apps logs`. For deep build debugging, use the DigitalOcean dashboard.

## Best Practices

- Always confirm `doctl account get` before every deploy. The preflight catches stale or missing auth before operations begin.
- Never echo `DIGITALOCEAN_ACCESS_TOKEN`, `DO_ACCESS_TOKEN`, or any value with the substring `do_*` or `dop_*`. Treat them as secrets. The skill never reads them; the user manages API tokens outside Claude.
- Always run `doctl apps get <app-id>` after a deploy to confirm the app reached ACTIVE state.
- Tail logs (`doctl apps logs <app-id> --tail`) for the first 60s after every deploy. Cold-start failures and config-only runtime errors surface within that window.
- Always probe `$DO_URL/health` with exponential backoff — not a single one-shot `curl`. DigitalOcean App Platform cold-starts can take several seconds; a single-shot probe produces false negatives.
- Pin the run command and health check path in `.do/app.yaml` so the deployment spec is version-controlled and reproducible.
- Configure environment-specific env vars in `.do/app.yaml` per component. Never reuse production secrets in staging.
- Run `doctl account get` to verify identity scope before every deploy — especially if working across multiple DigitalOcean teams.

## Installation Requirements

- The `doctl` CLI is **not** auto-installed by `scripts/install.sh`. Installation is user-driven — this mirrors Vercel's, Railway's, and Render's "user-driven install" stance. pipelinekit does not auto-install `doctl` in this feature iteration.
- Install `doctl` by following the instructions at https://docs.digitalocean.com/reference/doctl/how-to/install/ — the canonical install path is documented at that URL for macOS, Linux, and Windows.
- **`doctl auth init` is the user's responsibility.** After install, run `doctl auth init` in an interactive shell outside Claude. Do NOT run `doctl auth init` inside Claude — the skill refuses to do so.
- The skill verifies authentication state by running `doctl account get` at the start of every workflow. STOP and prompt the user if it returns non-zero — `DigitalOcean auth missing. Run \`doctl auth init\` outside Claude, then re-invoke this skill.`
- macOS, Linux, and WSL2 are all supported — see the DigitalOcean `doctl` documentation for the canonical install path for your OS.
