---
name: deploy
description: Deploys, verifies and operates apps on Vercel, Railway, Render, DigitalOcean App Platform and Azure (Container Apps, App Service) through each provider's CLI. Covers auth preflight, preview vs production deploys, env vars and secrets, health checks, logs and rollback. Use whenever the user says deploy, ship, release, push to prod or promote, asks why a build or deploy failed, wants logs from a hosted app, needs to set an env var on a provider, or needs to roll back, even if they only name the provider. Stops if the CLI is missing or not logged in, and never logs in for the user.
---

# deploy

## 1. Pick the provider

| Repo signal | Provider | Read |
|---|---|---|
| `vercel.json`, `.vercel/` | Vercel | `references/vercel.md` |
| `railway.json`, `railway.toml`, `.railway/` | Railway | `references/railway.md` |
| `render.yaml` | Render | `references/render.md` |
| `.do/app.yaml` | DigitalOcean App Platform | `references/digitalocean.md` |
| `.github/workflows/*` using `azure/login` and `az containerapp`; `azure.yaml`; `infra/*.bicep` | Azure | `references/azure.md` |

Read only the reference for the detected provider. If more than one matches, or none does, ask the user.

## 2. Rules for every provider

1. **Preflight auth.** Run the provider's whoami or account command first. If it fails, stop and ask the user to log in from their own terminal. Never run `login` yourself, and never switch the team, project, environment or subscription without being told to.
2. **Production only on explicit user intent.** Default to preview or staging. "Deploy" alone means preview. Treat "ship to prod", "promote", or a production rollback as the explicit intent.
3. **Secrets never go in argv or chat.** Don't echo tokens or env values, and don't put a secret value on a command line that you run, because it ends up in the transcript and the shell history. Use the provider's stdin or file option, or give the user the command to run with the value filled in themselves. Never commit `.vercel/`, `.railway/`, `.env*`, or anything else with credentials in it.
4. **Avoid prompts.** Use non-interactive flags (listed per provider) so a prompt cannot hang the shell.
5. **Run migrations as a pre-deploy step**, not at app start, whenever more than one instance can run (see rule 6).
6. **Verify every deploy, in this order:**
   1. Wait for the deploy to finish (the provider's `--wait` or `inspect`).
   2. Hit the health endpoint, `/health` or `/healthz`, rather than `/`.
   3. Read the error logs since the deploy started.
   4. Report the URL, the deployment ID and the status.
7. **Rollback** means returning to a known-good deployment or image, never a force push. Some providers only offer rollback in the dashboard. When that is the case, say so and give the user the steps.

## 3. Trading bots: never run two at once

Zero-downtime and rolling deploys keep the old instance running until the new one is healthy. For a web app that is a feature. For a trading bot it means **two live bots on the same account for a few seconds to minutes**. Both open positions, so orders get doubled and each bot cancels or "reconciles" the other's orders.

Before deploying CryptoBargain, FundingRateArb or any other process that places orders:

- **Use one instance with stop-then-start.** Scale to at most one replica, and pick a mode that stops the old instance before the new one starts. Where the platform can't do that, add a leader lock (below). The provider files list the settings for each platform.
- **Leader lock.** The bot takes an exclusive lock before trading and exits if it can't get it.
  - CryptoBargain uses `singleton.py` (`fcntl` on `state/.bot.lock`). That lock only works on a single host, so it won't stop a second container on another machine.
  - FundingRateArb has no cross-instance lock. Its code assumes a single-instance deployment (`SignalEngine` uses an in-process `SemaphoreSlim`).
  - For a multi-host lock, use a database lock (SQL Server `sp_getapplock`) or a blob lease.
- **Handle shutdown.** The bot must stop opening positions on SIGTERM, and on start it must reconcile against open exchange orders.
- **Pick the moment.** Before a production deploy, check that the bot isn't in the middle of a cycle (opening or closing a position). If you can't tell, ask.

How each project deploys today:
- **FundingRateArb.** GitHub Actions `deploy.yml` runs on every push to `main`:
  1. Builds the image and pushes it to ACR.
  2. Runs `dotnet ef database update` behind a temporary SQL firewall rule.
  3. Runs `az containerapp update --image`.
  4. Checks `/healthz`.

  Container Apps' default single-revision mode keeps the old revision live until the new one is ready, so the two overlap (see `references/azure.md`).
- **CryptoBargain.** Not on a PaaS. It runs on Bruce's own host as systemd units (`ops/cryptobargain-bot.service`, with `Restart=always` and `EnvironmentFile=.env`). Deploying it means `git pull` followed by `systemctl --user restart cryptobargain-bot` (or the system unit). systemd stops the old process before it starts the new one, and the flock catches accidental second copies. Moving it to a PaaS brings back the overlap problem.

## 4. If the CLI is missing

| CLI | Install |
|---|---|
| `vercel` | `npm i -g vercel` |
| `railway` | `npm i -g @railway/cli` |
| `render` | `brew install render`, or `curl -fsSL https://raw.githubusercontent.com/render-oss/cli/main/bin/install.sh \| sh` |
| `doctl` | `brew install doctl`, `sudo snap install doctl`, or the GitHub release tarball |
| `az` | Microsoft's install docs (`curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` on Debian/Ubuntu) |

Print the install line and stop. Don't install it yourself unless the user asks.
