---
name: vercel-ops
description: Vercel CLI (`vercel`) wrapper for common ops — project listing, deploy (preview / production), `vercel inspect` verification, log tail, redeploy. STOPS and prompts the user if `vercel whoami` fails — never auto-authenticates. Use when running day-to-day Vercel operations against an already-authenticated context.
allowed-tools:
  - Read
  - Bash
paths:
  - claude/skills/vercel-ops/**
  - vercel.json
  - documentation/deployment-vercel.html
---

# Vercel Operations Skill

This skill wraps the Vercel CLI (`vercel`) for common day-to-day operations: listing projects, deploying applications (preview + production), inspecting deployment state, tailing logs, and triggering redeploys. It focuses on the *operational* layer — for canonical `vercel` command reference, use https://vercel.com/docs/cli or the `context7` MCP.

The skill is deliberately narrow: it does NOT handle first-time Vercel setup, headless `VERCEL_TOKEN` automation, custom CI workflows, or dashboard-clicked configuration. It assumes the user has already run `vercel login` themselves in an interactive shell and that the current Vercel CLI context is healthy.

## Keywords

Vercel CLI, vercel, Next.js, SvelteKit, Astro, Remix, Edge Functions, Serverless Functions, vercel.json, framework preset, preview deployment, production deployment, vercel inspect, vercel deploy, vercel logs, vercel redeploy, vercel whoami, vercel login, vercel scope, vercel switch, Vercel team, Web Analytics, log drain

## Capabilities

### Authentication posture (FIRST — runs before every operation)

The skill begins every workflow with the following preflight probe:

```bash
vercel whoami
```

On non-zero exit (or empty output), STOP immediately and print this prompt: `Vercel auth missing. Run \`vercel login\` outside Claude, then re-invoke this skill.` Do not retry. Do not attempt alternative auth flows.

**Non-negotiable constraints:**
- The skill MUST NEVER auto-authenticate. It MUST NOT run `vercel login` itself under any circumstance — the user authenticates manually outside Claude.
- The skill MUST NOT read or echo `VERCEL_TOKEN`, any value with the substring `vercel_`, or any other credential material. Treat any `vercel_*` value as a secret.
- The skill MUST NOT cache tokens locally or in the environment.
- Authentication is the user's responsibility. The skill operates against an already-authenticated context only.

**Why this matters:** Non-interactive credential flows in agentic contexts have repeatedly leaked credentials through shell history, log files, and inadvertent transcript captures. The auth posture above eliminates that class of risk entirely — the skill simply refuses to operate without a healthy interactive `vercel login` context.

### Project & scope listing

List Vercel projects within the current scope (personal account or active team), and confirm the active scope before any deploy.

Common patterns:

- `vercel whoami` — show the active scope (user or team)
- `vercel project ls` — list all projects in the active scope
- `vercel ls` — list deployments for the current project (run inside a linked repo)
- `vercel ls <project>` — list deployments for a named project (any scope you have access to)
- `vercel switch <team>` — change the active scope to a team (run OUTSIDE Claude; the skill does not run this)

**Scope hygiene:**
- Always confirm `vercel whoami` shows the right scope before every deploy. Multi-team users on Vercel routinely deploy into the wrong scope; the preflight catches it.
- The skill MUST NOT auto-`vercel switch`. If the active scope is wrong, STOP and prompt the user to run `vercel switch <team>` themselves outside Claude.

### Deploy

The skill supports two deploy surfaces — preview and production.

**Preview deploy (per-commit URL):**
- `vercel deploy` — build remotely on Vercel and return a per-commit preview URL
- `vercel deploy --prebuilt` — upload the local `.vercel/output` directory (after `vercel build`) and return a preview URL. Use this when the build artifact must match CI exactly.
- `vercel build` — produce `.vercel/output` locally; pair with `--prebuilt` for byte-identical preview + prod artifacts

**Production deploy:**
- `vercel --prod` — promote to production. ALWAYS pair with the preview-smoke check (see § Provider-native verification below). Never auto-promote a preview to production without smoke-test confirmation.
- `vercel deploy --prebuilt --prod` — upload prebuilt artifact straight to production (after preview smoke passed)
- `vercel promote <deployment-url>` — promote an existing preview deployment to production (alternative to a fresh `--prod` build)

**Framework preset gotchas:**
- Vercel auto-detects Next.js, SvelteKit, Astro, Remix, Nuxt, Gatsby, and others via the `framework` field in `vercel.json` (or by package.json inspection). Override only when auto-detect is wrong.
- Output directory defaults differ per framework: Next.js uses `.next`, SvelteKit uses `.svelte-kit`, Astro uses `dist`. The framework preset normally handles this — only override `outputDirectory` in `vercel.json` for custom build pipelines.
- Edge Functions require `runtime: edge` in the route config. Serverless Functions default to Node.js; switch to `runtime: nodejs20.x` (or similar) explicitly when pinning.

### Provider-native verification

Every deploy MUST pass through this verification chain before being considered done.

```bash
# 1. Preview-URL smoke (the URL returned by `vercel deploy`)
curl -sI "$PREVIEW_URL" | head -1   # expect 200 or a 30x; non-2xx/3xx => FAIL

# 2. Block until the deployment reaches READY state (or ERROR)
vercel inspect "$PREVIEW_URL" --wait

# 3. Tail logs for the first 60s post-deploy — STOP on observed runtime errors
vercel logs --follow "$PREVIEW_URL"
```

**Decision rules:**
- If step 1 returns a non-2xx/3xx HTTP status, STOP. Do not promote. Re-run the deploy after fixing the build.
- If step 2 returns `ERROR` state, STOP. Read `vercel inspect` output for the failure reason and report it.
- If step 3 shows runtime errors (uncaught exceptions, 500s, cold-start failures), STOP. Do not promote until logs are clean.

Only after all three steps pass should a `vercel --prod` (or `vercel promote`) be considered safe.

### Log tail

Streaming and historical log access patterns.

**Streaming (tail / follow):**
- `vercel logs --follow <deployment-url>` — tail logs for a specific deployment. Includes build logs (if attached) and runtime logs (function invocations).
- `vercel logs <deployment-url>` — one-shot log dump (last few hundred lines).

**Build vs runtime distinction:**
- Build logs are surfaced inline during `vercel deploy` and are also retrievable via `vercel inspect <url> --logs`.
- Runtime logs (function executions, edge requests) stream via `vercel logs --follow`. For durable retention, configure a Log Drain to Datadog / Logflare / Axiom in the Vercel dashboard.

**When to use:**
- Streaming logs are for live debugging — what is the deployment doing right now?
- For incident investigation > 60 minutes old, query the Log Drain target (Datadog / Logflare) — Vercel's own log retention is short.

### Redeploy

Re-trigger a deploy without changing the source code.

- `vercel redeploy <deployment-url>` — re-run the build and re-deploy with no source changes. Use to pick up changed environment variables, re-bind a custom domain, or recover from a flaky external dependency at build time.
- `vercel --prod` (from a clean working tree) — re-run a production deploy; pairs with the verification chain above.

**When to redeploy:**
- A new environment variable was added in the dashboard and the running deploy is still on the prior set.
- A flaky upstream dependency caused a build failure that subsequently resolved (no code change needed).
- A custom domain DNS change is now active; redeploy to re-bind the certificate.

**When NOT to redeploy:**
- During an active deploy from the same source — wait for it to finish.
- To "kick" production traffic patterns — Vercel's edge cache invalidation is not driven by redeploy. Use the dashboard purge or a `vercel deploy --force` instead.

## How to Use

Every workflow MUST include the `vercel whoami` preflight as a visible step in the code block — not just narrative. The pattern below MUST be copied into each operational example.

**Project listing:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
vercel whoami || { echo "Vercel auth missing. Run: vercel login (outside Claude)"; exit 1; }
# 2. List projects in the active scope
vercel project ls
```

**Preview deploy:**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
vercel whoami || { echo "Vercel auth missing. Run: vercel login (outside Claude)"; exit 1; }
# 2. Build locally and upload prebuilt artifact (preview)
vercel build
PREVIEW_URL=$(vercel deploy --prebuilt)
# 3. Smoke the preview URL
curl -sI "$PREVIEW_URL" | head -1
# 4. Block until READY (or ERROR)
vercel inspect "$PREVIEW_URL" --wait
```

**Log tail (runtime logs from a deployment):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
vercel whoami || { echo "Vercel auth missing. Run: vercel login (outside Claude)"; exit 1; }
# 2. Stream logs from the deployment (Ctrl-C to stop)
vercel logs --follow https://myapp-abc123.vercel.app
```

**Production redeploy (verification-gated):**

```bash
# 1. Confirm authenticated context (STOP if non-zero exit)
vercel whoami || { echo "Vercel auth missing. Run: vercel login (outside Claude)"; exit 1; }
# 2. Re-trigger the production deploy
vercel --prod
# 3. Smoke + inspect (see Provider-native verification above)
```

**Scope confirmation:**

```bash
# Show the active Vercel scope (identity only — never dump tokens)
vercel whoami
```

## When to Use

Use this skill when you need to:

- List Vercel projects in the active scope (personal or team).
- Deploy an application as a preview (`vercel deploy`) or to production (`vercel --prod`).
- Verify a deployment's readiness via `vercel inspect <url> --wait`.
- Tail runtime logs from a deployment for live debugging.
- Redeploy an existing deployment after an env-var or DNS change.
- Confirm the active Vercel scope before running an operation.

## When NOT to Use

Do not use this skill for first-time Vercel setup — that requires interactive `vercel login`, which the skill does not perform. Do not use this skill in non-interactive CI environments without a pre-authenticated `VERCEL_TOKEN` managed by the CI platform (the skill does not read `VERCEL_TOKEN` itself).

Do not use this skill for:

- Bootstrapping a new Vercel account — that requires interactive signup + `vercel login`.
- Long-running unattended automation — the skill is built for interactive ops, not for `cron`-style schedulers (use GitHub Actions + the Vercel deploy hook, or a deploy bot wired with `VERCEL_TOKEN` managed outside Claude).
- Dashboard-only configuration (custom domains, env-var creation, log-drain wiring) — those tasks belong with the `@deployment-engineer` agent (dispatched with `provider: vercel`) and the Vercel dashboard.
- Multi-cloud deploys — this skill is Vercel-only.
- Vercel Enterprise tenant administration — out of scope for v1.

## Limitations

- No `VERCEL_TOKEN` automation. The skill operates against an already-authenticated interactive `vercel login` context only.
- No auto-`vercel switch`. The user changes scope manually outside Claude.
- No auto-`vercel login`. Authentication is the user's responsibility, every time.
- No edge-cache purge. The skill does not invalidate the edge cache directly — use the Vercel dashboard or a custom purge endpoint.
- No build-environment introspection beyond `vercel inspect`. For deep build-environment debugging, use the Vercel dashboard build logs.

## Best Practices

- Always confirm `vercel whoami` before every deploy. Multi-team users on Vercel routinely deploy into the wrong scope; the preflight catches it.
- Never echo `VERCEL_TOKEN` or any value with the substring `vercel_`. Treat them as secrets. The skill never reads them; the user manages tokens outside Claude.
- Prefer `vercel deploy --prebuilt` over `vercel deploy` when the build artifact must match CI exactly. `vercel build` locally → `vercel deploy --prebuilt` makes preview + prod byte-identical.
- Always smoke the preview URL (`curl -sI`) before promoting to production. Never auto-promote a preview to production without smoke-test confirmation.
- Use `vercel inspect <url> --wait` after every deploy to block until READY/ERROR. Without `--wait`, the CLI returns immediately and the deploy may still be building.
- Tail logs for the first 60s after a production deploy (`vercel logs --follow`). Cold-start failures and config-only runtime errors surface within that window.
- Configure a Log Drain (Datadog / Logflare / Axiom) for durable log retention — Vercel's native log retention is short.
- Pin function runtimes explicitly in `vercel.json` (`runtime: nodejs20.x`) — auto-detect can drift across Vercel platform upgrades.
- Use preview deploys for every PR — Vercel's GitHub integration provisions a per-commit URL automatically. Manual `vercel deploy` is for off-PR workflows.
- Never commit `.vercel/` directory. Add it to `.gitignore` if your project uses `vercel link`.
- Run `vercel --version` periodically. Vercel CLI updates monthly; user upgrades on their own schedule.

## Installation Requirements

- The Vercel CLI ships by default — `scripts/install.sh` runs the Vercel install step unconditionally. No opt-in flag is required.
- The install step prints the official npm install one-liner (`npm i -g vercel`) and reminds the user to run `vercel login` outside Claude. The step does NOT auto-execute either command — the user runs both manually.
- macOS / Linux / WSL2 all work with the npm install path. No platform-specific branch.
- **`vercel login` is the user's responsibility.** The install step does not authenticate. After install, run `vercel login` in an interactive shell before invoking this skill.
- The skill verifies authentication state by running `vercel whoami` at the start of every workflow. STOP and prompt the user if it returns non-zero — `Vercel auth missing. Run \`vercel login\` outside Claude, then re-invoke this skill.`
