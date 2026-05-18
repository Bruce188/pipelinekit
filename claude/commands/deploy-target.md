---
name: deploy-target
description: Set the active session deployment target (vercel, railway, render, digitalocean, or none).
allowed-tools: Read, Write, Bash, AskUserQuestion
argument-hint: <provider>
---

# /deploy-target — Select the active deployment provider

The deployment target tells `/pipeline` which overlay activates the deployment phase. Selection is session-scoped via the single-line file `docs/active-deployment` (one provider slug per line). Default: no provider, no deployment step. The slash command never auto-installs a CLI and never auto-authenticates — those responsibilities live in the per-provider skill (`vercel-ops`, etc.).

## Available providers

- `vercel` — Vercel deployments (Next.js / SvelteKit / Astro / static + Edge / serverless functions)
- `railway` — Railway deployments (apps + databases on Railway)
- `render` — Render deployments (web services / cron / workers)
- `digitalocean` — DigitalOcean App Platform deployments
- `none` — No deployment provider; the pipeline skips the deployment phase

Only `vercel` ships an end-to-end overlay in the MVP iteration. `railway`, `render`, and `digitalocean` write the slug but silently no-op until their overlay tables, agents, and skills are added in follow-up iterations. This preserves the default-no-op contract (no provider, no deployment step).

## Argument modes

- `/deploy-target <provider>` — Write `<provider>` (lowercase) to `docs/active-deployment`. Mutually exclusive — later invocations overwrite the prior value.
- `/deploy-target none` — Remove `docs/active-deployment`. Print `Deployment target cleared — pipeline will skip the deployment phase.`
- `/deploy-target` (no argument) — Use `AskUserQuestion` to offer the 4 valid provider slugs plus `none`. Then proceed as above.

## Process

1. Parse the argument from `$ARGUMENTS`.

2. If the argument is empty:
   - Use `AskUserQuestion` with the question "Which deployment provider should govern this session?" and the 5 options: `vercel`, `railway`, `render`, `digitalocean`, `none`.

3. Validate the chosen name. Must be one of: `vercel`, `railway`, `render`, `digitalocean`, `none`. Any other value: print `Unknown deployment target: <name>. Valid values: vercel, railway, render, digitalocean, none.` and exit.

4. If `none`:
   ```bash
   rm -f docs/active-deployment
   echo "Deployment target cleared — pipeline will skip the deployment phase."
   ```

5. Otherwise:
   ```bash
   mkdir -p docs
   echo "<name>" > docs/active-deployment
   echo "Active deployment target set to: <name>"
   ```

6. Remind the user (one line): `Deployment-target selection is session-scoped; /pipeline reads it at Step 0 and routes deployment-time work to the matching overlay.`

## Upstream selection paths

- `/pipeline` Step 0 (Charter Discovery, Topic 10 "Deployment target") is the canonical upstream selector during charter discovery. If the charter answer is set, this slash command is the mid-session override.
- When no charter exists and no slug is written, the pipeline auto-detects from provider config files in the working tree (`vercel.json`, `railway.toml`, `render.yaml`, `.do/app.yaml`); the detected provider activates its overlay.
- Explicit `/deploy-target <provider>` wins over both the charter answer and the auto-detection result.

## Constraints

- `docs/active-deployment` is a single-line file (one provider slug per line). Mutually exclusive across providers; later writes overwrite.
- `docs/active-deployment` is gitignored via `.git/info/exclude` and never-staged via `claude/config/never-stage.txt`.
- Do NOT auto-install any provider CLI (`npm i -g vercel`, `railway login`, etc.). The install one-liner is printed by `scripts/install.sh` under the `want vercel` (etc.) gate; the user runs it manually.
- Do NOT auto-authenticate. The per-provider ops skill (`vercel-ops`, etc.) STOPS and prompts the user to authenticate outside Claude.
- Do not modify any other file outside `docs/active-deployment`.
