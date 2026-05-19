# Vercel Deployment Provider

Vercel account setup, project linking, CLI install posture, pipelinekit integration via Charter Topic 10, environment configuration, runtime verification commands, auth posture, and provider comparison for edge-optimized workloads.

<div data-snippet="comparison-tabs"></div>

Vercel account setup, project linking, CLI install posture, pipelinekit integration via Charter Topic 10, environment configuration, runtime verification commands, auth posture, and provider comparison for edge-optimized workloads.

pipelinekit integrates Vercel as a first-class deployment provider on the same footing as Azure, Railway, Render, and DigitalOcean. When your project charter selects `vercel` as the deployment target (Charter Topic 10), pipelinekit routes deployment work to the `@vercel-deployment-engineer` agent and the `vercel-ops` skill automatically.

## 1. What is the Vercel provider integration

Vercel is a deployment platform optimized for frontend frameworks (Next.js, React, Vue, Svelte) and serverless functions. It offers edge-network acceleration, preview deployments per pull request, and zero-configuration deployments from Git.

The pipelinekit Vercel integration consists of three components:

- **`claude/skills/vercel-ops/SKILL.md`** — the operational skill that wraps the Vercel CLI (`vercel`) for day-to-day ops: deployment, status checks, environment variable management, domain configuration, and production/preview environment switching. Enforces the auth-posture contract (never auto-authenticates, always starts with `vercel whoami`).
- **`claude/agents/vercel-deployment-engineer.md`** — the deployment-engineer agent that covers Vercel project setup, environment configuration, performance optimization, preview-deployment workflows, team collaboration, billing guardrails, and the full provider-native verification chain.
- **Charter Topic 10 integration** — selecting `vercel` as the deployment provider in the project charter automatically routes `/pipeline` deployment phases to the agent and skill above.

## 2. Account & project setup

