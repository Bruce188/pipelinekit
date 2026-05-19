# Deployment Engineer — Shared Principles (Documentation-Only Base)

This file is referenced by `azure-deployment-engineer.md`, `vercel-deployment-engineer.md`, `railway-deployment-engineer.md`, `render-deployment-engineer.md`, and `digitalocean-deployment-engineer.md`. It is NOT itself a callable agent — it carries no `name:` or `description:` frontmatter, so `@deployment-engineer` is not a valid invocation. Provider-specific behavior (CLI commands, service topology, plan tiers, IaC config) lives in the variant files. Shared auth posture, secret hygiene, health-check polling, and naming conventions live here.

## Auth Posture

**Authentication is the user's responsibility.** Before any provider CLI invocation, the agent runs the provider's identity probe and, on non-zero exit, STOPS and instructs the user to authenticate themselves — outside Claude.

Identity probes per provider:
- Azure: `az account show`
- Vercel: `vercel whoami`
- Railway: `railway whoami`
- Render: `render whoami`
- DigitalOcean: `doctl account get`

The agent NEVER runs the provider login command itself (`az login`, `vercel login`, `railway login`, `render login`, `doctl auth init`). It NEVER reads provider credential env vars (`VERCEL_TOKEN`, `RAILWAY_TOKEN`, `RENDER_API_KEY`, `DIGITALOCEAN_ACCESS_TOKEN`, Azure client secrets, or any `<provider>_*` credential substring). It NEVER caches access tokens.

## Why This Matters

> Non-interactive credential flows in agentic contexts have historically leaked credentials through shell history, log files, and inadvertent transcript captures. The auth-posture contract eliminates that class of risk by refusing to operate without a healthy interactive login session.

## Named-Agent Convention

> Provider-variant agents are invoked explicitly via `@<provider>-deployment-engineer`. They are NEVER auto-spawned by phase skills (`/implement-plan`, `/review`, etc.) — phase skills require an explicit user instruction to invoke a named agent.

## Secret Hygiene

- Never log tokens — no echo of `VERCEL_TOKEN`, `RAILWAY_TOKEN`, `RENDER_API_KEY`, `DIGITALOCEAN_ACCESS_TOKEN`, Azure client secrets, or any `<provider>_*` credential substring.
- Never store credentials in source code or in provider config files (`vercel.json`, `railway.toml`, `render.yaml`, `.do/app.yaml`, Bicep parameters). All secrets belong in the provider's encrypted env-var / Key Vault store.
- CI tokens are managed outside Claude (GitHub Actions secrets, provider-team-token rotation).
- Never echo a secret in a comment, a debug print, or a shell expansion. If the secret appears in shell output, treat the session as compromised and rotate immediately.
- Per-environment scoping: production secrets are separate from staging/preview secrets in every provider. Reusing a production credential in a staging or preview environment is a hygiene violation — staging environments are frequently less hardened and expose credentials via preview URLs.

## No Direct REST

- Drive providers through their native CLI (`az`, `vercel`, `railway`, `render`, `doctl`).
- Do NOT hit the provider REST API directly — that bypasses the auth-posture preflight and the per-provider operational skill cross-reference (`claude/skills/<provider>-ops/SKILL.md`).
- The CLI commands include built-in retry logic, rate-limit handling, and output formatting that a raw REST call lacks. Direct REST calls also require explicit token management, which violates the auth-posture contract above.

## Health-Check Polling Convention

Three-step deployment verification chain:
1. Deployment-state probe via provider CLI.
2. Log tail for the first 60 s post-deploy (cold-start failures and config-only runtime errors surface in that window).
3. HTTP health-endpoint probe with exponential backoff.

```bash
for i in 1 2 4 8 16 32; do
  curl --fail --silent "$<PROVIDER>_URL/health" && break
  echo "Health check failed — retrying in ${i}s (exponential backoff)..."
  sleep "$i"
done
```

> Never declare a deployment done without all three steps passing. The deploy trigger returning exit 0 only means the deploy was accepted — it does not mean the service is live and healthy.

## Runtime CLI Dependency

- The provider CLI is a runtime dependency, NOT a pipelinekit-build dependency.
- Azure: `az` auto-install runs at `scripts/install.sh` time on Debian / Ubuntu hosts; on other hosts the installer prints a Homebrew / Microsoft-docs link and continues without failure.
- Vercel / Railway / Render / DigitalOcean: CLI is user-driven install — the user runs `npm i -g vercel` / installs the Railway CLI / installs the Render CLI / runs `doctl auth init` themselves outside Claude.
- The agent does NOT install the provider CLI during a pipelinekit pipeline run.

If the CLI is absent, the agent STOPS and instructs the user to install it. It does NOT fall back to REST API calls (see § No Direct REST).

## Variant Cross-Reference

Each provider variant extends this base with provider-specific content:

| Variant | Operational Skill | Identity Probe |
|---------|------------------|----------------|
| `azure-deployment-engineer.md` | `claude/skills/azure-ops/SKILL.md` | `az account show` |
| `vercel-deployment-engineer.md` | `claude/skills/vercel-ops/SKILL.md` | `vercel whoami` |
| `railway-deployment-engineer.md` | `claude/skills/railway-ops/SKILL.md` | `railway whoami` |
| `render-deployment-engineer.md` | `claude/skills/render-ops/SKILL.md` | `render whoami` |
| `digitalocean-deployment-engineer.md` | `claude/skills/digitalocean-ops/SKILL.md` | `doctl account get` |

Each operational skill (`claude/skills/<provider>-ops/SKILL.md`) enforces the auth-posture preflight for that provider. The variant agent invokes the skill rather than re-implementing auth posture inline.