1.  Create a Vercel account at [vercel.com](https://vercel.com). You can sign up with GitHub for seamless Git integration.

2.  Create a Vercel project either via the Vercel Dashboard (import from GitHub / GitLab / Bitbucket) or the CLI:

        vercel

    This command launches an interactive setup that detects your framework and configures build settings automatically.

3.  Link your Git repository (GitHub / GitLab / Bitbucket). Vercel will watch this repo and deploy automatically on every push to the production branch (default: `main`).

4.  Configure the production branch and preview branches in the Vercel Dashboard:
    - `Production` — branch that deploys to your primary domain (e.g., `myapp.vercel.app`)
    - `Preview` — every PR gets a unique preview URL for testing

## 3. Install the Vercel CLI

The Vercel CLI (`vercel`) is the primary interface for pipelinekit's Vercel ops. Install it globally via npm:

    npm install -g vercel

Verify the installation:

    vercel --version

## 4. Authenticate to Vercel

Before running any deployment via pipelinekit, authenticate to Vercel outside of Claude:

    vercel login

This opens a browser for interactive login or email verification. After authentication, the CLI stores your credentials in `~/.vercel/` (never in shell history, env vars, or transcript).

Verify authentication with:

    vercel whoami

The `@vercel-deployment-engineer` agent runs `vercel whoami` as a preflight check before any deployment operation. If authentication is not set up, the agent STOPS and instructs you to authenticate outside Claude.

## 5. Environment variables & secrets

Store environment variables in the Vercel Dashboard or via CLI:

    vercel env add

This prompts for variable name and value, then asks which environments to target (Development, Preview, Production — select all or subset).

Example: Setting up a database connection string

    vercel env add DATABASE_URL

Then paste the connection string when prompted. Vercel encrypts the value and makes it available to your application during build and runtime.

View all env vars:

    vercel env ls

## 6. Deploy from Git (automatic)

Once your Vercel project is linked to GitHub, every push to the production branch triggers an automatic deployment:

1.  Push code to your production branch (e.g., `git push origin main`)
2.  Vercel detects the push and starts a build
3.  Build completes and app is live at your domain
4.  Preview deployments are created for every PR automatically

## 7. Deploy from CLI (manual)

For urgent hotfixes or testing, deploy directly from the CLI:

    vercel --prod

This deploys your current working directory to production. Omit `--prod` to create a preview deployment.

## 8. Integrate with pipelinekit Charter

When creating a new project via `/pipeline`, Step 0 (Charter Discovery) asks about deployment target (Topic 10). Select `vercel` to route deployment tasks to the `@vercel-deployment-engineer` agent.

For existing projects, ensure your charter includes:

    **Deployment Target:** vercel

## 9. Runtime verification

After deployment, pipelinekit verifies the application with a three-step chain:

1.  **Deployment state probe:** Check deployment status via Vercel CLI

        vercel ls --prod

2.  **Log tail (60 seconds):** Stream build and function logs to catch errors

        vercel logs $(vercel inspect) --since 60s

3.  **Health-endpoint polling:** Hit your application's health endpoint with exponential backoff

        for i in 1 2 4 8 16 32; do
          curl --fail --silent "https://myapp.vercel.app/health" && break
          echo "Health check failed — retrying in ${i}s"
          sleep "$i"
        done

## 10. Common deployment tasks

### Redeploy production

    vercel --prod --force

### View deployment history

    vercel ls

### Inspect a specific deployment

    vercel inspect https://myapp.vercel.app

### Check build settings

    vercel inspect --meta

### View function logs

    vercel logs --follow

## 11. Preview deployments & PR workflow

Every pull request linked to your Vercel project automatically gets a preview deployment. This allows reviewers to test changes in a live environment before merging.

Vercel adds a comment to your PR showing:

- Preview URL (e.g., `myapp-pr-123.vercel.app`)
- Build status (success / failure)
- Performance impact (Lighthouse scores)

Preview environments inherit env vars from the Preview environment settings in the Vercel Dashboard.

## 12. Auth posture & secret hygiene

The `@vercel-deployment-engineer` agent enforces:

- **Authentication is your responsibility.** You run `vercel login` outside Claude. The agent verifies authentication with `vercel whoami` and STOPS if not authenticated.
- **No credential env vars.** The agent never reads `VERCEL_TOKEN` or `VERCEL_AUTH_SECRET`. All credentials live in `~/.vercel/` (on-disk encrypted).
- **No token logging.** Secrets never appear in logs, comments, or debug output. If a token leaks, rotate it immediately via the Vercel Dashboard.
- **Application secrets in Vercel env vars.** Production API keys, database passwords, and third-party tokens belong in the Vercel Dashboard (Environment Variables), never in source code or .env files.
- **Separate prod/preview secrets.** Production secrets are never shared with preview environments. Configure preview-specific env vars separately in the Dashboard.

## 13. Performance & cost optimization

### Vercel Analytics

Enable Vercel Analytics to monitor Web Vitals (LCP, FID, CLS) and identify performance bottlenecks:

    npm install @vercel/analytics

Then import and enable in your app:

    import { Analytics } from '@vercel/analytics/react';

    export default function App() {
      return (
        <>
          {/* Your app */}
          <Analytics />
        </>
      );
    }

### Bandwidth monitoring

The free tier includes 100 GB bandwidth per month. Monitor usage in the Vercel Dashboard under Settings → Usage. Overage costs \$0.15 per GB.

### Function execution

Serverless Functions have a default timeout of 60 seconds (300 seconds on Pro plan). Long-running tasks (data processing, video transcoding) should be offloaded to external queues (e.g., AWS SQS, Bull queue, Firebase Cloud Tasks).

## 14. Comparison with other providers

| Dimension                 | Vercel                                    | Azure                                         | Railway                               | Render                                       | DigitalOcean                                |
|---------------------------|-------------------------------------------|-----------------------------------------------|---------------------------------------|----------------------------------------------|---------------------------------------------|
| **Primary Use Case**      | Frontend; edge functions; serverless      | Enterprise; multi-service; managed containers | Any runtime; persistent volumes; cron | Any runtime; simple PaaS; persistent storage | Any runtime; simple PaaS; managed databases |
| **Best For**              | Next.js, React, Svelte apps               | .NET, Java, complex services                  | Full-stack; microservices             | Web apps; simple backends                    | Simple web apps; prototypes                 |
| **Framework Support**     | Next.js (native), all SPA frameworks      | Language-agnostic (containers)                | Language-agnostic                     | Language-agnostic                            | Language-agnostic                           |
| **Edge Computing**        | Yes (Edge Functions, edge middleware)     | No native edge                                | No                                    | No                                           | No                                          |
| **Free Tier**             | 100 GB bandwidth, 1M Function invocations | \$200 credit × 30 days + always-free tier     | \$5/month credit (trial)              | Free tier (limited)                          | \$5/month credit                            |
| **Min Cost (Production)** | ~\$20/month (Pro)                         | ~\$15/month (B1 App Service)                  | ~\$7/month                            | ~\$7/month                                   | ~\$12/month (basic droplet)                 |
| **Git Integration**       | Automatic (GitHub, GitLab, Bitbucket)     | Manual (via GitHub Actions)                   | Automatic (Git branch → service)      | Automatic (GitHub, GitLab, Bitbucket)        | Manual (via GitHub Actions)                 |
| **Preview Deployments**   | Yes (per PR, automatic)                   | Manual (staging slots)                        | Manual (branch-based services)        | Manual                                       | Manual                                      |
| **CLI Tool**              | vercel (Vercel)                           | az (Microsoft)                                | railway (Railway)                     | render (Render)                              | doctl (DigitalOcean)                        |

## 15. Troubleshooting

### Build fails with "Command failed"

Check the build logs in the Vercel Dashboard:

1.  Navigate to your project
2.  Click the failed deployment
3.  View the build log for error details

Common causes:

- Missing build script in `package.json` — add `"build": "next build"`
- Env var not set — add it in Dashboard → Settings → Environment Variables
- File size too large — default limit is 50 MB per function, 100 MB deployment

### Function times out (504 Gateway Timeout)

Your function is taking longer than the timeout limit (60 seconds on free tier, 300 on Pro).

Solutions:

- Optimize the function (reduce database queries, cache results)
- Offload to async queue (e.g., AWS SQS, Bull, Firebase Cloud Tasks)
- Upgrade to Pro plan for longer timeout

### "Not authenticated to Vercel"

Run `vercel login` outside Claude, then verify with `vercel whoami`.

### Preview deployment not showing

Ensure your GitHub PR is linked to a Vercel project:

1.  Check the Vercel Dashboard → Settings → Integrations
2.  Ensure the GitHub app is installed and authorized
3.  Re-push to the PR branch to trigger a new deployment

## 16. Additional resources

- [Vercel Documentation](https://vercel.com/docs)
- [Vercel CLI Reference](https://vercel.com/docs/cli)
- [Next.js Documentation](https://nextjs.org/docs)
- [Serverless Functions Guide](https://vercel.com/docs/concepts/functions/serverless-functions)
- [Edge Network Overview](https://vercel.com/docs/concepts/edge-network/overview)
- [Web Vitals Monitoring](https://vercel.com/docs/concepts/analytics/web-vitals)

